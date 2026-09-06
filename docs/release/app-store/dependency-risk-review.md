# App Store Production Dependency Risk Review

Review date: 2026-09-06

## Decision

The 2026-09-06 Mobile production and package-lock-only npm audits report 20
findings: 15 moderate and five high transitive package paths. The high paths
resolve to the two `image-size` denial-of-service advisories documented in
`mobile/npm-audit-policy.json`. The policy gate passes with exceptions expiring
on 2026-09-15; the local malicious-input regression passes 2/2. This is a
conditional dependency-policy pass, not a zero-vulnerability result. Moderate
findings remain for XML parsing, URI decoding and `qs` and must be assessed
during the next dependency remediation pass.

The full-tree audit and backend hashed production lock audit were not rerun in
this 2026-09-06 review. The backend zero-vulnerability result described below is
historical 2026-08-28 evidence and must be refreshed before release.

The newly disclosed `brace-expansion` advisories are remediated across every locked
major line used by Mobile (`1.1.18`, `2.1.4`, and `5.0.9`). PostCSS is pinned to the
patched `8.5.23`. The 2026-08-06 `js-yaml` omap advisory is remediated on both
locked major lines (`3.15.1` and `4.3.1`). Backend remediation pins
`aiohttp==3.14.3`, `cryptography==50.0.0`, and `h2==4.4.1` for the duplicate Host
header request-smuggling advisory.

ChromaDB `0.6.3` was removed from the production requirements and lock after
`CVE-2026-45830`, `CVE-2026-45831`, and critical code-injection
`CVE-2026-45833` were published without a patched ChromaDB release. Production
already routes knowledge retrieval through reviewed System KB and keeps the legacy
Chroma runtime disabled. The deploy dependency synchronizer now removes stale
`chromadb`/`chroma-hnswlib` installations before verifying the lock, and the lock
verifier rejects either residual package. A matching dependency marker is deleted
and durably synced before repair, so a failed uninstall cannot leave stale reuse
evidence. Rollback installs the target lock while services are stopped, removes
both forbidden packages, and verifies the remaining target-lock contract with the
immutable staged verifier before any service starts.

The two `image-size` exceptions remain active. The historical backend remediation
received independent G4b approval. A historical green CI run does not replace a
fresh dependency check, and App Review still requires exact-build acceptance.

## Controls

- All Agent Markdown rendering uses the shared `mobile/utils/safeMarkdown.ts` parser.
- Automatic linkification, typographer transformations and raw HTML parsing are disabled.
- Render input is capped at 50,000 characters before parsing.
- Direct Markdown render sites pass both the shared parser and the bounded source string.
- Production overrides pin patched XML, PostCSS, UUID, `brace-expansion`, and
  both locked `js-yaml` major lines.
- Both full-tree `npm audit` and `npm audit --omit=dev` are part of the release evidence.
- Mobile CI runs `scripts/npm-audit-gate.mjs` against the bounded-exception
  `mobile/npm-audit-policy.json`. The gate resolves every high/critical transitive
  path to its advisory leaf and fails closed on malformed, unresolved, or new
  advisories.
- Backend CI audits the hashed `backend/requirements.lock`; the lock is generated
  for the CI Python 3.12 Linux x86_64 target and must install with `--require-hashes`.
- Backend deployment removes forbidden stale packages before writing its
  lock-addressed dependency marker; verification fails if either `chromadb` or
  `chroma-hnswlib` remains installed, and repair failure leaves no reusable marker.
- Do not apply `npm audit fix --force`; dependency upgrades must stay within the
  Expo compatibility matrix and pass Mobile regression.

## Residual Risk

Dependency audit is a point-in-time signal, not proof that future advisories cannot
appear. Markdown and build-tool inputs therefore retain the defense-in-depth
controls above. Before each App Store candidate:

1. Re-run full and production-only npm audits plus
   `node ../scripts/npm-audit-gate.mjs --policy npm-audit-policy.json` from `mobile/`.
2. Re-run `python -m pip_audit -r requirements.lock --require-hashes --progress-spinner=off`
   from `backend/`.
3. Re-check the React Native/Expo build chain and shared Markdown parser for a new
   compatible patched release when an advisory appears.
4. Block the release for any unreviewed high/critical finding, a bypass of the
   shared Markdown parser, or a required forced major upgrade.

Owner: Mobile release owner.
