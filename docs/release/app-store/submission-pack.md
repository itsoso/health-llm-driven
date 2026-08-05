# 小巴(中和知微)App Store Submission Pack · 睿为健康

Status: draft for the next App Store submission.

## App Record

| Field | Value |
|---|---|
| App Store Connect app id | `6763569720` |
| Bundle ID | `life.executor.health` |
| SKU | `life.executor.health` |
| App name | `小巴` |
| Internal product name | `中和知微`(公司:睿为健康)|
| App Store Connect primary locale | English (U.S.) record with Simplified Chinese customer-facing metadata |
| Category | Health & Fitness |
| Privacy policy URL | `https://health.executor.life/privacy` |

## Metadata Draft

### Subtitle

个人健康记录与行动助理

### Promotional Text

把 Apple Watch、HealthKit、体检报告、饮食运动记录和 AI 对话收敛到一条日常健康动线，帮助你每天完成最重要的一件健康行动。

### Description

小巴，你忠实的健康参谋——面向长期健康管理的个人健康操作系统。它把你授权同步的 Apple Health / HealthKit 数据、Apple Watch 记录、体检报告、饮食运动记录、用药和补剂信息组织成可复盘的健康时间线，并通过 AI 帮你生成日常行动建议。

打开即进入小巴。小巴对话是主入口；当存在明确待办、风险或处理状态时，顶部动态上下文条会连接到今日计划，但不会在每轮回复后重复出现。你可以通过输入栏和快捷入口完成记录，并从更多菜单进入个人中心管理数据来源、健康档案、提醒、安全与隐私。

核心能力:

- HealthKit 数据连接: 读取你授权的活动、心率、睡眠、血氧等健康数据，包括 Apple Watch 写入 Apple Health 的记录。
- 体检报告导入: 上传报告后整理关键指标，形成可追踪的健康档案。
- 快速记录: 快速记录饮食、饮水、运动、体重、血压、症状、用药和补剂。
- AI 健康分析: 基于你的授权数据和上下文生成解释、复盘和行动草稿。
- 动态健康行动: 结合实时状态和历史数据，优先给出今天的下一步，未来节奏按新记录动态调整。
- 隐私与控制: 可断开数据来源，也可在 App 内发起账号与数据删除请求。

重要说明:

小巴提供健康记录、趋势解读和生活方式建议，不提供诊断、急救分诊、处方、治疗方案或药物剂量调整。任何医疗决策请咨询医生。紧急症状请立即联系医生或当地急救服务。

### Keywords

健康记录,Apple Watch,HealthKit,体检报告,饮食记录,运动记录,睡眠,用药提醒,补剂,小巴,中和知微,健康参谋

### What's New

本版本收敛为 iPhone 上的 Agent Native 核心体验：打开即进入小巴，动态上下文条与今日计划、文字与语音输入、拍照记录、确认写入和个人中心都围绕对话完成。新增可查询的账号与数据删除请求，改为场景触发权限，并优化动态行动、流式 Markdown、图片持久化和写入回执。

## Review Notes

Use `docs/release/app-store/review-notes.zh-CN.md` as the source text for App Store Connect.

## Production Build Preflight

Standard production is iPhone-only and portrait-only. It intentionally excludes the Watch companion, Rokid integration, Siri intents and background location. Those capabilities use separate non-submission profiles.

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

Immediately before an App Store submission, run the stricter final gate. It must fail if the submission pack or review notes are still marked draft, demo credentials are still placeholders, App Store Connect credentials are unavailable, the age rating or production OTA freeze has not been confirmed, or no exact-build App Store-ready screenshot and physical-iPhone evidence set is provided:

```bash
export APP_STORE_REVIEW_DEMO_ACCOUNT="..."
export APP_STORE_REVIEW_DEMO_PASSWORD="..."
export APP_STORE_REVIEW_CONTACT_PHONE="+8613800138000"
export APP_STORE_BUILD_ID="..."
export APP_STORE_REAL_DEVICE_EVIDENCE="/secure/path/real-device-acceptance.json"
export APP_STORE_PRIVACY_RESPONSES_PUBLISHED="1"
export APP_STORE_REGULATED_MEDICAL_DEVICE_STATUS="no"
export APP_STORE_AGE_RATING_CONFIRMED="1"
export APP_STORE_PRODUCTION_OTA_FROZEN="1"

python3 scripts/check_app_store_release_pack.py \
  --final-submit \
  --screenshot-dir design/screenshots/app-store/<build-id>-ready
```

Create the external evidence file from `docs/release/app-store/real-device-acceptance.template.json`. It must refer to the exact TestFlight build and include the app version, App Store build number, production EAS build ID, source commit, IPA `DTXcode`, IPA `DTPlatformVersion`, device, iOS version and tester. The final gate requires `DTXcode >= 2600`, iOS platform major `>= 26`, and exact matches for the configured app version and `APP_STORE_BUILD_ID`. Mark every physical-iPhone check `true`, including demo login, streaming Markdown, permission-denied text fallback, both voice modes, external-audio interruption, photo persistence, image/video playback and sharing, write/correct/delete idempotency, foreground recovery, draft preservation, latest-message scrolling, privacy and deletion paths. Do not commit tester evidence containing device or account details.

Extract the toolchain values from the exact downloaded IPA, not from a local Xcode assumption:

```bash
reva_ipa_extract_dir="$(mktemp -d)"
unzip -q /secure/path/Xiaoba-<build-id>.ipa -d "$reva_ipa_extract_dir"
reva_app_plist="$(find "$reva_ipa_extract_dir/Payload" -maxdepth 2 -path '*.app/Info.plist' -print -quit)"
plutil -extract DTXcode raw -o - "$reva_app_plist"
plutil -extract DTPlatformVersion raw -o - "$reva_app_plist"
rm -rf "$reva_ipa_extract_dir"
```

The release owner copies those two outputs into the external evidence file and verifies the EAS build ID, build number and commit against the same binary before setting any final-submit confirmation.

Run the non-destructive automated subset against the installed production app first:

```bash
scripts/run_ios_real_device_acceptance.sh \
  <physical-device-udid> \
  /secure/path/XiaobaAcceptance-<build-id>.xcresult
```

This harness covers launch, authenticated Agent access, briefing interaction, foreground draft recovery, and the privacy/account-deletion entries. It does not replace the dedicated physical checks for voice, camera, sharing, health writes, correction/deletion idempotency, or completed account deletion.

## Privacy Nutrition Label

Use `docs/release/app-store/privacy-nutrition-label.draft.json` as the working source. App Store Connect remains the final source of truth after manual entry.

Before final submission, compare every App Store Connect data type and purpose with the checked-in declaration, click Publish, and set `APP_STORE_PRIVACY_RESPONSES_PUBLISHED=1` only after the published product-page preview is visible.

## Regulated Medical Device Declaration

小巴 is not a regulated medical device. It supports personal health records, trend explanation and lifestyle action drafts, but does not claim to diagnose, prevent or treat disease, replace a medical device, prescribe treatment, or determine medication dosage.

Because the app is categorized as Health & Fitness and is intended for United States availability, App Store Connect requires an explicit declaration. In `App Information -> App Store Regulations & Permits -> Regulated Medical Devices`, select `No`, save it, then set `APP_STORE_REGULATED_MEDICAL_DEVICE_STATUS=no` on the release machine. A `yes` value must stop this release and trigger a separate regulatory review.

Official requirement: https://developer.apple.com/help/app-store-connect/manage-app-information/declare-regulated-medical-device-status

## Age Rating Confirmation

The release owner must open the saved App Store Connect age-rating questionnaire for version 1.3.3, review it against the production capability surface and save any required answers. Do not infer answers from the repository or set the confirmation before the saved questionnaire is visible. After this manual review, set `APP_STORE_AGE_RATING_CONFIRMED=1` on the release machine.

## Production OTA Freeze

From the moment the 1.3.3 candidate is built until App Review and public G6 verification finish, do not publish an EAS Update to the production channel. This keeps the reviewed JavaScript bundle identical to the tested candidate. The release owner records the freeze window and then sets `APP_STORE_PRODUCTION_OTA_FROZEN=1`; lift the freeze only after the approved binary is public and G6 passes.

## Screenshot Set

Build 226 historical App Store Connect set (uploaded and API-verified on 2026-07-15):

1. Agent home and today's priority.
2. Expanded today action and decision basis.
3. Agent conversation with rendered Markdown and message timestamps.
4. Mobile-first health record entry points.
5. Health archive import.

The uploaded set uses the demo account, contains no private user health data, and targets `APP_IPHONE_67` at 1290 x 2796. The settings screenshot containing the demo login identifier and the privacy-policy screenshot were validated locally but intentionally excluded from marketing assets.

The release target is version 1.3.3 Build 241 or later. Version 1.3.2 Build 240
and the Build 226 screenshots are historical evidence only and cannot satisfy
the final gate. Record the newly produced EAS build ID, source commit and IPA
metadata in the external evidence file, then capture or explicitly re-verify
the required screenshot set against that exact candidate before submission.

Use `docs/release/app-store/screenshot-runbook.md`. Required first pass:

1. Xiaoba: open directly into 小巴, with today briefing and suggested next action visible.
2. Chat: AI conversation with dynamic UI card.
3. Record: fast food/water/workout recording opened from the conversation entry points.
4. Profile: personal center / data connections and health profile.
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
- [ ] App Privacy answers exactly match `privacy-nutrition-label.draft.json`, have been published, and the product-page preview has been reviewed.
- [ ] App Information declares `Regulated Medical Devices: No` for this release; any `Yes` determination stops submission pending regulatory review.
- [ ] The release owner has reviewed and saved the current App Store Connect age-rating questionnaire, then set `APP_STORE_AGE_RATING_CONFIRMED=1`.
- [ ] Production-channel OTA is frozen for the candidate through App Review and public G6 verification, then `APP_STORE_PRODUCTION_OTA_FROZEN=1` is set.
- [ ] The exact IPA reports `DTXcode >= 2600` and `DTPlatformVersion` major `>= 26`; both values are copied into same-build real-device evidence.
- [ ] A physical iPhone has passed demo login, briefing expand/collapse, Agent text conversation, text fallback after denied optional permissions, real-time dictation toggle, hold-to-talk send/cancel/text conversion, camera/photo persistence, WeChat/Xiaohongshu share handoff, confirmed database write, personal-center/privacy and deletion-request status checks.
- [ ] Only after the same-build physical-iPhone run and final screenshot review pass, change the submission pack status to `ready for App Store submission` and remove `Draft` from the Review Notes heading.
- [ ] `docs/release/app-store/dependency-risk-review.md` still matches a fresh production dependency audit.
- [ ] The release machine has `APP_STORE_REVIEW_DEMO_ACCOUNT`, `APP_STORE_REVIEW_DEMO_PASSWORD`, and `APP_STORE_REVIEW_CONTACT_PHONE`, or a human has filled the equivalent Review Detail fields in App Store Connect.
