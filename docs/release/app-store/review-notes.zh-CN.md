# App Store Review Notes Draft

> Demo account seeded on production 2026-07-03 and verified via live API (login + 今日/时间线/工件 non-empty). Real credentials live OUTSIDE git: docs/release/app-store/demo-credentials.local.md (gitignored) + APP_STORE_REVIEW_DEMO_ACCOUNT/PASSWORD env at final submit.

## Reviewer Access

- Demo account: `[NEEDS APP STORE REVIEW DEMO ACCOUNT]`
- Password: `[NEEDS APP STORE REVIEW DEMO PASSWORD]`
- Region: China / United States compatible.

If the reviewer cannot sign in, please contact support@executor.life.

## What To Test

1. Open the app and sign in with the demo account.
2. Go to `今日` to see the current health summary and next suggested action.
3. Go to `阿衡` and ask: `今天应该先做什么健康行动？`
4. Go to `记录` and record a simple water or exercise entry.
5. Go to `我 -> 数据连接` to view Apple Health and data source controls.
6. Go to `我 -> 健康档案 -> 导入体检报告` to see report import entry.
7. Go to `我 -> 账号与隐私 -> 隐私政策` to view privacy explanation.
8. Go to `我 -> 账号与隐私 -> 删除账号与数据` to see the in-app deletion request flow. Do not confirm deletion unless the review team wants to test the request path.

## HealthKit Use

The app requests HealthKit access only after user action. HealthKit data is used for health state display, timeline review, reminders, and personalized health action suggestions. It is not used for advertising, marketing profiles, resale, or unrelated data mining.

## Medical Boundary

The app provides health records, trend explanation, lifestyle suggestions, and action drafts. It does not provide diagnosis, emergency triage, prescriptions, treatment plans, or medication dosage changes. The app reminds users to consult doctors for medical decisions and emergency services for urgent symptoms.

## Account Deletion

The account and data deletion entry is inside the app:

`我 -> 账号与隐私 -> 删除账号与数据`

The request is recorded in an auditable backend workflow. The user is told that processing usually completes within 7 days.

## Notes For Review

- The demo account is pre-loaded with sample health data, so `今日`, `时间线`, and `阿衡` show non-empty content **without requiring HealthKit authorization on the review device**.
- HealthKit / Apple Watch sync is optional and additive; the app is fully usable from the demo account's pre-loaded records.
- Apple Watch and iPhone HealthKit behavior should be tested on physical devices when possible (HealthKit cannot return data in the simulator).
