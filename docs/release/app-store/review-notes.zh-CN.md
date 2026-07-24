# App Store Review Notes Draft

> Demo account credentials stay outside git. At final submit, provide them through `APP_STORE_REVIEW_DEMO_ACCOUNT` and `APP_STORE_REVIEW_DEMO_PASSWORD`.
>
> App Store Connect contains the demo account, password, reviewer contact and these review notes. This checked-in draft intentionally retains placeholders so secrets are not committed; change the heading to final only after version 1.3.2 Build 235 passes the physical-iPhone G6 checklist.

## Reviewer Access

- Demo account: `[NEEDS APP STORE REVIEW DEMO ACCOUNT]`
- Password: `[NEEDS APP STORE REVIEW DEMO PASSWORD]`
- Region: China / United States compatible.

If the reviewer cannot sign in, please contact support@executor.life.

Reviewers can also use the local diet slice without any demo account. A device passcode must be enabled because the local encryption key uses the passcode-protected, device-only Keychain class.

## What To Test

1. For account-free review, tap `无需注册，立即本地使用`. The app creates a separate encrypted local vault without creating a server account.
2. Open `本地饮食记录`, enter `午饭半碗米饭两个鸡蛋`, generate the local draft, review it and confirm. The record remains available offline after relaunch.
3. Tap `从照片识别` to run the bundled Chinese-CLIP image tower on the device. The result is an approximate list of at most three candidates; it never estimates portion or nutrition and never saves before manual confirmation. The selected temporary photo copy is deleted after inference.
4. `运行模式` lets the user switch among strict local, local-first and cloud account. Switching does not silently upload or migrate existing data.
5. `本地数据管理` creates an encrypted backup and a separate recovery key, restores only into an empty vault, or permanently crypto-shreds local data.
6. To review the existing cloud product, tap `云端账号`, choose `账号密码登录`, and sign in with the demo account. The app opens directly into 小巴.
7. The 今日简报 at the top shows the current health focus. It can be collapsed and reopened.
8. Ask 小巴: `今天应该先做什么健康行动？`
9. Tap the `+` button beside the input bar to photograph or select a meal image. The recognized result remains an editable draft until the user confirms it.
10. Open the top-right more menu, then enter 个人中心 to manage data sources, health records, notifications, privacy and the mode configuration.

Text chat remains available if the reviewer declines notification, location, microphone, photo, camera or HealthKit permissions. Each optional permission is requested only after the reviewer starts the related feature.

Strict-local mode does not initialize cloud session restoration, push registration, remote configuration or Sentry delivery. Its local diet records, photo candidates, audit events and encrypted backups are not collected by the developer.

## HealthKit Use

The app requests HealthKit access only after user action. Authorized health and fitness data, including data written into Apple Health by Apple Watch, is used for health state display, timeline review and personalized action suggestions. It is not used for advertising, marketing profiles, resale or unrelated data mining.

The standard iPhone release does not include an Apple Watch companion app, Rokid integration, Siri intents or background location tracking.

## Medical Boundary

The app provides health records, trend explanation, lifestyle suggestions and action drafts. It does not provide diagnosis, emergency triage, prescriptions, treatment plans or medication dosage changes. Users are directed to qualified clinicians for medical decisions and emergency services for urgent symptoms.

App Store Connect declaration: No. 小巴 is not a regulated medical device and does not claim to replace one or to diagnose, prevent or treat disease.

## Account Deletion

The in-app path is:

`个人中心 -> 账号与隐私 -> 删除账号与数据`

The request receives a unique deletion request number and a queryable status. The user is told that processing usually completes within 7 days. Completion is allowed only after the operator verifies that account data and related stored objects have been removed.

## Notes For Review

- The demo account contains sample health records, so 今日简报 and 小巴 show non-empty content without HealthKit authorization on the review device.
- Optional permissions are not required for the reviewer to use text conversation.
- The submitted binary is iPhone-only, portrait-only and supports iOS 16 or later.
