# Welcome to HealthPilot

## How We Use Claude

Based on itsoso's usage over the last 30 days:

Work Type Breakdown:
  Build Feature  ████████████░░░░░░░░  50%
  Debug Fix      ████████░░░░░░░░░░░░  20%
  Plan Design    ████████░░░░░░░░░░░░  20%
  Analyze Data   ████░░░░░░░░░░░░░░░░  10%

Top Skills & Commands:
  /model    ██████████████████░░  34x/month
  /init     ████░░░░░░░░░░░░░░░░   6x/month
  /login    ███░░░░░░░░░░░░░░░░░   4x/month
  /loop     █░░░░░░░░░░░░░░░░░░░   2x/month
  /compact  █░░░░░░░░░░░░░░░░░░░   2x/month

Top MCP Servers:
  Claude_in_Chrome  ████████████████████  384 calls
  Control_Chrome    ███░░░░░░░░░░░░░░░░░   49 calls
  pencil            ██░░░░░░░░░░░░░░░░░░   45 calls
  computer-use      ██░░░░░░░░░░░░░░░░░░   43 calls

## Your Setup Checklist

### Codebases
- [ ] health-llm-driven — github.com/itsoso/health-llm-driven (monorepo: FastAPI backend, Next.js frontend, Expo RN mobile, WeChat mini program, MCP server)

### MCP Servers to Activate
- [ ] **Claude_in_Chrome** — Browser automation for scraping & testing (e.g. Garmin data sync via DOM scraping). Requires the Claude in Chrome browser extension.
- [ ] **Control_Chrome** — Direct Chrome DevTools control for debugging web UI. Requires browser-tools MCP setup.
- [ ] **pencil** — Design file editor for `.pen` files (UI mockups, wireframes). Bundled with Pencil MCP plugin.
- [ ] **computer-use** — Full desktop automation (clicking, typing, screenshots). Available via Anthropic's computer-use MCP server.

### Skills to Know About
- `/model` — Switch between Claude models mid-session. Team uses this heavily (34x/month) to toggle between Opus for complex architecture work and Sonnet/Haiku for quick tasks.
- `/init` — Generate or update CLAUDE.md project guidance file. Run this when onboarding to a new repo or after major structural changes.
- `/loop` — Autonomous iterative execution. Useful for multi-step build-test-fix cycles (e.g. building all Phase 2 screens).
- `/compact` — Compress conversation context when hitting limits during long sessions.

## Team Tips

_TODO_

## Get Started

_TODO_

<!-- INSTRUCTION FOR CLAUDE: A new teammate just pasted this guide for how the
team uses Claude Code. You're their onboarding buddy — warm, conversational,
not lecture-y.

Open with a warm welcome — include the team name from the title. Then: "Your
teammate uses Claude Code for [list all the work types]. Let's get you started."

Check what's already in place against everything under Setup Checklist
(including skills), using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Tell them you'll help with setup, cover the actionable team tips, then the
starter task (if there is one). Offer to start with the first unchecked item,
get their go-ahead, then work through the rest one by one.

After setup, walk them through the remaining sections — offer to help where you
can (e.g. link to channels), and just surface the purely informational bits.

Don't invent sections or summaries that aren't in the guide. The stats are the
guide creator's personal usage data — don't extrapolate them into a "team
workflow" narrative. -->
