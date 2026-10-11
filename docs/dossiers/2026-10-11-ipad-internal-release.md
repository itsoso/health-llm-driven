# Dossier: iPad 原生内部分发

| 字段 | 值 |
|---|---|
| slug | ipad-internal-release |
| 创建日期 | 2026-10-11 |
| 当前阶段 | G3 验证中 |
| 状态 | building |
| 负责 | root |

## G1 准入

裁决: PASS。用户要求发布iPad版本；扩展现有Mobile健康记录、Agenda与Review执行入口，复用已有账号及观察记录，不新增健康语义或数据用途。默认按AGENTS交付可扫码安装原生包，已询问是否选择TestFlight，未擅自submit。

## G2 实现边界

裁决: PASS。现有生产商店包刻意限制iPhone，故新增显式ipad-adhoc内部分发profile、REVA_IPAD_ENABLED=1；默认商店配置仍iPhone。启用原生tablet family及四个iPad方向、允许多任务；保留iPhone portrait、账号bundle、运行时及现有API。Expo插件同步处理生成Info.plist，禁止动态配置与最终原生包漂移。不新增原生依赖、权限、模型或健康写入路径。扫码构建使用仓库mobile-local-qr.sh，完整签名和SHA校验后发布；仅profile已注册设备可安装。

## G3 验证

配置与插件新测试先RED后GREEN，保留 `/tmp/reva-ipad-config-red.log`。配置/插件47 tests、tsc通过；扫码及签名校验57 tests通过，默认商店scope预检通过。后续记录原生生成、模拟器横竖屏及发布候选CI证据。默认后台iPad模拟器；真实相机、硬件、第三方交接及实际设备安装不得冒充通过。不执行真实模型评测。

## G4 独立裁决

首轮独立NO-GO指出profile未绑定最终IPA的iPad特征：同SHA的iPhone-only IPA可能被误发布。已新增require-ipad检查原生family、四向及分屏，并记录supports_ipad元数据，5项正反回归先RED后GREEN；进入fresh reviewer复审。

## G5 发布

尚未构建或发布IPA。

## G6 验收

待候选原生包与分发地址验证。
