# Mobile LifeNav entry from Agent

The native LifeNav workspace already supports daily tasks, weekly planning,
time slots, reviews and local task search. Its existing entry was below the
Today content, making it hard to discover from the primary Agent screen.

The Agent's empty conversation now shows a compact 人生导航 entry with
今日安排 · 周计划 · 复盘. More actions provides the same destination during
an ongoing conversation. Both open the existing `/life-navigation` route and
preserve the chat; neither sends a prompt nor creates or saves planning data.
The home entry hides while the keyboard is visible and returns on dismissal.
Existing screen authentication, owner isolation and explicit save remain unchanged.

Verification:

- Both new navigation tests failed before implementation because the entry was absent.
- CI-mode Chat and native LifeNav regression: 109 tests passed across four suites.
- Tests cover both entry points, menu dismissal, existing messages, no send/new-chat
  side effects, and keyboard hide/restore.
- Mobile TypeScript and targeted ESLint passed.
- Regenerated the mobile navigation graph; System Map drift gate passed.
- No simulator/device UI acceptance in this task; no simulator was running.

Release boundary: the latest verified production iOS OTA is `b5110ff14`, runtime
1.3.5, publish run 38576013830 on 2026-10-14 22:00 Asia/Taipei. It includes the
native workspace but not these new Agent entries. Provider publication does not
prove a particular phone loaded that update. Per the user's instruction, this
task integrates into main; the other computer owns backend and OTA publication.
