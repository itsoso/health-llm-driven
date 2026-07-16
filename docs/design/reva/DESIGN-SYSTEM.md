# 复元 Reva — Design System

> The 90 days after your check-up.
> 体检之后的 90 天主动健康管理 Agent。

Reva (复元 — *fùyuán*, "to recover, to restore vitality") is a proactive health‑management
agent for the period **after** a physical exam. China runs tens of millions of paid
health check‑ups a year for middle‑and‑high‑income adults, but almost none of that turns
into continuous management. Wearables (Apple Watch, Garmin, Huawei) generate a flood of
body data that never closes the loop with labs, diet, training, sleep, or a doctor's advice.

Reva closes that loop. It takes the **abnormal items** from your check‑up, converts them
into a **daily executable plan**, and **verifies improvement** with wearable + re‑check data
over a focused 90‑day window. The initial wedge is **cardiometabolic risk** (blood pressure,
lipids, glucose/HbA1c, weight, waist) and **exercise recovery**. The long‑term vision is to
become the operating system for personal health data and proactive prevention.

---

## ⚠️ Status & provenance

This is a **greenfield brand**. No existing brand assets, codebase, Figma, or decks were
provided. Everything here — name, logo, palette, type, voice, UI — is a **proposed system**
created from the company description, intended as a starting point to iterate on.

**Sources given:** a single product description (Chinese). No links, repos, or files.

**Open decisions flagged for the user** (see "Caveats" / ask at the end of this doc):
- Brand name **复元 / Reva** is proposed, not confirmed.
- Logo is a **proposed placeholder** (a recovery‑ring mark) — `assets/logo-mark.svg`.
- Fonts are loaded from **Google Fonts CDN**, not bundled TTFs (see Typography).

---

## Index — what's in this system

| Path | What it is |
| --- | --- |
| `README.md` | This file — context, content + visual foundations, iconography, manifest |
| `colors_and_type.css` | All design tokens: color, type scale, radii, shadows, spacing, motion |
| `assets/` | Logo mark (green + white on dark), proposed |
| `preview/` | Design‑system spec cards (rendered in the Design System tab) |
| `ui_kits/mobile-app/` | High‑fidelity recreation of the Reva app — `index.html` + JSX components |
| `SKILL.md` | Agent‑Skills manifest so this system can be used inside Claude Code |

Primary UI language is **Simplified Chinese**, with English/mono used for data labels,
units, and metric values.

---

## CONTENT FUNDAMENTALS — how Reva writes

Reva is a **calm, competent coach who happens to know medicine** — never alarmist, never
preachy, never a cheerleader. It speaks Chinese in plain, warm, specific language and treats
the user as a capable adult managing a project (their own 90 days).

**Voice principles**
- **Direct and specific over vague encouragement.** Not "继续加油！" but
  "今天走满 6,000 步，你的血压计划就完成了。" (Concrete action → concrete payoff.)
- **Address the user as 你.** Reva refers to itself sparingly as 复元, usually just speaks.
- **Lead with the "why it matters to you," then the action.** Translate a lab number into
  a lived consequence before prescribing.
- **Clinical honesty without alarm.** Flag risk plainly ("低密度脂蛋白偏高"), pair it
  immediately with a path forward ("90 天内可以明显改善")。 Never catastrophize.
- **Numbers are the hero, words are the frame.** Let the data value carry weight; keep
  surrounding copy short.

**Tone by surface**
- *Daily plan / nudges:* warm, brief, second‑person, one action at a time.
- *Lab / risk explainers:* neutral‑clinical, plain‑language, cites the measured value.
- *Re‑check results:* quietly celebratory — show the delta, let the improvement speak.
- *Onboarding:* reassuring and concrete about what the 90 days will involve.

**Casing & mechanics**
- Chinese body copy: no terminal periods on short UI lines; full stops only in paragraphs.
- English/labels: **Sentence case**, never ALL‑CAPS except small overlines (e.g. `TODAY`,
  `LDL‑C`). Units stay lowercase and mono (`mmHg`, `mmol/L`, `bpm`, `步`).
- Numbers: always tabular mono. Show units in muted ink, value in primary ink.
- **No emoji.** Status is carried by color + iconography, not faces. (One exception
  considered and rejected — keep it clinical.)

**Examples**
- Risk card title: `低密度脂蛋白胆固醇（LDL‑C）偏高`
- Risk card body: `你的 LDL‑C 是 3.8 mmol/L，理想值在 3.4 以下。这是心血管风险里最值得先处理的一项。`
- Today nudge: `早餐后散步 10 分钟，帮助餐后血糖回落。`
- Re‑check win: `12 周复查：LDL‑C 3.8 → 3.1 mmol/L。已回到理想范围。`
- Empty state: `还没有连接手环。连接后，复元会用你的真实数据校准计划。`

---

## VISUAL FOUNDATIONS

The feeling is **clinical calm with a pulse of vitality** — a quiet, paper‑warm interface
that gets out of the way of the data, with one confident green that signals health and
recovery. It should feel as trustworthy as a good clinic and as personal as a coach's text.

### Color
- **Warm paper, not stark white.** App background is `--paper` `#F7F6F2`; cards are pure
  white `--surface` to lift cleanly off the paper. This warmth is what keeps a data‑dense
  health app from feeling like a hospital EMR.
- **One hero color: Vital Green `#1F8A5B`.** Used for primary actions, the recovery ring,
  "in range / improving," and the brand mark. Restraint is the rule — green earns attention.
- **Clinical Blue `#2A6FDB`** is the secondary: links, informational trends, neutral data.
- **Three‑step clinical semantics** carry lab/metric status everywhere:
  green = normal/improving · amber `#C98A1E` = borderline/watch · coral‑red `#D5503A` =
  out‑of‑range/high. Each has a tint bg + line for chips and rows.
- **A deep green‑black "focus" surface `#0F1C17`** is reserved for hero data moments — the
  daily readiness ring, the agent chat header. On it, green goes bright (`#3AD29F`). Used
  sparingly, it makes the one number that matters today feel important.
- Imagery, when used, leans **warm and natural‑light** (skin, food, movement) — never cold,
  clinical stock blue. No heavy filters; gentle warmth, real texture.

### Type
- **Manrope** (Latin, humanist‑geometric) + **Noto Sans SC** (Chinese) for all UI and
  headlines. **IBM Plex Mono** for every number that's a measurement — lab values, scores,
  steps, heart rate, units. Putting data in mono with tabular figures is a core signature.
- Big metric numbers (`.display`, `.metric`) are the loudest thing on most screens.
  Headlines are tight (‑0.02em) and heavy (700–800); body is generous (1.5–1.55 line‑height).
- See the type scale cards in `preview/` and the semantic classes in `colors_and_type.css`.

### Shape, depth & borders
- **Corner radii are friendly but composed:** cards `--r-lg` 18px, hero/sheets `--r-xl` 24px,
  inputs/buttons 12–14px, chips & primary CTA fully pill. Never sharp, never bubbly.
- **Cards = white surface + 1px hairline `#E7E5DE` + soft low shadow** (`--shadow-md`).
  Shadows are green‑tinted, low, and diffuse — elevation is gentle. Avoid hard drop shadows.
- Dividers are hairlines; grouped lists sit on `--paper-2` recessed backgrounds.
- **No left‑border‑accent cards, no purple gradients, no emoji cards.** Status comes from a
  small colored dot/chip + the value, not from decorative banners.

### Layout
- Mobile‑first, single column, generous 16–20px gutters. A fixed top context bar (greeting +
  date) and a fixed bottom tab bar (今天 · 数据 · 复元 · 我的). Content scrolls between.
- Rhythm comes from alternating **white cards** on **warm paper**, occasional **focus‑surface
  hero**, and full‑width **section overlines**.

### Motion
- **Calm and physical.** Entrances fade + rise 8–12px with `--ease-out` over ~240ms. Rings
  and progress animate their sweep on appear (~420ms). No bounce, no spring overshoot, no
  infinite decorative loops. Tactile, not playful.

### States
- **Hover** (web/tablet): surface darkens ~4%, or primary goes to `--green-600`.
- **Press:** scale 0.97 + slightly darker; never a color flash.
- **Focus:** 2px `--green-500` ring at 40% + 2px offset.
- **Disabled:** `--ink-4` text on `--paper-2`, no shadow.
- Transparency/blur: used only for sheet scrims and the sticky top bar (paper at 80% +
  backdrop blur). Not decorative.

---

## ICONOGRAPHY

> ⚠️ **Substitution flagged:** no icon set was provided. Reva uses **[Lucide](https://lucide.dev)**
> (CDN), chosen for its clean, even **~1.75px stroke** and rounded line caps — clinical but
> humane, and it covers the health vocabulary well. If you have a house icon set, swap it in.

- **Style:** outline / stroke icons only, 1.75px, rounded caps & joins, 24px grid. No filled
  icons except tiny status dots. Icons inherit `currentColor` and sit in `--ink-2` by default,
  taking on a semantic color only when they represent status.
- **Health vocabulary** (Lucide names used in the kit): `heart`, `activity` (HR/pulse),
  `droplet`/`droplets` (glucose, lipids), `moon` (sleep), `footprints` (steps),
  `utensils` (diet), `flask-conical` (labs), `dumbbell` (training), `gauge` (blood pressure),
  `calendar-check` (re‑check), `trending-down`/`trending-up` (deltas), `watch` (wearable),
  `messages-square` (agent), `user`, `home`/`sun` (today), `chevron-right`.
- **Status semantics:** a 8px filled dot or a small chip — green/amber/red — never an emoji,
  never a colored exclamation illustration.
- **Unicode/glyphs:** arrows for deltas may use `↓ ↑ →` in mono; otherwise prefer Lucide.
- **Brand mark** (`assets/logo-mark.svg`) is the one bespoke glyph: a recovery progress ring
  with a "today" node — deliberately the same motif as the in‑app readiness ring.

---

## How to build with this system

1. Link `colors_and_type.css` and the Google Fonts line at the top of any file.
2. Use the semantic CSS vars (`--ink-1`, `--green-500`, `--normal`, `--r-lg`, `--shadow-md`)
   and type classes (`.h1`, `.display`, `.data-label`) — don't hard‑code hexes.
3. Pull UI from `ui_kits/mobile-app/` — components are cosmetic, modular, reusable.
4. Numbers in mono, Chinese‑primary copy, three‑step semantics for any health state.

---

## 强制契约(Enforcement) — 规范只有被闸守住才产生约束

> 2026-07-16 加固:premium-feel 审计发现"有 token、没约束"是移动端掉一档的根因
> (~597 处裸 hex、67 处裸 fontFamily 绕过 token)。规范文档不产生约束——**闸才产生约束**。

**单一真源(RN 侧):** `mobile/constants/revaTheme.ts` 是本 CSS 的忠实移植(colors/type/spacing/
radii/shadows/motion)。字体经 `mobile/components/reva/useRevaFonts.ts` 加载(Manrope + IBM Plex
Mono);字型 token 必须走 `revaFonts.sans/mono`,数字走 mono(tabular)。

**三层贯彻:**
1. **单一真源** — 颜色只用 `revaColors` / `theme` 语义 token;字型只用 `revaFonts`;间距只用 `revaSpacing`。
2. **强制原语** — 文字走 `AppText`(variant),卡片走 `CardShell` / 卡片原语,不手写裸样式。屏 = 组合原语。
3. **防漂移 CI 闸** — `mobile/scripts/check_design_tokens.js`(ratchet:存量债 grandfather 进 BASELINE,
   **新增裸 hex / fontFamily → 退出非零**)。跑 `npm run design:check`(ratchet)/ `design:report`(列 top 违规)。
   迁一批屏到原语后,用新计数**调低 BASELINE** 并提交——只减不增,与"加层不减层 / 只 TIGHTEN"同构。

**内容层规则(不止视觉——审计发现的"工程味"泄漏):**
- **一次事件一个确认**:一条记录不要用"正文 + 回执 + 卡片"三种表示叠着说(啰嗦=不精致)。留一个干净确认。
- **不露原始 id**:UI 里不出现 `#671` 这种 DB 主键;要么人话化("已记入今日饮水"),要么不显示。
- **透明化/meta 行默认收起**:模型名 / 轮次 / 耗时 / 分享入口是 power-user 信息,默认折叠(展开才看),别每轮挂一条灰噪声。
- **数字即仪表**:健康数字一律 mono + tabular-nums,列对齐、不抖动。

任何 agent(Claude/Codex/其他)在移动端建新屏 / 改样式,以上为**硬契约**:先读本节,产出走原语,过 `design:check`。
