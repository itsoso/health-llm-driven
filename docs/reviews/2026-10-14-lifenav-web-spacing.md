# LifeNav Web spacing correction

## Scope and cause

The fixed global Navigation already renders a 64px spacer. LifeNav added another 80px desktop / 72px mobile top margin. Its centered 1250px content cap and the 1550px breakpoint also added excess horizontal whitespace.

This CSS-only change retains the navigation spacer and sticky offsets, reduces the workspace gutter to 12px desktop / 8px mobile, lets content use the available width, and reduces header, intro, calendar, focus card and sidebar spacing. API, authentication, drafts and native Mobile code are unchanged.

## Verification

- Baseline: origin/main fcc323c3159f94bc48b95cc48f240ad2aedf96b2; CI 38578258596 succeeded.
- LifeNav regression tests: 37 passed.
- CI=true frontend test suite: 97 files passed, 548 tests passed, 1 skipped.
- Fresh npm ci and production build: passed. Initial build rejected a linked node_modules directory; replaced it with a normal lockfile install, preserving the dependency guard.
- Frontend lint: 0 errors, 39 existing warnings in unchanged files.
- Real Workspace component and CSS in local Vite preview; synthetic data, authentication and navigation shell. No production writes.
- Browser widths 1920, 1366, 390 and 320: no document horizontal overflow. Weekly view switching verified at 1366.
- At 1920px, workspace top 144 -> 76, date panel top 314.9 -> 201.5; content inset from sidebar 253 -> 24px.
- Screenshots: /Users/liqiuhua/.codex/visualizations/2026/10/14/lifenav-web-spacing/{before-1920,after-1920,after-390}.png.

## Delivery boundary

Production Web publication remains blocked by the repository's no-backup policy: docs/governance/deploy.md and deploy.sh reject --publish-frontend and --rebuild-deployed-frontend before external side effects. This patch does not bypass the frozen publisher or alter release security. Local preview and build are not production deployment. No Mobile OTA is needed for this Web-only CSS change.

## Second pass: compact first screen

Removed the introductory slogan, repeated English section labels and sidebar tagline. Moved the Health recording reminder to the footer. Replaced the large focus banner with title, optional completion criterion, one completion count and the existing task locator. Title and criterion each display at most two lines in the summary; full authored text remains in the existing editor.

The week number and month share a line. Desktop weekday/date pairs are horizontal; narrow screens stack them to keep the seven dates legible. The mobile toolbar uses a title/status row and one action row; history, reload, save and week controls have 44px minimum height. The visible today label is shorter while its accessible name remains unchanged.

Verification on 2026-10-14:

- 97 frontend test files passed: 548 tests passed, 1 skipped; production build passed; lint has 0 errors and 39 existing warnings.
- Browser widths 320, 390, 1024, 1366 and 1920: no document horizontal overflow.
- Same synthetic two-task fixture at 1920: focus banner 199.59 -> 87.20px; task section approximately 643.59 -> 441.20px from the top.
- Main-task action focuses the matching editor. Long title/criterion stay bounded in the summary and retain full text in the editor. No save request was made.
- Local preview screenshots: compact-1920.png, compact-390.png and compact-320.png under the screenshot directory above. These are synthetic local previews, not production acceptance.
- Synced unrelated backend/Mobile changes through d5862b45faf8d5aee0e97bbd14bbd98c257d2f38; their diff does not change the tested frontend tree.
- Production Web publisher remains frozen in deploy.sh and the deployment governance document. No deployment or native Mobile OTA claimed.

Second-pass delivery status: upstream main CI 38586581374 for d5862b45faf8d5aee0e97bbd14bbd98c257d2f38 completed with failure in backend-test-balanced-08 and backend-test-balanced-12; backend aggregate/release gates consequently failed. The second-pass UI commit is local only and was not part of that run. Per AGENTS.md section 7, no push was attempted against the non-green main. Web publication remains separately frozen. Resume by verifying the latest main and its CI, integrating these three task files, then using only an adapted canonical Web publisher.
