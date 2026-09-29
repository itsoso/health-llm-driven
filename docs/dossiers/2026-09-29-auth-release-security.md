# Auth release security remediation

| Field | Value |
| --- | --- |
| status | shipping |
| current_stage | S6 exact-revision CI and combined release readiness |
| Primary controller | health-harness-orchestrator |
| Overlay | safety-gate |
| Source baseline | fc9328b1b824427c6fcf2c18607461410077530c |

## G1/G2 Scope

裁决: PASS

The user authorized phone/SMS self-registration, phone/email password login,
Telegram administrator notifications, publication and deployment, then requested
repair of the release security blockers. Authentication behavior and notification
privacy remain defined in the self-registration spec. This repair closes the
fixed historical native-only upload and replaces the mutable local OTA publisher
with a fresh hosted, exact-revision transaction. No health-data or user-consent
boundaries change. Unrelated dirty shared-checkout work is preserved.

## G3 verification

The auth baseline CI run 36573092545 completed successfully at the exact source
baseline. Prior auth/OTP/notification, PostgreSQL and Mobile verification is
recorded in the feature spec; a configured Telegram channel test is not evidence
of a real registration notification.

The new native closure and OTA transaction/publisher tests cover hostile inputs,
credential isolation, ambiguous vendor outcomes, replay, durable receipts, original
lock identity, cross-filesystem archive handling and multipart manifest parsing.
A read-only live Expo response parsed successfully (runtime 1.3.4); it is not the
new OTA and proves no new deployment. Local checks: final combined security suite 245 passed; 302 broader security tests before the final recovery refinements;
15 transaction tests including real flock exclusion and simulated tmpfs loss;
20 hosted workflow tests; 79 auth and user-flow integration tests; 3 installed
release-tool compatibility tests. System Map, secret scan and skill governance
checks passed. Full release invariants, fixed-commit review and exact-revision
CI remain required.

## G4 and publication state

裁决: GO (release mechanism only)

Independent review required separate historical/current production evidence for
the native closure, both launcher/build locks for OTA, same-filesystem lease
retirement, and the actual Expo multipart response. Corrections are implemented;
independent G4 GO binds implementation commit
`4458077c5dc16c56fe0a7528fed2152ec1565162` on main `40d874f4d`. No security bypass, legacy-marker deletion, old-key
renewal or backend success fabrication is permitted. Production migration,
backend deployment, new OTA and end-to-end registration notification remain
unverified until their real receipts exist.


## Coordinated production admission

The separately authorized registration/ECS security task has confirmed missing
shared authentication rate-limit wiring and is repairing public-application
host boundaries. This release-mechanism GO does not certify those boundaries.
Do not deploy the open-registration configuration before that task's reviewed
hardening reaches the combined release revision. Keep the existing invitation
admission until both security conditions and actual production validation pass.
Source/CI publication of these release repairs may proceed independently; no
old-key renewal, local publisher fallback or concurrent production switch.
