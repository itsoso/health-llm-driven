# Changelog

## [Unreleased] - 2026-03-29

### Security
- Fixed unauthenticated health analysis endpoints
- Fixed performance endpoint admin check
- Added security response headers (X-Frame-Options, HSTS, etc.)
- Redis-based rate limiting with global default

### Fixed
- Celery notification tasks broken for 2 months (wrong Python, missing models, wrong field names)
- Diet auto-save hallucination detection
- OpenClaw stream timeout (120s -> 900s)
- Garmin 429 rate limiting intelligence (distinguish Cloudflare vs account lock)
- Blood pressure API record_time bug

### Added
- System health score script (project's val_bpb)
- Deploy auto-backup + verification + rollback
- Medical report AI suggestions + trend charts + comparison page
- Onboarding Step 4 (explore guide)
- Dashboard quick actions + non-Garmin user adaptation
- AI assistant "today's insights" cards
- Hover timestamps on AI messages
- 404 not-found page
- Empty states for weight/water pages
- Register form validation
- Invite code auto-approve

### Improved
- Test pass rate: 85% -> 100% (584/584)
- Settings page split: 2697 -> 524 lines
- 6 more pages split (10518 -> 2678 lines, 32 components)
- OpenClaw response UX (progress hints, friendly errors)
- Mini-program unified to OpenClaw mode
