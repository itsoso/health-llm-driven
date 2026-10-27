# Runtime 1.3.6 品牌变更兼容性候选

状态：静态证据、代码测试及限定的旧源码模拟器兼容验证完成；精确候选CI与生产发布仍待完成。

精确构建、来源 SHA、指纹、原始证据摘要和逐文件 pin 见同名 JSON。原始 EAS 返回保留在本机 `/tmp/exam-ota-cohort-investigation`，不提交含下载地址的完整 vendor 输出。

- 使用既有固定 EAS CLI 23.2.0，只读查询 production/iOS/runtime 1.3.6 完整已完成 cohort，共279、280、281、282；逐个 build:view 与三组 fingerprint:compare 均成功。
- 279→280：287项指纹来源中，仅既审 tooling patches 一项变化；本次不修改原 tooling pin。
- 280→281：287项中只变更 expoConfig、icon、splash-icon。配置差异为品牌名、颜色、既有权限的人类可读说明。未增加权限能力或原生模块接口；Watch plugin只改显示名，Siri plugin只改注释。相关测试、中文字符串及产品文档也只改品牌字节。
- 281→282：全部287项指纹来源一致。281→备考候选 a8cd1e7635eb697c0f0bc528382c98b3602893c3 的原生配置、模块及依赖输入无变化。

新增源码准入仅接受281提交中13个精确文件摘要；原生图标和启动图先走摘要检查，不能落入一般JS资源例外。既有279基线、runtime、环境限制、claim和发布事务不变。构建准入为279–282完整精确集合，缺少任一构建、额外未知构建（即使指纹相同）、来源或指纹变化均拒绝。

本地测试：15个新增回归先红；实现及证据路径更新后，trusted_ota、trusted_ota_publish、trusted_ota_startup 合计257通过。a8cd1e候选源码验证通过。这些只证明检查行为，不证明实际设备运行。

旧宿主验证：独立审查已核对280原生源码的模拟器Release构建、959个候选JS源文件摘要、独立npm ci及Android-only依赖差异证明。原生配置/插件/依赖与图标不变；完整候选登录页启动通过。另用同原生宿主和明确的合成只读Axios fixture验证SecureStore读取、练习组件渲染、上一题和下一题。实际原生源码、JS SHA、bundle摘要、构建失败及修复历史保存在同名JSON。先前跨目录Metro与未签名Keychain失败不计通过。

这是本地280源码模拟器宿主，不是STORE280二进制；合成数据不证明真实账号同步或服务端判分，也未把它称为精确生产OTA制品验收。逐次保存、失败重试和账号隔离另由前述应用与PostgreSQL测试覆盖。最终OTA制品仍须经可信发布器核对manifest与资源摘要，真实手机接收另行确认。

旧宿主仍保留其原生桌面名称、图标、启动画面和权限说明；OTA仅能更新JS内容，不能把品牌原生资源已更新作为承诺。最终精确候选仍须独立审查、完整CI、宿主验收和新鲜生产cohort核对。

独立280宿主依赖调查：本地指纹288源，EAS280为287源；286项逐字段一致，额外生成的`ios`目录为`bareNativeDir/hash=null`，另有voice包目录摘要不同。已核验lock固定voice 3.2.4 npm tarball的SHA512 integrity；原始包目录摘要精确等于EAS280。安装后包唯一正文变化为postinstall修改的`android/build.gradle`；在隔离副本只还原该文件，即精确恢复EAS280目录摘要，证明本次差异不来自iOS voice实现。未改构建中的依赖。生成ios目录没有被摘要覆盖，仍需核对生成工程、Pods及宿主构建来源；不能把整体指纹不同直接忽略，或将依赖比较等同于运行验收。
