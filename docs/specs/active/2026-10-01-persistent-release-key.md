# Feature Spec: Persistent release identity

> Status: implemented locally; production migration pending
> Updated: 2026-10-01
> Related code: `scripts/bootstrap_trusted_release.py`, `scripts/trusted_release_server.py`

## Decision and admission

Remove the mandatory eight-hour credential renewal and allow the current dedicated
cloud release key to be reused when an operator authorizes the next reviewed SHA.
The user explicitly requested this infrastructure maintenance change to reduce
repeated GitHub Secret edits. It does not change Health OS product objects,
health-data ownership, medical advice, application APIs, or database schemas.

## Contract

- `install` and `rotate` default `--expires-at` to integer zero: valid until revoked.
- Positive deadlines retain expiration semantics; malformed, missing policy fields,
  negative values, booleans and expired positive deadlines remain rejected.
- The server still binds one exact SHA and executor digest. RPC cannot select a
  different revision or an arbitrary shell command. Canonical source, exact CI,
  one-shot consumption, original locks and unresolved-operation gates remain.
- Persistent rotation may reuse only the current cloud public key. Replaced cloud
  keys and all historical loopback keys cannot be reused. Each version creates a
  fresh loopback key, restricted to localhost; it also has no automatic deadline
  in persistent mode and must be revoked and destroyed before retirement.
- Retirement intent optionally adds `cloud_key_reused: true`. Existing records
  remain byte-for-byte intact. An active historical cloud key is accepted only
  with a continuous completed reuse chain to the canonical current installation
  and one exact restricted SSH authorization. Current retirement still requires
  both authorizations absent and the old loopback private key removed.

## Operator flow and migration

Reviewed current SHA and CI → retire the prior terminal operation through the
existing operator process → bootstrap rotate with the current cloud public key
and default deadline → readiness check → authorized release → receipt/readback.
GitHub Secret need not change when its private key already matches that public key.
Existing expired installations are not revived by editing policy files: migration
requires a newly reviewed canonical SHA and all existing rotation prerequisites.

This change does not implement automatic version authorization, an OIDC issuer,
production deployment, credential distribution, or an unreviewed migration path.
The initial implementation was source-only. The user subsequently requested deployment;
production migration requires separate release evidence in the dossier.

## Security boundary and acceptance

The accepted tradeoff is absence of automatic credential expiration. Suspected
compromise requires operator revocation and replacement; deleting authorized_keys
does not terminate established sessions. Private keys must never enter logs or Git.

Acceptance covers default CLI behavior, persistent install/revoke, old finite
deadlines, consecutive same-key version transitions, unchanged historical receipts,
wrong-SHA rejection, non-reuse of consumed SHAs, replaced/loopback key rejection,
exact SSH restrictions, audit tampering and partial-rotation fail-closed behavior.
Unit and lifecycle tests use temporary synthetic fixtures. Real Linux SSH/systemd
and PostgreSQL gates remain separate from local macOS verification and are required
where applicable before release.
