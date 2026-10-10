# Isolated Neo WeChat bridge deployment

Status: implementation candidate, not deployed. The only admitted first-install
terminal is `INSTALLED_DORMANT`. It does not establish OAuth, bind WeChat, post to
Slack, expose an nginx route, or prove a closed-Mac acceptance test.

## Admission and release ownership

Use the existing canonical bootstrap procedure in [deployment governance](../governance/deploy.md).
The publisher must be the actual current `main` SHA with full CI, and its fixed
diff must receive independent G4 GO. This feature cannot use `backend-v1` or a
documentation-descendant exemption. Coordinate with the release owner before
starting; a previous lock observation is not a reservation.

The installed `/usr/local/lib/reva-release/trusted_release_server.py` must already
match this candidate's reviewed executor bytes. Install/rotate it through the
existing canonical bootstrap workflow, including all prior-operation gates. The
bridge installer cannot change release keys, policies, or the executor itself.
This prerequisite makes persistent bridge history visible to the actual launcher,
not merely to a newer source checkout. Ordinary `deploy.sh` history checks also
inspect bridge history when no vision-model history exists.

PR [#252](https://github.com/itsoso/health-llm-driven/pull/252), inspected at head
`55c30e2845803b0142ee88dd33ccf95a9e3dcd56`, proposes a publisher freeze after
same-UID bootstrap attacks. It was open during implementation, and its proposed
policy is not represented here as merged policy. Its concrete trust findings must
be considered in G4 and conflict resolution before merging this entry.

PR252 is not a code dependency and supplies no replacement launcher. Its actual
`deploy.sh` exits 78 before legacy writers. The concrete concern is execution before
local guards (Git replacement/filter behavior, import shadows, and shell/Python
startup hooks). An inner bridge guard cannot establish initial provenance. If the
existing external verification of canonical root-owned staging and interpreter
can be demonstrated, the currently merged governed bootstrap remains a possible
path. If not, a separate bounded release-trust repair needs its own G2/G4 and
rollout evidence. If PR252 merges first, its freeze must be reconciled through the
approved external-launcher feature; this bridge adds no exemption.

The original release owner supplied fresh read-only evidence at 08:57:32 UTC on
2026-10-10 through task `01a120c7-1ba0-75c3-9487-447bd5bfa28f` (`优化 README`).
Production was clean at `346035f78b362804df06e1524099f87294286ef6`; backend,
frontend, worker and beat were active. Candidate `637520e25` still had the trusted
terminal `NEEDS_OPERATOR`, and workflow `38031474956` remained failed. The
launcher inode was present with no holder observed in that instantaneous kernel
snapshot, and the business lease was absent. Runtime remained paused with
generation 8 and acknowledged generation 7. These observations do not authorize
release: original failed-attempt markers remain preserved, and the original
release owner plus authenticated administrator retain closure responsibility.
This bridge must not retry, clear locks, or delete that history. Fresh admission
and release ownership must be established before any bridge operation or executor
rotation; this task performed no production writes.

Before executing any repository bytes as root, the authorized operator must use
the existing trusted bootstrap to establish the canonical origin, exact reviewed
revision and actual file bytes, secure ancestors, interpreter ownership, and
root-owned non-writable staging. Self-checks executed by unverified code cannot
establish that initial trust. Start the already-verified canonical entry with an
empty environment, so shell startup hooks cannot run before its guards:

```text
/usr/bin/env -i PATH=/usr/bin:/bin /bin/bash \
  /var/lib/reva-release/bootstrap/<publisher-sha>/source/deploy.sh --neo-wechat \
  --publisher-sha <publisher-sha> --production-sha <actual-deployed-sha> \
  --operation-id <fresh-32-hex-operation-id>
```

This is the canonical `deploy.sh` entry, not a raw SSH/script-upload alternative.
The first call is an inspection only. Its sanitized receipt binds source files,
exact CI, deployed revision, service process identities and protected-file change
metadata. It opens no Health secrets. Repeating that same canonical command with
the exact returned `--evidence-sha256` admits only the dormant transaction. Changed
evidence, existing bridge objects, any pending release history, an occupied lock,
or an old installed executor fails closed.

Local `--package-only --publisher-sha <sha>` prints an explicitly untrusted
manifest for review. The supplied revision is only a label in this mode; it is not
validated against Git and cannot authorize installation. It never contacts or
inspects production. Unknown flags and `--apply`, `--install`, `--activate`, and
`--rollback` are not alternate admission paths.

## Dormant transaction

The installer holds the original launcher flock and atomically claims the
existing four-file business lease. It fsyncs an operation intent first, then
rechecks source and production after acquiring the lease. No business services
are stopped or restarted.

It creates only the dedicated no-login `neo-wechat` account, its private primary
group and `neo-wechat-proxy` group; an existing account or path is rejected.
The account has no Health supplementary groups. It creates a separate Python 3.12
venv under `/opt/neo-wechat/releases/<publisher-sha>`, using the committed complete
hash lock, binary wheels only, no dependency resolution or source builds. Package
installation runs as the dedicated unprivileged account in a limited transient
systemd unit. The build namespace hides Health, release state, home directories,
caches, logs, backups and optional data mounts, and exposes only its candidate
directory for writes. Global pip configuration is masked and configuration is
explicitly disabled. No shared environment or application credentials are used.

Before installing the units, the runtime is made root-owned and read-only to the
service account, each regular file and directory is fsynced, and a sandboxed
import/QR-asset check must pass without starting the application. The resulting
runtime digest is bound to the receipt. The nginx fragment is parked in that
release directory; it is not included or reloaded. Both service and socket units
are verified and daemon-reloaded, but must remain `inactive` and `static` with no
enablement section. No Unix socket path is opened by the dormant installer.
Both config and state directories remain empty. The receipt includes the dedicated
proxy group ID needed by the later nonsecret configuration.

Runtime containment: systemd 249-compatible directives, CPU 25%, memory 256 MiB,
32 tasks, 256 descriptors, no privilege acquisition, no capabilities, private
temporary files/devices, read-only filesystem with only bridge state writable.
The service must inherit exactly one pre-opened listening Unix socket from systemd
at `/run/neo-wechat/bridge.sock`; the socket unit owns its path lifecycle, independent
of service restarts. The service's seccomp policy denies both `bind` and `listen`,
including unbound TCP `listen()` autobind, and the three io_uring entry syscalls
that could otherwise provide asynchronous bind/listen operations on newer kernels.
A strictly validated inherited socket
adapter avoids asyncio's redundant `listen()` call without relaxing kernel policy.
`SocketBindDeny=any` alone is not a safety boundary: native systemd 249 CI demonstrated
an IP listener escaping it. The revised boundary still requires real passing CI.
The socket is owner-private with group access for only the dedicated proxy group.
Health paths are inaccessible. The runtime receives three
separate credentials through `LoadCredential`, never through an EnvironmentFile.
Actual Linux `systemd-analyze verify` and sandbox behavior are deployment gates;
Mac unit tests do not establish host compatibility.

Systemd credentials can be service-owned with private permission bits or root-owned
with an exact named-service-UID POSIX ACL, depending on backing filesystem support.
The ACL mask appears in group mode bits and is not itself an owning-group grant.
Credential acceptance must verify the exact file and directory owner/ACL, deny
extra principals, and require the actual credential mount to be read-only. A
mode-only `0440` exception is not sufficient. The application reader and native
probe must share the same validator so a probe success covers the real read path.

## Interrupted install and rollback

An unknown command or persistence outcome is not retried. The original operation,
source, receipt and any remaining lease are retained. Missing, extra, malformed or
unbound history blocks later canonical launches/rotation even after `/run` is
cleared by reboot. A failure after lease release but before completed receipt
still blocks via durable history. Do not delete the audit or lease or change the
operation ID to retry.

There is deliberately no automatic rollback or activation action. A failed
first-install may have created an account, partially installed files, or loaded
an inactive unit. Recovery needs a separately reviewed exact-operation transaction
that inventories the original state and removes only proven bridge-owned objects;
it must preserve evidence and must not delete owner data or affect Health. A
successful dormant installation requires a separately reviewed removal flow if
the user later cancels it. `INSTALLED_DORMANT` must never be relabelled as active
or a successful WeChat/Slack/OAuth acceptance result.

## Human-owned activation handoff

The installer creates no configuration or secret values. The owner must use an
approved secret-entry UI, not chat, shell arguments, source files or logs. No
such UI is supplied by this deployment mode. Before activation the owner supplies
the encryption key, admin-password hash and channel-scoped Slack webhook to
root-managed files under `/etc/neo-wechat`; the unit reads protected copies via
`LoadCredential`. Nonsecret `config.json` must pin the owner, public HTTPS origin,
registered OAuth public client and exact callback, Health owner binding, and proxy
group ID. Config must be root-owned, mode 0640, group `neo-wechat`; secret originals
must be root-owned 0600. A reviewed activation transaction must verify all of this,
nginx worker membership in only the dedicated proxy group, and the exact HTTPS
locations before starting both the socket and service and publishing the route.
Explicitly start the service so collection does not wait for the first MCP request.
Stop/unpublish operations must stop both units; preserve encrypted state and keys.

G2 continuation: the proposed owner-operated SSH terminal with hidden `/dev/tty`
prompts has been presented as a surface choice; acceptance remains pending. The
new offline provisioning helper validates exact nonsecret configuration, supplied
key shape, admin-password confirmation and the finn workspace/channel confirmation,
and prepares an in-memory credential bundle with a fresh password salt. It has no
CLI, filesystem writer, environment secret reader or network. It is not a secret
entry surface or authorization to create secrets. URL shape cannot establish the
webhook's actual channel; owner selection and real sender acceptance remain required.

Bounded lifecycle decisions retained for the next implementation stage: only the
exact bridge nginx include/proxy group/reload may change; deactivation/removal
preserves encrypted data, keys and audit by default; no account/group purge is
authorized; recovery reconciles the original operation and never reinstalls,
redownloads, changes operation ID or recreates a lost lease. The old dormant
receipt remains immutable. Local transport-independent provisioning transactions,
injected-host activation/stop implementations and conservative recovery readback
can be prepared and tested before the input-surface decision. This does not permit
production execution or choose an owner-input adapter. The actual input adapter
awaits the owner choice; all lifecycle dispatch and history-reader rollout still
require exact fixed-code review and existing release gates. No general cleanup of
partially installed objects or recreation of missing leases is authorized.

`neo_wechat_provision_transaction.py` is the internal, transport-independent
one-shot writer. It consumes the validated memory bundle through trusted directory
descriptors and a required canonical-lock/path guard; defaults require root-owned
files. Its separate `provision-v1` metadata namespace is not part of the dormant
installer's immutable audit. No current CLI or production entry invokes it, and
no current history reader admits its records. The future caller must retain its
original lease on any uncertain outcome; merely finding `completed.json` does not
prove fsync/final-guard success or permit activation. Tests use synthetic temporary
directories only. This internal implementation does not select the owner-input UI.

`neo_wechat_runtime_lifecycle.py` implements bounded start/stop sequencing against
an injected trusted host. It records intent before each effect, starts the socket
and then the service explicitly, publishes only the receipt-bound include, validates
nginx before reload, and checks read-only readiness. Stop requests both fixed units
together, then removes only that exact include and validates/reloads. Every step
rechecks the original lease, bound configuration/unit/proxy identities and preserved
Health services, keys, state, audit and accounts/groups. An exception after the
claim begins retains an uncertain operation, with no retry or compensation.

`neo_wechat_lifecycle_history.py` validates a separate versioned runtime history
and provisioning history. Its recovery inspection is read-only and returns no
executable actions. Complete ordered records, authenticated original provenance,
the original live lease, exact current readback, and independently authenticated
fsync/final-guard acknowledgement are all required even to classify an original
completion. A visible completion file or matching hashes alone are insufficient.

`neo_wechat_host.py` now contains descriptor-relative file operations and an exact
command allowlist with a clean environment, bounded output and deadlines. Its
only admission factory requires a temporary filesystem and a recording runner;
production admission is deliberately unavailable. A private Python object is not
canonical provenance, current-main CI or G4 approval. The fixed nginx strategy
requires a previously reviewed, pinned server file with exactly one
`include /etc/nginx/neo-wechat/*.conf;` slot and a dedicated directory; it does not
infer or rewrite production topology. Only `locations.conf` can be published or
removed, and removal requires exact prior inode ownership as well as content.
No current CLI invokes this adapter or starts a production lifecycle.

One concrete stop limitation remains: after stopping both units but before nginx
unpublish/reload, the public discovery request can return 502. That response is
not proof of nginx's loaded configuration. The adapter retains an uncertain
operation instead of treating cached HTTP success or a caller boolean as fresh
proof. A reviewed loaded-generation proof or separately versioned stop protocol
is needed before production stop can be admitted. Synthetic recording-runner
success exercises sequencing and filesystem effects only; the realistic 502
case must remain a blocking regression.

`neo_wechat_installed_history.py` reads bounded metadata histories using pinned
nofollow descriptors. It rejects unknown files, links, changed identities and
malformed ordered records, and never reads credential or lease-token contents.
Its diagnostics grant no actions. The actual installed release server uses an
even smaller fail-closed rule: any `neo-wechat-lifecycle` namespace blocks new
release admission until an independently reviewed closure protocol is available.
Backend/frontend, OTA, retained-build claims and bootstrap install/rotation all
reach this gate before consuming new work. A completion file or caller-created
acknowledgement cannot lift the block. Existing exact credential revocation and
receipt-bound completion paths retain their established scope.

`neo_wechat_boot.py` implements exact two-unit startup-link creation and removal
with durable intents, fsync and ownership readback. Only a temporary-directory
test permission can enable links; production startup remains denied. The current
templates remain static and this helper is not called by the runtime transaction.
A real boot guard must establish confirmed closure before any restart activation;
`Restart=on-failure` alone is not evidence for host-reboot behavior. No production
systemd/nginx operation or closed-Mac acceptance is established by synthetic tests.
The separate owner-input surface decision remains pending.

`neo_wechat_linux_probe.py` adds an ephemeral-runner-only synthetic systemd test
using retained directives from the real unit template. It exercises effective
filesystem, credential, socket, cgroup and privilege boundaries with positive
controls. Paths/identity are synthetic and PrivateNetwork is added; it does not
prove production egress, proxy access or systemd249 unless that version is actually
observed. Unsupported hosts fail required mode. It must never run on Health.

For Slack, the owner creates/authorizes an app with **Incoming Webhooks** enabled
and the `incoming-webhook` OAuth scope, selecting private channel `C0C89QBQLBB` in
workspace `T6TNPEFLY`. No `chat:write`, history, or user impersonation scope is
needed by this transport. Do not create the app or transfer its webhook value on
the owner's behalf. A webhook posts only the fixed generic new-message signal;
it must never receive WeChat text, health data or message IDs. The actual webhook
sender must be verified in a synthetic acceptance test, then the parent task must
update its existing event filter. The prior owner-authored test is not evidence
that a webhook-authored message triggers the current Neo conversation.

The owner then personally scans the new QR, completes the new remote MCP plugin
connection and OAuth consent, and separately consents to owner-only Health reads.
The grant may last 3650 days; access tokens remain short-lived and refresh tokens
rotate. No old Health or Site grant is expanded or exported. Finally verify
closed-Mac delivery, service restart/cursor recovery, generic Slack wakeup, pinned
owner replies, duplicate/uncertain sends, token replay and revocation. Record each
real result separately; unresolved acceptance keeps G6 open.
