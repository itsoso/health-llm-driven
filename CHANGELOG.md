# Changelog

## [Unreleased] - 2026-03-31

### Security (3/30-31)
- users.py endpoints require admin auth
- diet.py delete requires ownership verification
- family_health.py compare route ordering fix

### Fixed (3/30-31)
- Garmin 429 root cause: all Garmin() instances now use curl_cffi Chrome TLS fingerprint
- Garmin session lock bypass: valid session skips lock check in both scheduler and service
- Garmin session timezone-aware datetime comparison fixes
- Garmin auto-renew: 30s delay between users to prevent rate limiting
- data-health API: None datetime + sent_at→created_at query fixes
- Navigation bar flickering: Nginx Origin header for Next.js Server Actions
- HRV data gap: fallback to /hrv-service/hrv/{date} API

### Added (3/30-31)
- Genetic data management: structured input + TXT upload (42 health SNPs) + AI cross-analysis
- Daily health briefing with AI narrative (writes to OpenClaw conversation at 07:35)
- Weekly health report (writes to conversation every Monday 09:05)
- Quick record: natural language input ("午餐牛肉面" / "喝水500" / "吃了维生素D")
- Garmin session auto-renew every 12 hours (curl_cffi fallback)
- Data health dashboard API (Garmin/HRV/diet/water/notifications/genetic status)
- OpenClaw health context enriched: goals, allergies, memories, energy balance, fitness level, genetic traits
- Smart quick questions: context-aware scoring based on goals, stress, illness
- Food photo auto-save in OpenClaw stream
- Skill execution verification rules in health-record
- genetic-analysis Skill with cross-Skill integration (nutrition/supplement advisors)
- 10 page titles for browser tabs
- Relative time utility + conversation history preview
- deploy.sh auto-sync to kuaishou GitLab

### Improved (3/30-31)
- Tests: 662→680+ (quick record, genetic data, openclaw, family health, system health score)
- 20-round autonomous optimization (security, UX, tests, infrastructure)
- Garmin sync time changed to 09:02 Beijing time
- Only user_id=3 Garmin sync enabled (others disabled to prevent rate limiting)

---

## [Previous] - 2026-03-29

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
