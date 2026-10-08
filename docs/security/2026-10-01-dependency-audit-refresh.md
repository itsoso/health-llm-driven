# 2026-10-01 依赖审计刷新

PR #259 的 CI（2026-10-01）在线审计阻断以下新披露漏洞，所有分支的合并与部署被卡住。

- 后端 `pip_audit -r requirements.lock --require-hashes`：urllib3 2.7.0
  （CVE-2026-97687 / 97688 / 97689）与 PyJWT 2.14.0（CVE-2026-101918）。
- Mobile 与 Frontend `osv-npm-audit-gate.mjs`：axios 1.18.1 的 7 个 HIGH 公告。
- 本地复跑 Frontend 审计时另发现 2026-09-30 新发布的 next 16.3.4 CRITICAL 公告
  GHSA-vcvr-r3jv-pc5j（next/og ImageResponse RCE，影响 >=16.2.0 <16.3.6），同一闸门会阻断。

最小升级（均为正式版、exact pin）：

- urllib3 2.8.0：作为传递依赖在 `requirements.txt` 显式 pin，`uv pip compile`
  只升级该包并重新生成 hash lock。
- PyJWT 2.15.0：修复版本下限；未跳到 2.15.1。
- axios 1.20.0：所有 7 个公告的修复版本均为 1.20.0（1.19.0 仍受影响）。
- next / eslint-config-next 16.3.6：同小版本内的最小修复补丁。

未添加审计忽略项，未改变原生模块版本。`scripts/runtime_permission_repair.py` 仍只服务
固定 051 发布上的 PyJWT 2.14.0 事故修复，本次不修改；部署后的正常运行身份检查仍需对
新 PyJWT 安装做真实 JWT 签验。

依据：[PyJWT 公告](https://github.com/advisories/GHSA-42vr-xj54-vc7v)、
[urllib3 公告](https://github.com/advisories/GHSA-8988-9cw3-xx77)、
[axios 公告](https://github.com/advisories/GHSA-3pq3-5fj3-cg6v)、
[Next.js 公告](https://github.com/advisories/GHSA-vcvr-r3jv-pc5j)。
