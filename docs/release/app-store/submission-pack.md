# 小巴(中和知微)App Store Submission Pack · 睿为健康

Status: draft for the next App Store submission.

## App Record

| Field | Value |
|---|---|
| App Store Connect app id | `6763569720` |
| Bundle ID | `life.executor.health` |
| SKU | `life.executor.health` |
| App name | `小巴` |
| Internal product name | `中和知微`(公司:睿为健康;内部代号 HealthPilot)|
| Primary language | Simplified Chinese |
| Category | Health & Fitness |
| Privacy policy URL | `https://health.executor.life/privacy` |

## Metadata Draft

### Subtitle

个人健康记录与行动助理

### Promotional Text

把 Apple Watch、HealthKit、体检报告、饮食运动记录和 AI 对话收敛到一条日常健康动线，帮助你每天完成最重要的一件健康行动。

### Description

小巴是面向长期健康管理的个人健康操作系统。它把你授权同步的 Apple Health / HealthKit 数据、Apple Watch 记录、体检报告、饮食运动记录、用药和补剂信息组织成可复盘的健康时间线，并通过 AI 帮你生成日常行动建议。

你可以在“今日”看到当前最重要的健康行动，在“小巴”里用对话追问和执行记录，在“记录”里快速记录饮水、饮食、运动、体重、血压、症状、用药和补剂，在“我”里管理数据来源、健康档案、提醒、安全与隐私。

核心能力:

- HealthKit / Apple Watch 自动同步: 读取你授权的活动、心率、睡眠、血氧等健康数据。
- 体检报告导入: 上传报告后整理关键指标，形成可追踪的健康档案。
- 快速记录: 快速记录饮食、饮水、运动、体重、血压、症状、用药和补剂。
- AI 健康分析: 基于你的授权数据和上下文生成解释、复盘和行动草稿。
- 7 天健康运行时: 结合实时状态和历史数据，生成提醒、复盘和下一步建议。
- 隐私与控制: 可断开数据来源，也可在 App 内发起账号与数据删除请求。

重要说明:

小巴提供健康记录、趋势解读和生活方式建议，不提供诊断、急救分诊、处方、治疗方案或药物剂量调整。任何医疗决策请咨询医生。紧急症状请立即联系医生或当地急救服务。

### Keywords

健康记录,Apple Watch,HealthKit,体检报告,饮食记录,运动记录,睡眠,用药提醒,补剂,小巴,中和知微,健康守护者

### What's New

本版本重构了移动端核心动线: 今日、小巴、记录、我。新增 App 内账号与数据删除请求入口，更新隐私政策说明，并优化 HealthKit、体检导入、快速记录和复盘入口。

## Review Notes

Use `docs/release/app-store/review-notes.zh-CN.md` as the source text for App Store Connect.

## Production Build Preflight

Before triggering a production iOS build or submit, run the no-network config gate:

```bash
python3 scripts/check_ios_app_store_submission.py
```

Immediately before upload/submit, require local App Store Connect API credentials as well:

```bash
python3 scripts/check_ios_app_store_submission.py --require-asc-credentials
```

The production binary path remains EAS production build with App Store Connect auto-submit. QR install is the default for local mobile distribution, but App Store submission requires the production EAS/App Store Connect path.

## Final Submit Gate

The default release-pack check validates repo materials that do not require human secrets or fresh screenshots:

```bash
python3 scripts/check_app_store_release_pack.py
```

The adapted review checklist is `docs/release/app-store/adapted-review-checklist.md`. It is included in the release-pack gate and maps operational App Review risks to automated and manual checks.

Immediately before an App Store submission, run the stricter final gate. It must fail if demo credentials are still placeholders, App Store Connect credentials are unavailable, or no App Store-ready screenshot set is provided:

```bash
export APP_STORE_REVIEW_DEMO_ACCOUNT="..."
export APP_STORE_REVIEW_DEMO_PASSWORD="..."
export APP_STORE_REVIEW_CONTACT_PHONE="+8613800138000"

python3 scripts/check_app_store_release_pack.py \
  --final-submit \
  --screenshot-dir design/screenshots/app-store/<build-id>-ready
```

## Privacy Nutrition Label

Use `docs/release/app-store/privacy-nutrition-label.draft.json` as the working source. App Store Connect remains the final source of truth after manual entry.

## Screenshot Set

Use `docs/release/app-store/screenshot-runbook.md`. Required first pass:

1. Today: next best health action.
2. Chat: AI conversation with dynamic UI card.
3. Record: fast food/water/workout recording.
4. Me: data connections and health profile.
5. Privacy: account deletion path.

Candidate screenshot sets are not App Store-ready unless `manifest.json` marks them as `demo` or `sanitized` and the PNGs match accepted 6.9-inch portrait dimensions.

Use `scripts/prepare_app_store_screenshots.py` to convert a raw demo/sanitized capture into a ready set before upload:

```bash
python3 scripts/prepare_app_store_screenshots.py \
  design/screenshots/app-store/<build-id>-raw \
  design/screenshots/app-store/<build-id>-ready \
  --size 1290x2796
```

If the source screenshots came from a private QA run, generate a review-required sanitized candidate first:

```bash
python3 scripts/sanitize_app_store_screenshots.py \
  design/screenshots/app-store/<private-build-id> \
  design/screenshots/app-store/<build-id>-sanitized
```

Then visually review every PNG and run prepare with explicit confirmation:

```bash
python3 scripts/prepare_app_store_screenshots.py \
  design/screenshots/app-store/<build-id>-sanitized \
  design/screenshots/app-store/<build-id>-ready \
  --size 1290x2796 \
  --confirm-sanitized-reviewed
```

## Official Requirements Mapped

- Apple account deletion support says deletion must be easy to find, usually in account settings, and users must be kept informed if deletion takes time.
- Apple screenshot specs require one to ten screenshots per selected device size; iPhone 6.9-inch portrait sizes include 1260 x 2736, 1290 x 2796, or 1320 x 2868 pixels.
- Apple Review Guidelines 5.1.3 treat health, fitness, and medical data as especially sensitive and prohibit advertising/marketing/data-mining uses outside health management or permitted research.
- Apple Review Guidelines 1.4 scrutinize medical apps that provide inaccurate health information or imply diagnosis/treatment without support.

## Submission Gate

Do not submit until:

- [ ] `python3 scripts/check_app_store_release_pack.py` passes.
- [ ] `docs/release/app-store/adapted-review-checklist.md` has been reviewed for any new route, dynamic card, payment, permission, HealthKit, or medical-boundary change.
- [ ] `python3 scripts/check_app_store_release_pack.py --final-submit --screenshot-dir design/screenshots/app-store/<build-id>-ready` passes on the release machine.
- [ ] `python3 scripts/check_ios_app_store_submission.py --require-asc-credentials` passes on the release machine.
- [ ] Any sanitized candidate generated from private QA screenshots has passed human visual review before prepare.
- [ ] Candidate screenshots exist under `design/screenshots/app-store/<build-id>-ready/` and pass:
      `APP_STORE_SCREENSHOT_DIR=design/screenshots/app-store/<build-id>-ready python3 scripts/check_app_store_release_pack.py`.
- [ ] Privacy policy URL is publicly reachable: `curl -fsSI https://health.executor.life/privacy`.
- [ ] A production IPA or EAS build is visible in App Store Connect.
- [ ] The release machine has `APP_STORE_REVIEW_DEMO_ACCOUNT`, `APP_STORE_REVIEW_DEMO_PASSWORD`, and `APP_STORE_REVIEW_CONTACT_PHONE`, or a human has filled the equivalent Review Detail fields in App Store Connect.
