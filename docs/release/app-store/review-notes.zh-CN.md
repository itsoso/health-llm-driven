# App Store Review Notes

> Demo account credentials stay outside git. At final submit, provide them through `APP_STORE_REVIEW_DEMO_ACCOUNT` and `APP_STORE_REVIEW_DEMO_PASSWORD`.
>
> App Store Connect contains the demo account, password, reviewer contact and these review notes. Placeholders remain intentionally so secrets are not committed. Candidate 1.3.6 (282), source `83876750fcbb404255b7439482688fee82a490d4`, uses the owner-authorized simulator-risk policy in `docs/governance/simulator-review-acceptance.md`; unverified physical checks remain explicitly recorded outside Git, not represented as passes. Final submission remains pending notification-fix deployment and online acceptance.
>
> Paste only `## What To Test` through the end into ASC Notes (maximum 4,000 UTF-8 bytes). Enter credentials and contact details in their separate fields; do not paste this preface.

## Reviewer Access

- Demo account: `[NEEDS APP STORE REVIEW DEMO ACCOUNT]`
- Password: `[NEEDS APP STORE REVIEW DEMO PASSWORD]`
- Region: China / United States compatible.

If the reviewer cannot sign in, please contact support@executor.life.

## What To Test

1. Choose `账号密码登录` and sign in with the demo account. The app opens directly into 小气候.
2. If a pending action, risk or processing state exists, tap the top context strip for 今日计划, use 返回小气候 to return, or close it.
3. Ask `帮我算我的BMI`. First use shows a separate AI data-sharing disclosure. Declining preserves the draft without AI transmission. After permission, medical answers display `参考来源`.
4. Open 国家卫生健康委员会 (https://www.nhc.gov.cn/) or CDC (https://www.cdc.gov/bmi/) under 参考来源. The answer states: 健康信息用于辅助管理，不替代诊断；做医疗决定前请咨询医生。
5. Ask 小气候: `今天应该先做什么健康行动？`
6. Tap the `+` button beside the input bar to photograph or select a meal image. The recognized result remains editable until it is saved.
7. Open the top-right more menu -> 个人中心 for records, data sources, notifications and privacy.

Text chat remains available after declining notification, location, microphone, photo, camera or HealthKit permissions. Optional permissions are requested only when starting the related feature.

AI requests require authentication. The app does not bundle an on-device inference model or provide an account-free local mode.

## Third-Party AI Permission

Before the first AI request, a separate disclosure names Alibaba Cloud Model Studio (Qwen, speech and image models), submitted text, selected images/files/audio and relevant health/profile/conversation context. Apple system speech recognition may run on-device or on Apple's servers and is also disclosed. OS permissions remain separate.

Login does not grant AI sharing permission. Declining keeps non-AI records, privacy controls and account deletion available. Manage or withdraw permission in `设置 -> AI 数据共享`. Withdrawal blocks subsequent AI dispatches, but cannot recall sent data. Re-enabling requires explicit agreement.

## HealthKit Use

HealthKit access requires user action. Authorized health/fitness data, including Apple Watch records in Apple Health, supports health displays, timelines and personalized suggestions, never advertising, marketing profiles, resale or unrelated data mining.

No Watch companion, Rokid integration or Siri intents are included. Optional daily GPS journeys require daily opt-in, retention consent and OS location permission; background location is used only for an enabled journey. This is not required for chat or records.

## Medical Boundary

Health records, trends and lifestyle suggestions are supported. Medical calculations and guidance show clickable authoritative references below the answer. The app does not provide diagnosis, emergency triage, prescriptions, treatment plans or medication dosage changes. Medical decisions require a clinician; urgent symptoms require emergency services.

App Store Connect declaration: No. 小气候 is not a regulated medical device and does not claim to replace one or to diagnose, prevent or treat disease.

## Account Deletion

The in-app path is:

`个人中心 -> 账号与隐私 -> 删除账号与数据`

Users receive a deletion request number, queryable status and an expected 7-day timeframe. Completion requires verifying removal of account data and stored objects.

## Notes For Review

- The demo account has sample health records for 小气候 and 今日计划 without HealthKit authorization. The context strip appears for pending actions.
- Optional permissions are not required for the reviewer to use text conversation.
- The submitted binary is iPhone-only, portrait-only and supports iOS 16 or later.
