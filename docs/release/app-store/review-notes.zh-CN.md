# App Store Review Notes Draft

> Demo account credentials stay outside git. At final submit, provide them through `APP_STORE_REVIEW_DEMO_ACCOUNT` and `APP_STORE_REVIEW_DEMO_PASSWORD`.
>
> App Store Connect contains the demo account, password, reviewer contact and these review notes. This checked-in draft intentionally retains placeholders so secrets are not committed; change the heading to final only after the exact version 1.3.3 EAS candidate passes the physical-iPhone G6 checklist.

## Reviewer Access

- Demo account: `[NEEDS APP STORE REVIEW DEMO ACCOUNT]`
- Password: `[NEEDS APP STORE REVIEW DEMO PASSWORD]`
- Region: China / United States compatible.

If the reviewer cannot sign in, please contact support@executor.life.

## What To Test

1. Choose `账号密码登录` and sign in with the demo account. The app opens directly into 小巴健康.
2. A compact context strip appears for qualified pending actions, risks or processing states. Tap it to open 今日计划, use 返回小巴 to return, or close it. It does not repeat after every response.
3. Ask 小巴健康: `帮我算我的BMI`. On first use, read the separate AI data-sharing disclosure and choose whether to allow sharing. Declining preserves the draft and does not transmit it to an AI provider. After explicit permission, the answer shows an always-visible `参考来源` panel directly below the medical information.
4. Tap `中国成人体重判定标准（WS/T 428—2013）` or `成人 BMI 计算方法与分类`. The app opens the official HTTPS source from 国家卫生健康委员会 (`https://www.nhc.gov.cn/`) or CDC (`https://www.cdc.gov/bmi/`). The same panel states `健康信息用于辅助管理，不替代诊断；做医疗决定前请咨询医生。`
5. Ask 小巴健康: `今天应该先做什么健康行动？`
6. Tap the `+` button beside the input bar to photograph or select a meal image. The recognized result remains editable until it is saved.
7. Open the top-right more menu, then enter 个人中心 to manage data sources, health records, notifications and privacy.

Text chat remains available after declining notification, location, microphone, photo, camera or HealthKit permissions. Optional permissions are requested only when starting the related feature.

The app does not bundle an on-device inference model or expose an account-free local mode. Requests require authentication and use documented endpoints; unknown or unavailable sessions fail closed.

## Third-Party AI Permission

Before the first AI request, a separate disclosure names Alibaba Cloud Model Studio (Qwen, speech and image models), submitted text, selected images/files/audio and relevant health/profile/conversation context. Apple system speech recognition may run on-device or on Apple's servers and is also disclosed. OS permissions remain separate.

Login does not grant AI sharing permission. Declining keeps non-AI records, privacy controls and account deletion available. Manage or withdraw permission in `设置 -> AI 数据共享`. Withdrawal blocks subsequent AI dispatches, but cannot recall sent data. Re-enabling requires explicit agreement.

## HealthKit Use

HealthKit access requires user action. Authorized health/fitness data, including Apple Watch records in Apple Health, supports health displays, timelines and personalized suggestions, never advertising, marketing profiles, resale or unrelated data mining.

The standard iPhone release does not include an Apple Watch companion app, Rokid integration, Siri intents or background location tracking.

## Medical Boundary

The app provides health records, trend explanation, lifestyle suggestions and action drafts. Medical calculations, ranges and health guidance show easy-to-find, clickable references from authoritative sources directly below the answer. It does not provide diagnosis, emergency triage, prescriptions, treatment plans or medication dosage changes. Users are directed to qualified clinicians for medical decisions and emergency services for urgent symptoms.

App Store Connect declaration: No. 小巴健康 is not a regulated medical device and does not claim to replace one or to diagnose, prevent or treat disease.

## Account Deletion

The in-app path is:

`个人中心 -> 账号与隐私 -> 删除账号与数据`

The request receives a unique deletion request number and a queryable status. The user is told that processing usually completes within 7 days. Completion is allowed only after the operator verifies that account data and related stored objects have been removed.

## Notes For Review

- The demo account has sample health records for 小巴健康 and 今日计划 without HealthKit authorization. The context strip requires a qualified action, risk or processing state.
- Optional permissions are not required for the reviewer to use text conversation.
- The submitted binary is iPhone-only, portrait-only and supports iOS 16 or later.
