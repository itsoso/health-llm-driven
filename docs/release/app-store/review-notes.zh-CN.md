# App Store Review Notes Draft

> Demo account credentials stay outside git. At final submit, provide them through `APP_STORE_REVIEW_DEMO_ACCOUNT` and `APP_STORE_REVIEW_DEMO_PASSWORD`.

## Reviewer Access

- Demo account: `[NEEDS APP STORE REVIEW DEMO ACCOUNT]`
- Password: `[NEEDS APP STORE REVIEW DEMO PASSWORD]`
- Region: China / United States compatible.

If the reviewer cannot sign in, please contact support@executor.life.

## What To Test

1. Open the app and sign in with the demo account. The app opens directly into 小巴.
2. The 今日简报 at the top shows the current health focus. It can be collapsed and reopened.
3. Ask 小巴: `今天应该先做什么健康行动？`
4. Tap the `+` button beside the input bar to photograph or select a meal image. The recognized result remains an editable draft until the user confirms it.
5. Tap the left voice button to switch to `按住说话`; tap the keyboard icon to switch back. Tap the microphone inside the input field to start or stop real-time transcription.
6. Open the top-right more menu, then enter 个人中心 to manage data sources, health records, notifications and privacy.
7. In 个人中心, open `账号与隐私 -> 隐私政策`.
8. In 个人中心, open `账号与隐私 -> 删除账号与数据` to inspect the deletion request flow. Do not confirm deletion unless the review team wants to test the request path.

Text chat remains available if the reviewer declines notification, location, microphone, photo, camera or HealthKit permissions. Each optional permission is requested only after the reviewer starts the related feature.

## HealthKit Use

The app requests HealthKit access only after user action. Authorized health and fitness data, including data written into Apple Health by Apple Watch, is used for health state display, timeline review and personalized action suggestions. It is not used for advertising, marketing profiles, resale or unrelated data mining.

The standard iPhone release does not include an Apple Watch companion app, Rokid integration, Siri intents or background location tracking.

## Medical Boundary

The app provides health records, trend explanation, lifestyle suggestions and action drafts. It does not provide diagnosis, emergency triage, prescriptions, treatment plans or medication dosage changes. Users are directed to qualified clinicians for medical decisions and emergency services for urgent symptoms.

## Account Deletion

The in-app path is:

`个人中心 -> 账号与隐私 -> 删除账号与数据`

The request receives a unique deletion request number and a queryable status. The user is told that processing usually completes within 7 days. Completion is allowed only after the operator verifies that account data and related stored objects have been removed.

## Notes For Review

- The demo account contains sample health records, so 今日简报 and 小巴 show non-empty content without HealthKit authorization on the review device.
- Optional permissions are not required for the reviewer to use text conversation.
- The submitted binary is iPhone-only, portrait-only and supports iOS 16 or later.
