# Mobile Tab Aheng Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename the second Mobile bottom tab from `私教` to `阿衡` and keep App Store release narrative aligned.

**Architecture:** Keep route names unchanged (`chat`) and centralize visible tab labels in `mobile/app/(tabs)/_layout.tsx`. Release docs and `check_app_store_release_pack.py` should gate against stale public tab wording.

**Tech Stack:** React Native / Expo Router, Jest, Python pytest release tooling.

---

### Task 1: Lock Mobile Tab Labels

**Files:**
- Modify: `mobile/app/(tabs)/_layout.tsx`
- Test: `mobile/app/(tabs)/__tests__/tabLayout.test.ts`

**Steps:**
1. Add failing tests for `getMainTabLabels()` and `getMainTabAccessibilityLabels().chat`.
2. Run `cd mobile && ./node_modules/.bin/jest --runTestsByPath 'app/(tabs)/__tests__/tabLayout.test.ts' --runInBand`; expected fail because helpers do not exist.
3. Export tab metadata helpers from `_layout.tsx`.
4. Change visible chat tab label to `阿衡` and accessibility label to `阿衡，与健康参谋对话`.
5. Rerun the same Jest command; expected pass.

### Task 2: Lock Release Narrative

**Files:**
- Modify: `scripts/check_app_store_release_pack.py`
- Modify: `backend/tests/test_app_store_release_pack.py`
- Modify: `docs/release/app-store/submission-pack.md`
- Modify: `docs/release/app-store/review-notes.zh-CN.md`
- Modify: `docs/release/app-store/screenshot-runbook.md`

**Steps:**
1. Add failing pytest coverage that treats `私教` as stale public wording and expects `今日 / 阿衡 / 记录 / 我`.
2. Run `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py::test_release_narrative_rejects_stale_public_positioning -q --no-cov`; expected fail.
3. Update release gate constants and App Store docs.
4. Rerun target pytest and `python3 scripts/check_app_store_release_pack.py`; expected pass.

### Task 3: Update System Docs And Verify

**Files:**
- Modify: `docs/system-map/product-map.md`
- Modify: `docs/system-map/mobile-nav-map.md`
- Modify: `mobile/PRODUCT_MAP.md`
- Modify: related weekly/dossier docs.

**Steps:**
1. Replace current user-facing tab references with `阿衡`.
2. Keep historical notes and technical paths where needed.
3. Run dossier consistency, doc drift, TypeScript, release gate, target Jest, target pytest, and `git diff --check`.
