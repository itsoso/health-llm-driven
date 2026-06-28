# App Store Screenshot Runbook

## Target Devices

Apple allows one to ten screenshots per device size. For the first iPhone submission, capture the 6.9-inch display set from iPhone 17 Pro Max / 16 Pro Max / 16 Plus / 15 Pro Max / 15 Plus / 14 Pro Max compatible sizes.

Recommended first pass:

- iPhone 17 Pro simulator or physical device for actual UI traversal.
- Export or resize final marketing screenshots to App Store Connect accepted 6.9-inch portrait sizes when needed: 1260 x 2736, 1290 x 2796, or 1320 x 2868 pixels.

## Core Screens

1. `今日`: next health action and timeline.
2. `私教`: chat + dynamic UI card.
3. `记录`: fast food, water, supplement, workout, body metric entry.
4. `我`: data connections and health profile hub.
5. `隐私政策`: HealthKit, AI, account deletion, medical boundary.
6. `删除账号与数据`: destructive confirmation sheet, only for internal review screenshot; do not include if it exposes account data.

## Capture Command

If the app is already installed on a booted simulator:

```bash
./scripts/mobile-sim-screenshots.sh
```

If the app is not installed, build the simulator app first:

```bash
./scripts/sim-build.sh --device "iPhone 17 Pro"
```

Then rerun:

```bash
./scripts/mobile-sim-screenshots.sh --output design/screenshots/app-store/manual
```

## Human QA Checklist

- [ ] No diagnosis, treatment, prescription, or dosage-change promise appears in screenshots.
- [ ] No private user PII, raw lab values, genotype, medication details, or family data is visible unless using a dedicated demo account.
- [ ] Bottom navigation labels are `今日 / 私教 / 记录 / 我`.
- [ ] Chat screenshot shows a bounded dynamic card, not raw JSON.
- [ ] Record screenshot shows quick food/water/workout entry.
- [ ] Me screenshot shows `账号与隐私` and data controls.
- [ ] Privacy screenshot matches `https://health.executor.life/privacy`.

## Output Convention

Save raw screenshots under:

`design/screenshots/app-store/<YYYYMMDD-HHMMSS>/`

Only commit screenshots when the user explicitly asks. The runbook and scripts are the durable source; screenshots are often regenerated.
