# Dossier: iPad 原生内部分发

| 字段 | 值 |
|---|---|
| slug | ipad-internal-release |
| 创建日期 | 2026-10-11 |
| 当前阶段 | G6 PASS，已发布内部分发包 |
| 状态 | shipped |
| 负责 | root |

## G1 准入

裁决: PASS。用户要求发布iPad版本；扩展现有Mobile健康记录、Agenda与Review执行入口，复用已有账号及观察记录，不新增健康语义或数据用途。默认按AGENTS交付可扫码安装原生包，已询问是否选择TestFlight，未擅自submit。

## G2 实现边界

裁决: PASS。现有生产商店包刻意限制iPhone，故新增显式ipad-adhoc内部分发profile、REVA_IPAD_ENABLED=1；默认商店配置仍iPhone。启用原生tablet family及四个iPad方向、允许多任务；保留iPhone portrait、账号bundle、运行时及现有API。Expo插件同步处理生成Info.plist，禁止动态配置与最终原生包漂移。不新增原生依赖、权限、模型或健康写入路径。扫码构建使用仓库mobile-local-qr.sh，完整签名和SHA校验后发布；仅profile已注册设备可安装。

## G3 验证

裁决: PASS。

配置与插件新测试先RED后GREEN，保留 `/tmp/reva-ipad-config-red.log`。配置/插件47 tests、tsc通过；扫码及签名校验57 tests通过，默认商店scope预检通过。原生生成、模拟器横竖屏及发布候选CI证据见下文。默认后台iPad模拟器；真实相机、硬件、第三方交接及实际设备安装不得冒充通过。不执行真实模型评测。

## 审查修订历史

首轮独立NO-GO指出profile未绑定最终IPA的iPad特征：同SHA的iPhone-only IPA可能被误发布。已新增require-ipad检查原生family、四向及分屏，并记录supports_ipad元数据，5项正反回归先RED后GREEN；进入fresh reviewer复审。

## G5 发布

裁决: PASS。

原候选8f30458b5的完整CI 38144526405发现OTA startup按预期拒绝原生变化(native_source_incompatible)，不得将其作为绿色发布证据。修订仅credential-free CI fidelity：保留真实publisher原样执行与BLOCKED输出，smoke只接受严格匹配的原生拒绝；export记录TEST_NATIVE_RELEASE_REQUIRED及export_performed=false，不导出、不调用gate/claim/vendor。未知上下文、runtime错误和其他phase失败仍阻断。真实trusted OTA发布入口不变，原生包只走独立扫码校验；本轮不会发OTA。新增正反测试先RED后GREEN，234 tests passed。后续修订候选完整CI和实际IPA均已通过，详见交付结果。


## G6 验收

裁决: PASS。候选绑定Release模拟器横竖屏与登录输入控件通过；最终签名IPA按require-ipad、证书/profile/SHA/digest校验通过，公网IPA摘要一致，安装页、manifest和IPA均可访问。只说明内部分发制品发布和模拟器验证；实际注册iPad安装、真实账号、相机/硬件和实际分屏操作未验证。


## G4 最终审查

裁决: GO。新独立reviewer绑定6e33e09bf49b8d09f8f3e70ca2e34620376096fd，234项Python相关测试、47项配置/插件测试、tsc、shell语法与diff-check通过。补充记录CI适配初版stdout/stderr错误的NO-GO，现严格检查真实CLI stderr且stdout为空，新增实际publisher.cli集成与错误通道/附加输出拒绝测试；真实OTA publisher/workflow完全未改。日志 `/tmp/reva-ipad-final-review-all-python.log`、`/tmp/reva-ipad-final-review-jest.log`、`/tmp/reva-ipad-final-review-tsc.log`。

## 原生包验收进展

精确候选完整CI [38145121022](https://github.com/itsoso/health-llm-driven/actions/runs/38145121022)成功；本地CI-mode 3593 passed、22 skipped、84 subtests passed。后台iPad Pro13-inch(M5)/iOS26.5 Release1.3.5(277)构建成功，最终simulator app plist含family[1,2]、四向和非fullscreen。首轮XCTest标题同名多匹配导致探针失败，原始xcresult保留；实际截图/控件坐标核对并精确firstMatch选择后，无额外诊断等待的最终XCTest通过横竖屏、实际横向frame、登录切换与密码输入框可操作检查，证据 `/tmp/reva-ipad-ui-final.xcresult`。真实账号登录、相机实拍、HealthKit硬件、分屏实际操作和已注册iPad安装未验证；不将声明配置当作这些项目通过。

## 交付结果

精确代码候选 `6e33e09bf49b8d09f8f3e70ca2e34620376096fd`，版本1.3.5(277)、production/iOS/runtime1.3.5；签名归档和导出均成功。实际IPA UIDeviceFamily=[1,2]，四种iPad方向、UIRequiresFullScreen=false、DTXcode=2660、DTPlatformVersion=26.5；签名及已安装ad-hoc profile检查通过，设备数1，supports_ipad=true，SHA256 `76a390be4c3a6060c753403fe779f4d58be702ec95272ed0c05ff3fa5dec6776`。注册设备类型/目标iPad是否在profile内尚未确认，未宣称任意iPad可安装。

经仓库mobile-local-qr.sh单次发布到不可覆盖独立目录，原IPA回执复用并重新校验，无重新造包或submit；[iPad安装页面](https://health.executor.life/mobile-install/ios/20261011-ipad-release-6e33e09bf-277/install.html)及二维码可访问，公网完整IPA摘要匹配，保留既有latest别名。源revision绑定、公共readback及结果日志 `/tmp/reva-ipad-ipa-build-result.json`、`/tmp/reva-ipad-publish-result.json`、`/tmp/reva-ipad-publish.log`；私有索引 `docs/reviews/2026-10-11-ipad-internal-release-receipt.json`。

候选相对已部署bd7的backend/frontend源码无变化，生产公开健康接口200；本次未重新部署后端、未发TestFlight或OTA。正式OTA仍因原生变化受阻，后续OTA需先完成受审的native baseline更新，不能拿本轮CI负向验证当发布授权。没有运行真实模型评测。最终文档提交为候选后继，制品仍绑定上述代码SHA。
