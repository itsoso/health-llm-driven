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
