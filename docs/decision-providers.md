# Jev / Laya decision routing

The optional decision service is independent of the answer LLM. Configure one
provider on the backend and restart. No key belongs in a client or committed file.

## Jev direct

```dotenv
DECISION_MODE=shadow
DECISION_PROVIDER=jev
DECISION_MODEL=jev-1.13.0
DECISION_API_KEY=<set in server secret storage>
DECISION_TIMEOUT_SECONDS=2
DECISION_MIN_CONFIDENCE=0.8
```

Default endpoint: https://api.typesafe.ai/v1/systemone. The existing AI consent
screen includes TypeSafe and the exact destination when enabled. Users must
accept the new policy revision before remote I/O. Shadow also sends data.

## Local Laya

For development, start Laya separately (not in the application environment).
Production uses the pinned, authenticated deployment described below:

```sh
python3.12 -m venv ~/.venvs/laya
~/.venvs/laya/bin/python -m pip install 'laya[serve]==0.3.11'
LAYA_HOST=127.0.0.1 LAYA_PORT=8092 LAYA_DEVICE=cpu LAYA_MODELS=multilingual \
  LAYA_API_KEY="$DECISION_API_KEY" \
  ~/.venvs/laya/bin/laya-serve
```

```dotenv
DECISION_MODE=shadow
DECISION_PROVIDER=laya
DECISION_BASE_URL=http://127.0.0.1:8092/v1
DECISION_MODEL=multilingual
# DECISION_API_KEY must match the service's private bearer key.
```

Loopback is relative to the backend process/container, not the end user's Mac.
Only loopback allows HTTP; use authenticated HTTPS for another machine. Laya's
default multilingual context is short: the adapter conservatively caps the
serialized state/questions at 960 UTF-8 bytes and each question at 240 bytes,
and rejects larger input rather than silently truncating. This intentionally
trades coverage for safety; a custom checkpoint needs its own evaluated adapter
budget. Full histories are never passed by the routing integration.

### Verified local installation (2026-09-24, Asia/Shanghai)

The development Mac has a separate native ARM environment at `~/.venvs/laya`
and a current-user LaunchAgent named `com.reva.laya`. Its wrapper and usage
instructions are in `~/.local/share/laya/README.md`. The service listens only on
`127.0.0.1:8092`, requires a private bearer key, uses Apple MPS, and loads the
multilingual checkpoint offline from revision
`aa8c91ca088ec597df95a0d1c76b3063cb2ae5e8`. All downloaded model files were checked
against the pinned repository's hashes. Credentials are outside the repository.

To use its private connection profile before starting a local backend:

```sh
source ~/.local/share/laya/reva.env
```

This profile selects `shadow`. Real HTTP Choice/Score/Noul calls, wrong/missing
key rejection, loopback binding, restart recovery, and the Reva adapter were
verified. A short synthetic request with three questions measured 19.7 ms median
HTTP latency over seven warmed calls; this is not a concurrency or accuracy
benchmark. A separate abbreviated Chinese choice example selected the wrong
option with low confidence, so business-quality calibration remains necessary.
Evidence is in `~/.local/share/laya/deployment-verification.json`.

Local requests do not initialize the remote consent/database module. Its cold
import exceeded the two-second decision budget during initial verification;
the import now occurs only in the existing remote-consent branch. Identity and
configuration checks still apply to every request, and remote consent remains
mandatory immediately before sending.

## Production and administrator switch

The Web management page `/admin` shows “意图决策服务” only for administrator
user_id=3. GET/PUT `/api/v1/admin/decisions` independently require the authenticated
user to be active, have is_admin=true, and have id=3. This is a global switch,
initially disabled, stored in PostgreSQL. PUT accepts only `enabled` (Boolean)
and the last read `revision`. Conflicts return 409; the update and audit are atomic.

`DECISION_ADMIN_CONTROL_ENABLED=true` makes every routing boundary read this
switch afresh. Missing/unavailable state produces an explicit fallback, and
disabling during inference discards the returned advice. `DECISION_MODE=off`
always overrides the database. Changing providers still uses server deployment
configuration; API keys and destination URLs are never editable in the browser.

The production deployment uses `infra/laya/requirements.lock`, a Linux x86_64
Python 3.12 CPU-only dependency lock, and `model-manifest.json` with exact hashes.
The three small upstream JSON configurations are included as Base64 assets that
preserve their exact original bytes, with Apache 2.0 license and provenance.
The two large model/tokenizer files use the
fixed `hf-mirror.com` mirror because the production host cannot reach the original
Hugging Face endpoint. Only HTTPS redirects to the verified upstream
`cas-bridge.xethub.hf.co` CDN are permitted; proxy environment settings and
alternative-source fallback are disabled. Original upstream byte sizes and full
SHA256 hashes remain mandatory during installation and every reuse.
The reviewed `deploy.sh -b` exports only named assets from the exact candidate
Git bundle under the existing release lease, prepares them before stopping the
backend, then starts and verifies the separate service while the old backend is
still healthy. First installation requires proof that the exact old backend
source has no decision integration. The candidate checkout only re-verifies it.
Normal production publishing continues through the trusted release workflow.

The publisher creates a first-use Laya profile only when the live configuration
contains no `DECISION_*` assignments. Explicit settings, including off or Jev,
are preserved. The random private key is included before the normal environment
snapshot/seal; an existing sidecar key is reused after an old-backend rollback.
The database switch remains disabled until the designated administrator acts.

The sidecar listens on `127.0.0.1:8092` as `reva-laya`, with bearer authentication,
offline model loading, no health-directory access, a 2-CPU quota and 3-GB memory
limit. `/etc/reva-laya/service.env` is root-owned and readable only by its group.
Generation files are root-controlled; the service cannot update them. Successful
installation requires actual synthetic inference, wrong-key rejection, immutable
identity checks and a stable process across the restart interval.

Rollback first disables the switch; the established code routing remains usable.
The standard backend rollback restores old code/environment and deliberately
leaves the independent Laya service idle, retaining the additive table and audit.
The installer only reuses an identical, completely verified installation. An
unknown partial install or an upgrade is a BLOCK requiring a separately reviewed
operator change, never an overwrite, retry with a new identity, or deletion of
release evidence. Linux production acceptance remains a release gate, separate
from the development Mac results above.

## Compatible or remotely hosted service

```dotenv
DECISION_MODE=shadow
DECISION_PROVIDER=systemone
DECISION_BASE_URL=https://decision.example.com/v1
DECISION_MODEL=laya-multilingual
DECISION_RECIPIENT_NAME=Your decision service operator
DECISION_API_KEY=<optional service bearer token>
DECISION_MAX_INPUT_BYTES=960
```

`systemone` requires explicit URL/model; remote services require a recipient
name. Use the service's actual alias (`multilingual` for upstream Laya versus
`laya-multilingual` in the internal deployment). Internal plain HTTP endpoints
require a trusted TLS front end; an internal hostname is not a local exception.
An arbitrary open-source model is not automatically System One compatible:
non-compatible protocols need a `DecisionProvider` implementation.

## Application behavior

`off`: no decision request or extra metadata. `shadow`: observe only. `on`: apply
confident tier upgrades and bounded read-capability advice. These modes are
independent of `STAGED_RESPONSE_MODE`; existing model preferences and safety
floors remain authoritative. No downgrade or write permission comes from the
decision service. Question vocabulary and policy live in `decisions/routing.py`.

Low confidence, timeout, oversized input, invalid response and denied consent
produce observable abstention/fallback. The normal agent handles the request;
the service never forwards it to another decision vendor. No retries are made.
Transport accepts only a complete matching set of typed answers. Redacted
`decision_routing` metadata on the stored assistant message/done event records
provider, actual model, status, reason, token usage and elapsed time. No raw state
or response is stored in that metadata. Compare task success, errors and latency
on the same Chinese evaluation set; confidence is not measured correctness.

Configuration switches change the opaque consent version when the remote
recipient/address changes. Key rotation does not invalidate consent. Setting a
new URL alone never authorizes sharing. Setting mode=off is the rollback.
Removing a remote recipient also restores the base consent revision; users who
accepted the extended policy may be asked to confirm the current disclosure again.

References: [Jev API](https://docs.typesafe.ai/api),
[Laya HTTP adapter](https://github.com/NandhaKishorM/laya/blob/main/laya/serve.py).
