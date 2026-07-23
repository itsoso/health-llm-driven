# ETH Staking Daily Report Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build, test, deploy, and verify a read-only ETH staking accounting service that sends a validator `1331` income report to Telegram every day at 09:01 Asia/Shanghai and exposes scoped external-agent skills.

**Architecture:** Version the implementation under `infra/eth-ops/` and deploy it independently to `/opt/eth-ops/staking-report`. Pure accounting functions consume normalized Beacon/Besu fixtures; adapters collect live chain data, persist public facts in a dedicated SQLite database, and deliver idempotent Telegram reports. A loopback-only HTTP API exposes read-only reports through hashed, scoped bearer tokens, while systemd services/timers own scheduling.

**Tech Stack:** Python 3 standard library, SQLite, Lighthouse Beacon REST API, Besu JSON-RPC, Telegram Bot API, systemd services/timers, pytest.

---

## Global Constraints

- Work on `main` as required by repository instructions; stage only files listed in each task.
- Do not read, copy, log, or test with validator keystores, mnemonics, signing keys, execution JWT, Telegram token, or production bearer tokens.
- No external-agent operation may restart services, sign messages, withdraw, transfer, transact, or mutate chain state.
- Keep ETH Ops runtime and data outside the health backend and health PostgreSQL.
- Use `Asia/Shanghai` for report windows and schedule; report at `09:01`.
- Unknown/incomplete values remain unknown; never coerce them to zero.
- Run tests directly; never pipe tests to `tail`.
- Deployment must not restart Besu, Lighthouse beacon, or Lighthouse validator.

### Task 1: Create the isolated package and deterministic accounting model

**Files:**
- Create: `infra/eth-ops/staking_report/__init__.py`
- Create: `infra/eth-ops/staking_report/models.py`
- Create: `infra/eth-ops/staking_report/accounting.py`
- Create: `infra/eth-ops/tests/test_accounting.py`
- Create: `infra/eth-ops/tests/fixtures/proposed_block.json`
- Create: `infra/eth-ops/tests/fixtures/receipts.json`

**Step 1: Write failing accounting tests**

Cover:

- consensus delta from two gwei balances;
- priority fee formula per receipt;
- base fee subtraction cannot become negative;
- non-proposed blocks are excluded;
- missing receipt makes execution result incomplete rather than zero;
- Wei → ETH conversion uses `Decimal`.

Representative assertion:

```python
def test_priority_fees_sum_effective_tip_per_receipt():
    block = {"baseFeePerGas": "0x64"}
    receipts = [
        {"gasUsed": "0x5208", "effectiveGasPrice": "0x78"},
        {"gasUsed": "0x2710", "effectiveGasPrice": "0x6e"},
    ]
    result = calculate_priority_fees(block, receipts)
    assert result.wei == 520_000
    assert result.complete is True
```

**Step 2: Run tests and confirm RED**

Run:

```bash
python3 -m pytest infra/eth-ops/tests/test_accounting.py -q
```

Expected: FAIL because `staking_report.accounting` does not exist.

**Step 3: Implement minimal immutable models and pure functions**

Implement:

- `wei_to_eth(wei: int) -> Decimal`
- `consensus_delta_gwei(start: int, end: int) -> Decimal`
- `calculate_priority_fees(block, receipts) -> AmountResult`
- `sum_known_amounts(...)` that refuses to return a complete total if a required component is unknown.

Use integer parsing for hex RPC values and `Decimal` only at the display boundary.

**Step 4: Run tests and confirm GREEN**

Run the same pytest command. Expected: all Task 1 tests pass.

**Step 5: Commit**

```bash
git add infra/eth-ops/staking_report/__init__.py infra/eth-ops/staking_report/models.py infra/eth-ops/staking_report/accounting.py infra/eth-ops/tests/test_accounting.py infra/eth-ops/tests/fixtures/proposed_block.json infra/eth-ops/tests/fixtures/receipts.json
git commit -m "feat(eth-ops): add deterministic staking accounting"
```

### Task 2: Implement natural-day windows, snapshots, and SQLite persistence

**Files:**
- Create: `infra/eth-ops/staking_report/windows.py`
- Create: `infra/eth-ops/staking_report/store.py`
- Create: `infra/eth-ops/tests/test_windows.py`
- Create: `infra/eth-ops/tests/test_store.py`

**Step 1: Write failing tests**

Cover:

- previous `Asia/Shanghai` natural-day boundaries;
- UTC conversion across date boundaries;
- nearest snapshot selection with actual sample timestamps retained;
- absent start/end snapshot produces `incomplete`;
- schema creation is idempotent;
- report and delivery idempotency keys are unique;
- bearer token material is never stored in report tables.

**Step 2: Run tests and confirm RED**

```bash
python3 -m pytest infra/eth-ops/tests/test_windows.py infra/eth-ops/tests/test_store.py -q
```

**Step 3: Implement the SQLite store**

Tables:

- `validator_snapshots`
- `proposed_blocks`
- `execution_rewards`
- `exchange_rates`
- `daily_reports`
- `deliveries`
- `alerts`
- `api_tokens`
- `api_audit`

Use SQLite WAL, foreign keys, explicit transactions, ISO UTC timestamps, and a schema version table. Store only token SHA-256 hashes plus metadata.

**Step 4: Run tests and confirm GREEN**

Run Task 2 tests and then Task 1+2 tests.

**Step 5: Commit**

```bash
git add infra/eth-ops/staking_report/windows.py infra/eth-ops/staking_report/store.py infra/eth-ops/tests/test_windows.py infra/eth-ops/tests/test_store.py
git commit -m "feat(eth-ops): persist validator income snapshots"
```

### Task 3: Add Beacon and Besu read-only collectors

**Files:**
- Create: `infra/eth-ops/staking_report/http_client.py`
- Create: `infra/eth-ops/staking_report/beacon.py`
- Create: `infra/eth-ops/staking_report/besu.py`
- Create: `infra/eth-ops/staking_report/collector.py`
- Create: `infra/eth-ops/tests/test_beacon.py`
- Create: `infra/eth-ops/tests/test_besu.py`
- Create: `infra/eth-ops/tests/test_collector.py`
- Create: `infra/eth-ops/tests/fixtures/beacon_validator.json`
- Create: `infra/eth-ops/tests/fixtures/beacon_block.json`

**Step 1: Write failing adapter tests**

Cover:

- validator index is fixed by configuration and validated as numeric;
- Beacon validator response parsing;
- proposer duty and signed beacon block map to execution block hash/number;
- only validator `1331` blocks enter reward accounting;
- JSON-RPC response IDs/errors are validated;
- receipt collection is bounded and timeout-aware;
- Beacon/Besu errors are returned as structured data-quality errors, not swallowed.

**Step 2: Run tests and confirm RED**

```bash
python3 -m pytest infra/eth-ops/tests/test_beacon.py infra/eth-ops/tests/test_besu.py infra/eth-ops/tests/test_collector.py -q
```

**Step 3: Implement minimal read-only collectors**

Default endpoints:

- Beacon: `http://127.0.0.1:5052`
- Besu: `http://127.0.0.1:8545`

No endpoint may accept an execution JWT or validator key. Enforce loopback defaults; non-loopback endpoints require explicit configuration.

**Step 4: Run tests and confirm GREEN**

Run Task 3 tests, followed by all `infra/eth-ops/tests`.

**Step 5: Commit**

```bash
git add infra/eth-ops/staking_report/http_client.py infra/eth-ops/staking_report/beacon.py infra/eth-ops/staking_report/besu.py infra/eth-ops/staking_report/collector.py infra/eth-ops/tests/test_beacon.py infra/eth-ops/tests/test_besu.py infra/eth-ops/tests/test_collector.py infra/eth-ops/tests/fixtures/beacon_validator.json infra/eth-ops/tests/fixtures/beacon_block.json
git commit -m "feat(eth-ops): collect validator and execution rewards"
```

### Task 4: Add evidence-based MEV attribution and ETH/CNY conversion

**Files:**
- Create: `infra/eth-ops/staking_report/mev.py`
- Create: `infra/eth-ops/staking_report/exchange.py`
- Create: `infra/eth-ops/tests/test_mev.py`
- Create: `infra/eth-ops/tests/test_exchange.py`
- Create: `infra/eth-ops/tests/fixtures/builder_payment_block.json`

**Step 1: Write failing positive and negative tests**

MEV cases:

- explicit builder payment to configured fee recipient;
- ordinary transfer to fee recipient is not automatically MEV;
- coinbase/fee-recipient ambiguity returns `unknown`;
- no relay evidence returns `unknown`, not zero;
- priority fee and MEV are not double counted.

Exchange cases:

- parse provider ETH/CNY response;
- reject non-positive, stale, boolean, NaN, and infinite rates;
- attach provider and fetched timestamp;
- timeout/error returns unavailable without changing ETH amounts.

**Step 2: Run tests and confirm RED**

```bash
python3 -m pytest infra/eth-ops/tests/test_mev.py infra/eth-ops/tests/test_exchange.py -q
```

**Step 3: Implement evidence rules and rate provider interface**

Use a primary HTTPS ETH/CNY provider and a separately configured fallback. Cache only successful responses. Do not derive or invent a rate when both providers fail.

**Step 4: Run tests and confirm GREEN**

Run Task 4 tests and the complete ETH Ops test directory.

**Step 5: Commit**

```bash
git add infra/eth-ops/staking_report/mev.py infra/eth-ops/staking_report/exchange.py infra/eth-ops/tests/test_mev.py infra/eth-ops/tests/test_exchange.py infra/eth-ops/tests/fixtures/builder_payment_block.json
git commit -m "feat(eth-ops): attribute mev and convert rewards to cny"
```

### Task 5: Generate deterministic reports and send idempotent Telegram messages

**Files:**
- Create: `infra/eth-ops/staking_report/report.py`
- Create: `infra/eth-ops/staking_report/telegram.py`
- Create: `infra/eth-ops/staking_report/alerts.py`
- Create: `infra/eth-ops/tests/test_report.py`
- Create: `infra/eth-ops/tests/test_telegram.py`
- Create: `infra/eth-ops/tests/test_alerts.py`

**Step 1: Write failing tests**

Cover:

- complete daily report;
- first-day “基线建立中” report;
- incomplete priority fee/MEV/rate language;
- no unknown value is rendered as `0`;
- Telegram visible text contains no token or internal endpoint;
- delivery idempotency prevents duplicate 09:01 reports;
- 30-minute alert dedup and recovery;
- Telegram non-2xx and malformed response fail loudly and remain pending.

**Step 2: Run tests and confirm RED**

```bash
python3 -m pytest infra/eth-ops/tests/test_report.py infra/eth-ops/tests/test_telegram.py infra/eth-ops/tests/test_alerts.py -q
```

**Step 3: Implement report and delivery services**

Required environment variables:

- `ETH_TELEGRAM_BOT_TOKEN`
- `ETH_TELEGRAM_CHAT_ID`

Never include their values in exceptions or logs. Use plain text Telegram messages to avoid parse-mode injection. Store a deterministic delivery key:

```text
telegram:daily:<report_date>:<chat_hash>
```

**Step 4: Run tests and confirm GREEN**

Run Task 5 tests and the complete ETH Ops test directory.

**Step 5: Commit**

```bash
git add infra/eth-ops/staking_report/report.py infra/eth-ops/staking_report/telegram.py infra/eth-ops/staking_report/alerts.py infra/eth-ops/tests/test_report.py infra/eth-ops/tests/test_telegram.py infra/eth-ops/tests/test_alerts.py
git commit -m "feat(eth-ops): send staking reports to telegram"
```

### Task 6: Replace unsafe token management and expose the read-only skill API

**Files:**
- Create: `infra/eth-ops/staking_report/auth.py`
- Create: `infra/eth-ops/staking_report/api.py`
- Create: `infra/eth-ops/skills/staking-report/SKILL.md`
- Create: `infra/eth-ops/tests/test_auth.py`
- Create: `infra/eth-ops/tests/test_api.py`
- Create: `infra/eth-ops/tests/test_skill_manifest.py`

**Step 1: Write failing security tests**

Cover:

- no hardcoded admin/token material in source;
- only token hash is persisted;
- create-token output returns plaintext once, list never returns plaintext;
- expiry, revocation, scope and constant-time verification;
- unauthorized 401, wrong scope 403;
- API routes are GET-only;
- responses exclude secrets and signing material recursively;
- CORS is explicit or absent, never wildcard;
- audit records never contain Authorization;
- skill manifest only documents `health`, `daily-report`, `rewards-range`, `alerts`.

**Step 2: Run tests and confirm RED**

```bash
python3 -m pytest infra/eth-ops/tests/test_auth.py infra/eth-ops/tests/test_api.py infra/eth-ops/tests/test_skill_manifest.py -q
```

**Step 3: Implement the scoped loopback API**

Routes:

- `GET /v1/health`
- `GET /v1/reports/daily?date=YYYY-MM-DD`
- `GET /v1/rewards?from=...&to=...`
- `GET /v1/alerts?since=...`

Token creation/revocation is an offline root-only CLI, not a public HTTP endpoint.

**Step 4: Run tests and confirm GREEN**

Run Task 6 tests and the complete ETH Ops test directory.

**Step 5: Commit**

```bash
git add infra/eth-ops/staking_report/auth.py infra/eth-ops/staking_report/api.py infra/eth-ops/skills/staking-report/SKILL.md infra/eth-ops/tests/test_auth.py infra/eth-ops/tests/test_api.py infra/eth-ops/tests/test_skill_manifest.py
git commit -m "security(eth-ops): expose scoped read-only staking skill"
```

### Task 7: Add CLI, systemd units, deployment and rollback

**Files:**
- Create: `infra/eth-ops/staking_report/cli.py`
- Create: `infra/eth-ops/systemd/eth-staking-snapshot.service`
- Create: `infra/eth-ops/systemd/eth-staking-snapshot.timer`
- Create: `infra/eth-ops/systemd/eth-staking-report.service`
- Create: `infra/eth-ops/systemd/eth-staking-report.timer`
- Create: `infra/eth-ops/systemd/eth-staking-api.service`
- Create: `infra/eth-ops/eth-staking.env.example`
- Create: `infra/eth-ops/deploy.sh`
- Create: `infra/eth-ops/README.md`
- Create: `infra/eth-ops/tests/test_infrastructure.py`

**Step 1: Write failing infrastructure tests**

Assert:

- report timer contains `OnCalendar=*-*-* 09:01:00 Asia/Shanghai` or equivalent valid calendar/timezone directives;
- snapshot timer includes 00:01 and hourly collection with `Persistent=true`;
- services run as dedicated `eth-ops` user, not root;
- `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome=true`;
- writable paths are limited to `/var/lib/eth-ops` and `/var/log/eth-ops`;
- API listens only on `127.0.0.1`;
- EnvironmentFile is root-only and optional example contains no secrets;
- deployment never restarts `eth1`, `besu`, `lighthouse-beacon`, or `lighthouse-validator`;
- deploy keeps a versioned rollback directory and verifies checksums.

**Step 2: Run tests and confirm RED**

```bash
python3 -m pytest infra/eth-ops/tests/test_infrastructure.py -q
```

**Step 3: Implement CLI and deployment artifacts**

CLI commands:

- `snapshot`
- `report --date`
- `alert-check`
- `serve`
- `token-create --name --scope --expires-at`
- `token-revoke --id`

`deploy.sh` must:

1. build a deterministic source archive;
2. copy it to a versioned `/opt/eth-ops/releases/<sha>`;
3. create/update `/opt/eth-ops/staking-report` symlink;
4. install units;
5. daemon-reload;
6. start only the new API/timers;
7. run shadow smoke;
8. roll back the symlink and new units on failure.

**Step 4: Run tests and confirm GREEN**

Run infrastructure tests and the complete ETH Ops test directory.

**Step 5: Commit**

```bash
git add infra/eth-ops/staking_report/cli.py infra/eth-ops/systemd infra/eth-ops/eth-staking.env.example infra/eth-ops/deploy.sh infra/eth-ops/README.md infra/eth-ops/tests/test_infrastructure.py
git commit -m "chore(eth-ops): add secure staking report runtime"
```

### Task 8: Full local verification and security review

**Files:**
- Modify as required only when verification exposes a real defect.
- Update: `docs/dossiers/2026-07-23-eth-staking-report.md`

**Step 1: Run the focused suite**

```bash
python3 -m pytest infra/eth-ops/tests -q
```

Expected: all tests pass.

**Step 2: Run repository infrastructure and document gates**

```bash
python3 -m pytest scripts/test_infrastructure_security.py -q
python3 backend/scripts/check_dossier_consistency.py
python3 scripts/check_doc_drift.py
```

Expected: all commands exit 0.

**Step 3: Scan for secrets and forbidden capabilities**

Search the new tree for:

```text
token literals, private keys, mnemonic, jwtsecret, withdraw, sign, transfer,
systemctl restart eth1/besu/lighthouse, Access-Control-Allow-Origin: *
```

Expected: no secret literal or write capability; documentation references are allowed only where explicitly safe.

**Step 4: Run a fixture-based shadow report**

Generate a report using recorded fixtures and a temporary SQLite database. Expected: deterministic report, no network, no Telegram delivery.

**Step 5: Update Dossier G2/G3/G4**

Record exact commands and results. Commit only files changed by this task.

### Task 9: ETH2 shadow deployment and Telegram canary

**Files:**
- Update: `docs/dossiers/2026-07-23-eth-staking-report.md`

**Step 1: Preflight production without mutation**

Verify:

- `eth1`/`besu` alias active;
- Lighthouse beacon/validator active;
- Beacon/Besu APIs healthy;
- disk and memory capacity;
- `/opt/eth-ops` backup;
- Telegram configuration availability by boolean only, never print values.

**Step 2: Deploy new runtime with timers disabled**

Deploy to a versioned release. Keep API loopback-only. Do not replace the existing health/alert scripts until compatibility is proven.

**Step 3: Run live shadow collection**

Collect validator snapshot, proposer evidence, execution data and exchange rate. Generate report JSON/text without Telegram.

Expected:

- validator `1331`;
- all chain facts have source timestamps;
- unknown MEV remains unknown;
- no service restart count increases.

**Step 4: Send one Telegram canary**

Send a clearly labeled canary report using the configured target chat. Verify Telegram returns success and delivery is recorded once.

**Step 5: Security migration**

- Back up existing OpenClaw API config.
- Remove hardcoded initial key behavior and full-token list responses by deploying the new API.
- Rotate/revoke legacy exposed keys.
- Keep the API loopback-only until Nginx auth and TLS smoke pass.

**Step 6: Enable timers**

Enable/start snapshot and 09:01 report timers only after shadow and canary pass.

**Step 7: Commit Dossier deployment evidence**

Record release SHA, rollback path, canary result and timer next-run timestamps.

### Task 10: Production health gate and next-day verification

**Files:**
- Update: `docs/dossiers/2026-07-23-eth-staking-report.md`
- Update system map only if the repository generator classifies this infrastructure as a generated architectural fact.

**Step 1: Immediate post-deploy smoke**

Verify:

- one Besu process;
- `eth1.service`/`besu.service` active;
- EL online, beacon synced/non-optimistic;
- validator active/not slashed;
- execution block advances;
- new API returns 401 without auth and 200 for scoped canary token;
- no secret in logs;
- timers show expected next runs.

**Step 2: Observe alert cycle**

Run `alert-check` without injecting a production fault. Confirm healthy state produces no duplicate Telegram alert.

**Step 3: Verify the first 09:01 report**

If two boundary snapshots do not yet exist, expected result is “基线建立中”. Confirm one Telegram delivery and a stored idempotency key.

**Step 4: Verify the first complete natural-day report**

After the next complete Beijing day:

- recompute consensus delta from stored snapshots;
- recompute priority fees from recorded block/receipt evidence;
- verify MEV evidence/unknown status;
- verify ETH/CNY multiplication and provider timestamp;
- confirm Telegram receipt.

**Step 5: Close Gates**

Update G5/G6/S8, run dossier consistency/doc drift, commit, and push `main` only when every gate is green. If any production gate fails, disable only the new timers/API and restore the prior `/opt/eth-ops/staking-report` symlink; do not touch validator/Besu/Lighthouse data.

