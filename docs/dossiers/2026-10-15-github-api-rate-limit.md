# GitHub API 限流优化

| Field | Value |
| --- | --- |
| status | building |
| current_stage | G3 verification / G4 review |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 Scope admission

裁决: PASS。用户要求落实限流优化，并调查付费提额。保留发布鉴权、精确主干CI、单发布owner、回执和不备份要求。此变更不自动授权购买套餐，不创建GitHub App或读取/复制现有秘密，不调用真实模型或用户健康数据。

## 原因与范围

生产匿名API快照limit60/used53/remaining7。full gate合成响应计数5 GET；各阶段实时复核不能直接删除。Actions env-i使主要校验没有GH_TOKEN，生产隔离环境同样缺少受控来源。429无Retry-After原先1秒重试。详见 docs/ops/github-relay.md 调查。

实现：Actions内置只读token仅通过stdin传入canonical gate；Git子进程仍在无token隔离环境内先物化源码。OTA publisher只向gate子进程传递token，不进入Expo进程。生产支持独立固定root-owned文件提供仓库绑定、带过期时间的只读API凭据，非法配置失败不降级；未配置仍保留原兼容路径，但不能声称生产认证已启用。403/429退出时返回脱敏not_before，不在特权进程里短间隔重试。不缓存或放宽最终授权。

## 验证与发布边界

- Actions传递RED：新增测试先失败；release workflow +真实shell凭据隔离测试78通过。
- gate初轮RED14、GREEN209通过；生产固定文件支持与OTA集成仍验证中。
- 尚未配置GitHub App凭据，生产认证未启用。用户已被询问现有App状态，禁止在聊天收集Token/私钥。
- 旧发布2fbc的外部操作身份交接仍未确认；本任务不重放旧rotation，不推动未知归属的发布。
- 付费调查：官方未列按请求量购买的API流量包；Enterprise Cloud特定认证请求有更高额度，匿名及二级限流不因此解除。当前优先免费认证，无购买动作。

初轮OTA集成267 passed / 1既有skip；发布workflow shell语法30个step通过。既有workflow已共用concurrency group，此次不重复加锁。自动GitHub App签发/刷新和跨进程冷却调度不在本次候选中，生产认证需受控配置及真实只读API验收，不把本地合成结果称为线上提额成功。

最终固定文件凭据测试230 passed，先RED12；相关release/OTA/admission集成476 passed / 1既有skip。Dossier一致性、System Map、diff检查通过。固定本地提交后做独立G4；未push、未部署、未启用真实生产凭据。

固定候选9161f46d7独立G4 GO，但完整CI-mode发现retained-TestFlight无凭据启动测试适配器仍匹配旧gate命令（1840 passed / 1 failed / 10 skipped），不能发布。仅同步测试适配器精确剔除新的认证断言与stdin gate命令，保留逐行唯一匹配及其他物化边界；增加认证断言删除/变更必须失败的回归。生产workflow与鉴权实现未放宽。修复后重新绑定候选做独立审查与完整CI-mode。
