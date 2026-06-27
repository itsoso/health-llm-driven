# Handoff: Reva (复元) Mobile App — UI

> 体检之后的 90 天主动健康管理 Agent。A post‑checkup, 90‑day proactive
> health‑management agent. Wedge: cardiometabolic risk + exercise recovery.

This package documents the **optimized Reva mobile UI** so it can be continued
and implemented in a real codebase — including with **Claude Code**. A developer
who was not in the original design conversation should be able to rebuild every
screen from this README alone.

---

## 1. About the design files

The files in this bundle are **design references created in HTML/JSX** — a
working prototype showing the intended look, copy, and behavior. They are **not
production code to ship as‑is**. The task is to **recreate this UI in the target
codebase's environment** (React Native, SwiftUI, Flutter, a React web app,
etc.) using that project's established patterns, navigation, and data layer. If
no app codebase exists yet, pick the framework that best fits the product (a
native or RN mobile app is the obvious target for this design) and implement
there.

What's in the bundle:

| File | Role |
|---|---|
| `RevaApp.jsx` | **The real UI source.** All screens + components in one React file (plain React 18, inline styles). This is what you port. |
| `Reva Mobile.dc.html` | A thin wrapper that mounts `RevaApp` for previewing. Ignore its `support.js`/`x-import` plumbing — that's the prototype host, not part of the app. |
| `colors_and_type.css` | **Design tokens** (CSS custom properties) + semantic type classes. The source of truth for color/space/radius/shadow/type. |
| `assets/logo-mark.svg` | Brand mark — a recovery progress ring with a "today" node (green on light). |
| `assets/logo-mark-white.svg` | Brand mark, white — for the dark focus surface. |

> Note: the brand (复元 / Reva), the logo, and the fonts are a **proposed
> greenfield system**, not a confirmed brand. Treat them as the current design
> direction, swappable later.

---

## 2. Fidelity

**High‑fidelity.** Final colors, typography, spacing, radii, shadows, copy, and
interactions are all specified. Rebuild pixel‑accurately using the codebase's
component library, then map the literal values below onto your design tokens.

---

## 3. Product structure

Single‑column, mobile‑first. Fixed bottom tab bar with four tabs; a sticky top
context bar per screen; content scrolls between. One screen (Risk detail) is
pushed modally over the tabs.

```
Onboarding (3 steps) ──"进入复元"──▶ App
                                     ├─ 今天  Today      (tab)
                                     ├─ 数据  Data       (tab)  ──tap LDL row──▶ Risk detail (pushed)
                                     ├─ 复元  Agent      (tab)
                                     └─ 我的  Me         (tab)
                          Today / Risk detail also deep‑link ▶ Risk detail / Agent
```

Tabs: **今天 (sun) · 数据 (activity) · 复元 (messages-square) · 我的 (user)**.

---

## 4. Screens / Views

Coordinates are logical; the design canvas is a 402 × 874 iPhone frame, 16px
content gutters. "mono" = IBM Plex Mono tabular figures; "sans" = Manrope +
Noto Sans SC.

### 4.1 Onboarding (3 steps, full‑screen, paper bg)
Shared shell: 72px top padding, content flexes, footer holds a 3‑dot stepper +
full‑width primary button + muted sub‑caption. Dot for current step is a 22×7
green pill; others 7×7 `--line`.

- **Step 0 — Welcome.** 72×72 `--focus-bg` rounded‑22 tile holding the white
  logo mark (shadow `0 14px 36px rgba(8,20,15,.3)`). H1 (sans 800, 34px,
  −0.02em): "体检之后，/ 主动健康的 90 天。" Body (sans 16/1.6 `--ink-2`):
  "复元把你的体检异常项，变成每天可执行的小计划，再用手环和复查数据验证它真的在改善。"
  CTA "开始". Sub: "已有 12,000+ 体检用户在复元管理健康".
- **Step 1 — Import report.** Info chip "第 1 步". H (sans 800, 26px) "导入你的体检报告".
  Body "复元会自动识别异常项，并按心代谢风险排序。" Card (pad 0): file row
  (`file-text` icon, "体检报告_2026.pdf", normal chip "已解析"), then 3 lab rows
  (LDL‑C / 空腹血糖 / BMI — no range bar here). Footer line with `lock` icon:
  "数据加密存储，仅你可见". CTA "继续".
- **Step 2 — Connect wearable.** Chip "第 2 步". H "连接你的穿戴设备". Body
  "用真实的心率、睡眠、步数校准计划，并验证改善。" Card with 3 device rows: Apple
  Watch (connected — green tile, `check-circle-2`), 华为运动健康 + Garmin
  (ghost "连接" button). CTA "进入复元" → enters app.

### 4.2 今天 / Today (tab) — most important screen
Top bar: sub "晚上好 · 5月18日 周一", title "子衡，今天还差一点", right = 40px green
avatar "衡". Body is a 22px‑gap vertical stack:

1. **Readiness hero (focus surface).** `--focus-bg` card, radius 24, pad 20,
   shadow `--shadow-focus`, `overflow:hidden`. A decorative radial glow
   (`rgba(58,210,159,.18)`) bleeds from the top‑right corner. Layout:
   - **Left:** Readiness ring (see §6.1) — 110px, score **86**, gradient arc
     green→bright with a bright tip node, "86" mono + "/ 100" caption centered.
   - **Right:** overline mono "TODAY · 恢复就绪度" (`--focus-ink-2`); status (sans
     700, 18px, `--green-bright`) "已就绪 · 适合中等强度"; body (sans 13.5/1.5
     `--focus-ink-2`) "静息心率比上周低 4 bpm，睡眠略短。今天可以快走或骑行 30 分钟。"
   - **Footer strip** (above a `--focus-line` hairline): 3 vitals, each label +
     mono value + delta — 静息心率 **56** bpm (↓ 4), 睡眠 **6h12** (略短), HRV
     **48** ms (↑ 平稳). Deltas in `--green-bright`.

2. **今明空气 / Air quality (today + tomorrow).** ← *added in the latest pass.*
   Section overline "今明空气" with right action "朝阳区 · 实时". White card
   (pad 0) split into two equal columns by a vertical hairline:
   - **今天:** label "今天" + status chip; mono AQI **62**, level "良"
     (`normal`/green); advice (sans 12.5 `--ink-2`) "空气不错，适合户外快走、骑行".
   - **明天:** "明天" + chip; mono AQI **118**, level "轻度污染"
     (`caution`/amber); advice "改室内运动，外出戴口罩".
   Rationale: AQI qualifies the hero's outdoor‑exercise recommendation, so the
   two are intentionally adjacent. Levels use the three‑step semantic
   (good→green, light pollution→amber, heavy→risk/red).

3. **今日计划 / Today plan.** Overline "今日计划" + right action = a mini progress
   bar (54×6, green fill) followed by "1/4". White card (pad 0) of tappable plan
   rows (see §6.4): 餐后散步 20 分钟 (footprints, "2 次", done), 午餐用全谷物替换精米
   (utensils), 记录今日血压 (pill), 23:30 前入睡 (moon). Footer line w/ `sparkles`:
   "计划每天根据你的数据自动调整".

4. **今日数据 / Today metrics.** Overline + a 3‑up row of metric tiles (§6.5):
   血压 122/78 mmHg (normal, "达标") · 空腹血糖 6.3 mmol/L (caution, "↑ 临界") ·
   步数 7.2k (info, "目标 8k").

5. **本阶段重点 / Current focus.** Overline + a tappable white card → Risk detail.
   44px `--risk-bg` tile w/ `trending-down`, title "把 LDL‑C 降到 3.4 以下", sub
   "3.8 → 3.1 · 12 周内可明显改善", trailing `chevron-right`.

### 4.3 数据 / Data (tab)
Top bar: sub "体检 · 2026‑04‑11", title "你的数据".
1. **90‑day progress card** (§6.6): "90 天主动管理 · 第 23 / 90 天", green
   gradient bar at 26%.
2. **体检异常项** (overline, action "5 项异常"). Card of **lab rows with inline
   range bars** (§6.3): LDL‑C 3.8 (risk, tappable→Risk detail), 空腹血糖 6.3
   (caution), BMI 26.4 (caution), 血压 122/78 (normal), HDL‑C 1.3 (normal).
3. **手环数据** (overline, action "过去 7 天"). Card: 静息心率 58 bpm with a filled
   sparkline `[64,62,63,60,61,59,58]`, caption "↓ 4 bpm，恢复在改善". Below, a
   3‑up metric row: 睡眠 6h12 (caution) · HRV 48 ms (normal, ↑) · 活动 412 kcal
   (normal).

### 4.4 Risk detail (pushed over tabs)
Sticky translucent header (paper @ 85% + blur, hairline): 38px circular back
button (`chevron-left`), eyebrow "心代谢风险", title "低密度脂蛋白 LDL‑C".
Scrolling body, 20px gap:
1. **Current value card:** label "当前值"; **3.8** mono 44px `--risk` + " mmol/L"
   16px `--ink-3`; risk chip "偏高". Explainer (sans 14.5/1.6): "你的 LDL‑C 是
   **3.8 mmol/L**，理想值在 3.4 以下。它是心血管风险里最值得先处理的一项——好消息是，它
   对饮食和运动的反应很快。"
2. **12 周改善预测** (overline). Card holding the trend chart (§6.2), series
   `基线 3.8 → 4周 3.6 → 8周 3.4 → 12周 3.1`, target line 3.4.
3. **你的计划** (overline). Card of 3 rows (green tiles): 用全谷物替换精米白面
   (utensils, "每天 1 餐") · 每周 2 次深海鱼 (fish, "补充 Omega‑3") · 每天 6,000
   步以上 (footprints, "已坚持 18 天").
4. **Dark CTA** (full, `messages-square`): "问复元：怎么吃能降得更快？" → Agent.

### 4.5 复元 / Agent (tab) — chat
Sticky header: 32px logo mark, "复元", status dot + "了解你的全部健康数据".
Scrollable message list of chat bubbles (§6.7). Composer (fixed): a horizontally
scrollable row of quick‑reply pills (green‑50, green‑100 border) — "今天能跑步吗？"
/ "解读我的血糖" / "这周吃得怎么样？" — then a pill input "问问复元…" with a 38px
round green send button (`arrow-up`). Seed agent message:
"晚上好，子衡。今天的恢复就绪度是 86，状态不错。想聊聊计划，还是看某项指标？"
Replies are 4 canned, keyword‑matched branches (跑/运动/强度, 血糖/糖, 吃/饮食/降,
else) — see `revaReply()` in `RevaApp.jsx`. **Replace with a real model call.**

### 4.6 我的 / Me (tab)
Top bar title "我的" (no mark). Profile card: 54px avatar "衡", "张子衡", "男 · 41
岁 · 心代谢管理中", plus the 90‑day progress bar. **已连接设备** list: Apple Watch
(实时同步) · 体检报告 (2026‑04‑11) · 华为运动健康 (未连接, ghost "连接"). **设置**
list: 每日提醒 08:00 · 复查提醒 7月 11 日 · 隐私与数据 · 帮助与反馈, each a row
with leading icon + trailing value/chevron.

---

## 5. Interactions & behavior

- **Navigation = a small state machine** (`RevaApp`): `phase` (`onboard`|`app`),
  `tab` (`today`|`data`|`agent`|`me`), `route` (`null`|`risk`). Risk detail is a
  pushed route that overlays the tabbed shell; its back button clears `route`.
  Replace with the platform's real navigator (stack + tab navigator).
- **Plan toggle:** tapping a plan row flips its `done` state — circle fills
  green with a check, title gets strike‑through + 0.5 opacity. `planDone` map.
- **Agent send:** appends the user bubble, then after ~450ms appends a canned
  reply; list auto‑scrolls to bottom. Quick‑reply pills submit their text.
- **Tab switch:** the Today/Data/Me screens scroll internally; Agent manages its
  own scroll (no outer scroll).
- **Press feedback:** buttons scale to 0.97 on pointer‑down. Tappable cards lift
  (translateY −1px + deeper shadow) on hover (web/tablet).
- **Deep links:** Today's "本阶段重点" card and any LDL‑C row → Risk detail;
  Risk detail CTA → Agent tab.

### Animation note (important gotcha)
The readiness ring and progress bars are authored to **render correct at rest**
(final arc offset / final width set directly), *not* via a JS
`requestAnimationFrame` tween. An earlier version animated from empty via rAF and
rendered blank in non‑painting/headless contexts. **When you re‑implement, drive
the sweep/grow entrance with the platform's animation API**, but keep the resting
value correct so a static render is never empty. Per the design system, motion is
calm: ring sweep ~420ms, ease `cubic-bezier(.22,.61,.36,1)`, no bounce, no
infinite loops.

---

## 6. Component specs

All non‑interactive numbers are **mono, tabular**. Status color always comes
from the three‑step `STATUS` map: `normal` green · `caution` amber · `risk`
coral‑red · `info` blue — each with a value color `c`, tint `bg`, and line `ln`.

### 6.1 ReadinessRing
SVG ring, default 110px, 11px stroke. Track = `--green-100` (light) /
`--focus-line` (dark). Arc = a linear gradient `--green-500 → --green-bright`,
round cap, `strokeDashoffset` set to the final value for `score/100`. A filled
`--green-bright` tip node sits at the arc's end angle. Center: score (mono,
~0.33×size) over "/ 100" caption.

### 6.2 TrendChart
SVG line chart, viewBox 320×164. 3 horizontal gridlines (`--line`). Dashed target
band at `target` with right‑aligned mono label "理想 ≤ {target}". Gradient area
fill under the line (`--green-500` @ 14%→0). Line `--green-500`, 2.75px round.
Each point: hollow white dot (last point = filled + 8px halo) with a mono value
label above and an x‑axis time label below.

### 6.3 LabRow (with range bar)
Row: status dot + name (sans 600, 15px), an **inline range bar**, then a sub
caption in the status color. Right: mono value (19px, status color) over a mono
unit. Optional trailing chevron when tappable. The range bar is a 5px pill with a
segmented gradient `normal‑bg 0–55% / caution‑bg 55–78% / risk‑bg 78–100%` and an
11px circular marker (status‑colored, white ring) positioned at `pos` (0–1).
Current positions: LDL‑C .86, 空腹血糖 .64, BMI .70, 血压 .32, HDL‑C .28.
(Onboarding reuses LabRow with `pos=null` to hide the bar.)

### 6.4 PlanItem
38px rounded icon tile (green‑50/green when done, else paper‑2/ink‑2) + title +
sub + optional mono tag + a 24px check circle. Done → strike‑through, 0.5 opacity,
filled green check. Whole row tappable.

### 6.5 MetricTile
Flexible white tile, radius 16. Icon + label row; mono value (22px, status color)
+ mono unit; optional **delta pill** (mono 10.5, status‑colored, tint bg + line,
with an optional `↑/↓` trend glyph).

### 6.6 DayProgress
Label "90 天主动管理" + mono "第 {day} / {total} 天"; 8px track (`--paper-2`) with a
`--green-500 → --green-bright` gradient fill at `day/total`.

### 6.7 ChatBubble
Max‑width 82%. Agent = white surface, hairline, soft shadow, bottom‑left tail
(radius 5). Me = `--green-500`, white text, green shadow, bottom‑right tail. sans
15/1.55.

### Shared chrome
- **Button** variants: `primary` (green, white, green shadow), `secondary`
  (white + strong hairline), `tertiary` (text), `dark` (focus bg, bright‑green
  text), `ghost` (green‑50). Sizes sm/md/lg, fully pill, 0.97 press.
- **Chip:** pill, status‑tinted bg + line + a 7px dot. **Dot:** status circle.
- **SectionLabel:** uppercase overline (sans 700, 11px, .09em) + optional right
  action (green‑600).
- **Card:** white, 1px `--line`, radius 18, `--shadow-md`; lifts on hover when
  tappable.
- **TopBar:** sticky, paper @ 82% + blur, optional logo mark, sub + 21px/800
  title, optional right slot.
- **TabBar:** sticky bottom, white @ 92% + blur, 4 items; active item shows a
  green‑50 pill behind the icon and green‑600 label.

---

## 7. Design tokens

Use `colors_and_type.css` as the source of truth. `RevaApp.jsx` mirrors these in
a JS `C` map (and a `STATUS` map) because it's inline‑styled React — when porting,
**delete the `C` map and bind to your real tokens instead.** Mapping:

**Color**
- Paper `--paper #F7F6F2` · paper‑2 `#F1EFE8` · surface `#FFFFFF` · surface‑2 `#FBFAF7`
- Ink 1–4 `#16201B / #5C6660 / #8A938D / #B7BDB7`
- Line `#E7E5DE` · line‑strong `#D7D5CC`
- Green 50/100/300/500/600/700 `#E8F2EC / #CDE6D8 / #6FBE94 / #1F8A5B / #176F49 / #115738`; green‑bright `#3AD29F`
- Blue 50/100/500/600 `#E7EEFB / #CBDCF6 / #2A6FDB / #1F58B6`
- Focus bg `#0F1C17` / bg‑2 `#16271F` / line `#23463A` / ink‑1 `#EAF3EE` / ink‑2 `#9DB3A8`
- Semantic: normal `#1F8A5B` (bg `#E8F2EC`, line `#CDE6D8`) · caution `#C98A1E` (bg `#FBF1DD`, line `#F0DCB0`) · risk `#D5503A` (bg `#FBE8E4`, line `#F3CDC4`) · info `#2A6FDB` (bg `#E7EEFB`, line `#CBDCF6`)

**Radii** xs 6 · sm 10 · md 14 · lg 18 (cards) · xl 24 (hero/sheets) · pill 999
**Shadows** sm/md/lg + focus `0 18px 48px rgba(8,20,15,.45)` (green‑tinted, low)
**Spacing** 4px base: 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 64
**Motion** ease‑out `cubic-bezier(.22,.61,.36,1)`; dur fast 140 / base 240 / slow 420ms

**Type** (semantic classes in the CSS): display (mono 56) · metric (mono 30) ·
h1 (800/28) · h2 (700/22) · h3 (700/18) · title (600/16) · body (15/1.55) ·
body‑2 (14) · caption (12) · overline (600/11, .08em, upper) · data‑label
(mono 12) · unit (mono 14). Latin **Manrope**, Chinese **Noto Sans SC** (≈
PingFang SC on device), data **IBM Plex Mono** with tabular figures.

---

## 8. Assets & dependencies

- **Icons:** Lucide (1.75px stroke, rounded caps). Names used: `sun, activity,
  messages-square, user, footprints, utensils, pill, moon, gauge, droplet,
  trending-down, sparkles, wind, file-text, lock, watch, check-circle-2,
  check, chevron-left, chevron-right, arrow-up, fish, flame, bell,
  calendar-check, shield, circle-help`. Swap to your house icon set if you have
  one (match the ~1.75px outline style).
- **Fonts:** Manrope, Noto Sans SC, IBM Plex Mono (Google Fonts in the proto;
  bundle real font files / use platform equivalents in production).
- **Logo:** `assets/logo-mark.svg` (+ white variant) — recovery ring with a
  "today" node; deliberately the same motif as the readiness ring.
- **No real data layer.** All values are hardcoded mock data; there is **no
  backend, auth, or live API** in this prototype. Wire screens to your real
  endpoints (exam parse, wearable sync, plan engine, AQI provider, agent model).

---

## 9. Continuing in Claude Code

This bundle is self‑contained — drop it into your repo and drive the work with
Claude Code:

1. **Place the bundle** at the repo root, e.g. `design/reva-mobile/`, and commit
   it so Claude Code can read it as reference.
2. **Open Claude Code in the repo** and point it at this README first:
   > "Read `design/reva-mobile/README.md` and `RevaApp.jsx`. We're implementing
   > this Reva mobile UI in <your stack>. Start with the **Today** screen."
3. **Establish the foundation before screens.** Ask it to: (a) add the design
   tokens from `colors_and_type.css` to your theme system; (b) wire the three
   fonts; (c) build the shared primitives (Button, Chip, Card, SectionLabel,
   TopBar, TabBar) so screens compose from them.
4. **Build screen‑by‑screen, in priority order:** Today → Data → Risk detail →
   Agent → Me → Onboarding. Reference the matching §4 section each time and have
   Claude Code diff its result against the spec.
5. **Replace the prototype's fakes with real integrations:** the nav state
   machine → your router; `revaReply()` → a real model/streaming endpoint;
   hardcoded labs/metrics/AQI → your APIs; "connect device" → real wearable
   OAuth.
6. **Keep the animation guidance from §5** — correct resting state first, then
   layer entrance motion with the platform's animation API.
7. **Iterate on optimization** against the design system's principles (numbers
   are the hero, three‑step semantics, warm‑paper calm, restraint with green).

To regenerate this package after more design changes here, re‑export the handoff
folder and re‑sync it into the repo.

---

## 10. Files in this bundle
- `README.md` — this document
- `RevaApp.jsx` — the full UI source (port this)
- `Reva Mobile.dc.html` — preview wrapper (reference only)
- `colors_and_type.css` — tokens + type classes (source of truth)
- `assets/logo-mark.svg`, `assets/logo-mark-white.svg` — brand mark
