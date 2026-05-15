# 体重与腰围录入自动化路线

日期: 2026-05-15  
范围: Mobile 端体重/腰围承接页、未来设备同步优先级、所有录入型功能的产品原则。

## 第一性原理

健康轨迹 Agent 需要的是低摩擦、可审计、可重复的纵向数据, 不是更多表单。每一种移动端录入都按同一优先级设计:

1. **设备自动测量**: 传感器或外设完成测量, 用户不用打开 App。
2. **系统健康库聚合**: iOS 读 Apple Health / HealthKit, Android 读 Health Connect; 厂商 App 先把数据写入系统健康库。
3. **厂商云 API**: 适合 B2B 或已获授权的品牌, 作为系统健康库不可用时的补充。
4. **一屏手动兜底**: 只填核心数字, 保存后马上进入 Twin、Daily Plan、Trajectory。

## 本次落地

- `mobile/app/body-measurements.tsx`: 体重 + 腰围一屏录入, 显示最近值, 保存后刷新 dashboard / twin / daily-plan / trajectory。
- `mobile/services/bodyMeasurements.ts`: 封装 `/weight/records` 与 `/waist/records`。
- 首页 Daily Operating Plan 的 measurement action 如果命中 `体重/腰围/weight/waist/bmi`, 直接进入 `/body-measurements?focus=morning`。
- Record tab 增加 `体重腰围` 快捷入口。

## 自动化调研结论

### iOS: Apple Health / HealthKit 是第一入口

Apple HealthKit 原生支持 `bodyMass` 和 `waistCircumference` 两类 body measurements。体重样本使用质量单位, 腰围样本使用长度单位。对 iOS 用户, 最短路径是让智能秤/软尺厂商 App 写入 Apple Health, 我们读取 HealthKit 并做去重入库。

参考:
- https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/bodymass
- https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/waistcircumference
- https://developer.apple.com/documentation/healthkit/data_types

### Android: Health Connect 是第一入口

Health Connect 将 body measurement 作为标准类别, 官方文档列出 Weight 权限; Android 帮助文档也列出 Body Measurement 下包含 Waist circumference 和 Weight。对 Android 用户, 先接 Health Connect, 后续再按机型补 Samsung / Huawei。

参考:
- https://developer.android.com/health-and-fitness/health-connect/data-types
- https://developer.android.com/health-and-fitness/guides/health-connect/data-format
- https://support.google.com/android/answer/13770320

### 厂商 API / SDK 可用性

| 厂商/平台 | 体重 | 腰围 | 接入判断 |
|---|---:|---:|---|
| Withings API | 有, `Weight = type 1`; getmeas/measure 模型成熟 | 无明确腰围外设 | 海外可做 OAuth 云同步; 用户反馈“中国区同步不稳定”时, 不作为中国首选 |
| Garmin Health API / SDK | Health API 含 Body Composition; SDK 支持 Index Scale biometrics | 无 | B2B/企业审批与授权, 适合后续高端用户或研究项目 |
| Fitbit Web API | Get Weight Logs / Body Fat Logs; 来源含 API / Aria / AriaAir / Withings | 无 | 可作为海外补充; 中国可用性弱 |
| Huawei Health Kit | Health Kit 可读写健康数据; 数据类型包含 body weight | 未确认官方腰围开放 | 中国 Android 值得优先评估, 但需要 HMS 审核与 native 接入 |
| Samsung Health Data SDK | Body composition 支持 read/write/delete | 未确认腰围 | Android/Samsung 用户可做 native SDK; 健康用途声明不能诊断治疗 |
| Xiaomi / Zepp | 官方公开 API 更偏设备/表盘/用户 profile, 未看到稳定开放的体重云 API | 无稳定开放 API | 不作为首批直连; 走 Health Connect / Apple Health 聚合 |
| RENPHO Smart Tape | 软尺可同步 waist circumference 到 Apple Health | 有 | 腰围自动化最现实的消费级方案之一: 软尺 → RENPHO → Apple Health → 我们 |

参考:
- Withings: https://developer.withings.com/developer-guide/v3/models/measures/
- Garmin: https://developer.garmin.com/gc-developer-program/health-api/
- Garmin SDK: https://developer.garmin.com/health-sdk/overview/
- Fitbit data dictionary: https://enterprise.fitbit.com/wp-content/uploads/Fitbit-Web-API-Data-Dictionary-Downloadable-Version-2023.pdf
- Huawei Health Kit: https://developer.huawei.com/consumer/en/hms/huaweihealth/
- Samsung Health Data SDK: https://developer.samsung.com/health/data/overview.html
- Samsung data types: https://developer.samsung.com/health/data/guide/features/data-types.html
- RENPHO Smart Tape FAQ: https://renpho.com/pages/faq-for-renpho-health-app

## 产品原则: 所有录入都按“自动化梯度”建模

每个 record type 必须在功能地图里写清:

- `measurement_method`: device / system_health_store / vendor_cloud / manual / voice
- `source`: apple_health / health_connect / garmin / huawei / samsung / withings / renpho / manual
- `confidence`: sensor_direct / user_confirmed / imported / inferred
- `dedupe_key`: user_id + record_type + source + timestamp bucket + value
- `fallback_ui`: 一屏最多 1-3 个核心字段

## 后续实现建议

1. **native build 才做**: 接 HealthKit / Health Connect。需要新增 native module 或第三方稳定 SDK, 不能 OTA。
2. **先 iOS**: HealthKit 读 `bodyMass`, `waistCircumference`, `bodyFatPercentage`; 用户授权后后台/启动同步最近 30 天。
3. **再 Android**: Health Connect 读 Weight, BodyFat, Waist circumference; 三星/Huawei 作为厂商增强。
4. **腰围设备推荐**: RENPHO Smart Tape 这类能写 Apple Health 的智能软尺优先; 无开放 API 的软尺不直连。
5. **手动兜底保留**: 任何自动同步失败时, 仍要能从 Daily Plan 一点进入一屏保存。
