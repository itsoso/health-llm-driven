# App Store Screenshot Runbook

## Target Devices

Apple allows one to ten screenshots per device size. For the first iPhone submission, capture the 6.9-inch display set from iPhone 17 Pro Max / 16 Pro Max / 16 Plus / 15 Pro Max / 15 Plus / 14 Pro Max compatible sizes.

Recommended first pass:

- iPhone 17 Pro simulator or physical device for actual UI traversal.
- Export or resize final marketing screenshots to App Store Connect accepted 6.9-inch portrait sizes when needed: 1260 x 2736, 1290 x 2796, or 1320 x 2868 pixels.

## Core Screens

1. `今日`: next health action and timeline.
2. `小巴`: chat + dynamic UI card.
3. `记录`: fast food, water, supplement, workout, body metric entry.
4. `我`: data connections and health profile hub.
5. `隐私政策`: HealthKit, AI, account deletion, medical boundary.
6. `删除账号与数据`: destructive confirmation sheet, only for internal review screenshot; do not include if it exposes account data.

## Capture Command

If the app is already installed on a booted simulator:

```bash
./scripts/mobile-sim-screenshots.sh --privacy-status private
```

If the app is not installed, build the simulator app first:

```bash
./scripts/sim-build.sh --device "iPhone 17 Pro" --configuration "Release" --build-number "$APP_STORE_BUILD_ID"
```

Then rerun:

```bash
./scripts/mobile-sim-screenshots.sh --output design/screenshots/app-store/manual --privacy-status private
```

For App Store candidate screenshots, use a dedicated demo account or a sanitized data build and mark the capture explicitly. Capture first; do not reuse a private QA set:

```bash
./scripts/mobile-sim-screenshots.sh \
  --output design/screenshots/app-store/<build-id>-raw \
  --privacy-status demo \
  --build-id <build-id>
```

If a demo account is not available yet, a private QA set can be turned into a review-required sanitized candidate. This is a fallback, not an automatic approval:

```bash
python3 scripts/sanitize_app_store_screenshots.py \
  design/screenshots/app-store/<private-build-id> \
  design/screenshots/app-store/<build-id>-sanitized \
  --overwrite
```

Review every PNG manually. If the sanitized candidate still exposes private data, discard it and capture with a dedicated demo account instead.

Then prepare the final App Store-sized export:

```bash
python3 scripts/prepare_app_store_screenshots.py \
  design/screenshots/app-store/<build-id>-raw-or-sanitized \
  design/screenshots/app-store/<build-id>-ready \
  --size 1290x2796 \
  --confirm-sanitized-reviewed
```

`prepare_app_store_screenshots.py` refuses `privacy_status=private`, writes `app_store_ready=true`, and validates the prepared output before returning success. If the source was produced by `sanitize_app_store_screenshots.py`, prepare refuses it until `--confirm-sanitized-reviewed` is provided after human visual QA.

## Machine Gate

Every capture writes `manifest.json` next to the PNGs. Validate local QA evidence:

```bash
python3 scripts/check_app_store_screenshots.py design/screenshots/app-store/<build-id>
```

Validate an App Store candidate set:

```bash
python3 scripts/check_app_store_screenshots.py \
  design/screenshots/app-store/<build-id>-ready \
  --app-store-ready \
  --build-id <build-id>
```

The App Store-ready gate requires:

- `privacy_status` is `demo` or `sanitized`.
- `app_store_ready` is `true`.
- `build_id` matches the exact TestFlight/App Store build under review.
- all seven core screenshots exist in `manifest.json`.
- each PNG uses an accepted 6.9-inch portrait size: 1260 x 2736, 1290 x 2796, or 1320 x 2868.
- sanitized candidates created from private QA screenshots have passed human visual review before prepare.

To include screenshots in the full release-pack gate:

```bash
APP_STORE_SCREENSHOT_DIR=design/screenshots/app-store/<build-id>-ready \
  python3 scripts/check_app_store_release_pack.py
```

## Human QA Checklist

- [ ] No diagnosis, treatment, prescription, or dosage-change promise appears in screenshots.
- [ ] No private user PII, raw lab values, genotype, medication details, or family data is visible unless using a dedicated demo account.
- [ ] First screenshot shows the agent-native shell: 打开即进入小巴. If a qualified context strip is visible, it is compact and relevant; do not require or stage a fixed briefing card.
- [ ] Record and personal center screenshots are reached from 小巴 conversation entry points, not from a persistent bottom tab bar.
- [ ] Chat screenshot shows a bounded dynamic card, not raw JSON.
- [ ] Record screenshot shows quick food/water/workout entry.
- [ ] Me screenshot shows `账号与隐私` and data controls.
- [ ] Privacy screenshot matches `https://health.executor.life/privacy`.

## Output Convention

Save raw screenshots under:

`design/screenshots/app-store/<YYYYMMDD-HHMMSS>/`

Only commit screenshots when the user explicitly asks. The runbook and scripts are the durable source; screenshots are often regenerated.
