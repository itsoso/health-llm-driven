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
2. When the demo account has a qualified pending action, risk or processing state, a compact context strip appears at the top. Tap it to open 今日计划, use 返回小巴 to return, or close the strip. It is intentionally not repeated after every response.
3. Ask 小巴健康: `帮我算我的BMI`. The answer shows an always-visible `参考来源` panel directly below the medical information.
4. Tap `中国成人体重判定标准（WS/T 428—2013）` or `成人 BMI 计算方法与分类`. The app opens the official HTTPS source from 国家卫生健康委员会 (`https://www.nhc.gov.cn/`) or CDC (`https://www.cdc.gov/bmi/`). The same panel states `健康信息用于辅助管理，不替代诊断；做医疗决定前请咨询医生。`
5. Ask 小巴健康: `今天应该先做什么健康行动？`
6. Tap the `+` button beside the input bar to photograph or select a meal image. The recognized result remains editable until it is saved.
7. Open the top-right more menu, then enter 个人中心 to manage data sources, health records, notifications and privacy.

Text chat remains available if the reviewer declines notification, location, microphone, photo, camera or HealthKit permissions. Each optional permission is requested only after the reviewer starts the related feature.

The submitted binary does not bundle an on-device inference model or expose an account-free local mode. Authenticated requests are sent only to the documented service endpoints; an unavailable or unknown session fails closed instead of producing an offline model response.

## HealthKit Use

The app requests HealthKit access only after user action. Authorized health and fitness data, including data written into Apple Health by Apple Watch, is used for health state display, timeline review and personalized action suggestions. It is not used for advertising, marketing profiles, resale or unrelated data mining.

The standard iPhone release does not include an Apple Watch companion app, Rokid integration, Siri intents or background location tracking.

## Medical Boundary

The app provides health records, trend explanation, lifestyle suggestions and action drafts. Medical calculations, ranges and health guidance show easy-to-find, clickable references from authoritative sources directly below the answer. It does not provide diagnosis, emergency triage, prescriptions, treatment plans or medication dosage changes. Users are directed to qualified clinicians for medical decisions and emergency services for urgent symptoms.

App Store Connect declaration: No. 小巴健康 is not a regulated medical device and does not claim to replace one or to diagnose, prevent or treat disease.

## Account Deletion

The in-app path is:

`个人中心 -> 账号与隐私 -> 删除账号与数据`

The request receives a unique deletion request number and a queryable status. The user is told that processing usually completes within 7 days. Completion is allowed only after the operator verifies that account data and related stored objects have been removed.

## Notes For Review

- The demo account contains sample health records, so 小巴健康 and 今日计划 show non-empty content without HealthKit authorization on the review device. The compact context strip appears only when the current data produces a qualified action, risk or processing state.
- Optional permissions are not required for the reviewer to use text conversation.
- The submitted binary is iPhone-only, portrait-only and supports iOS 16 or later.
