# LifeNav Web 参考体验对齐

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | S5 本批实现与本地验收通过，尚未发布 |

用户原话：「最终实现跟 https://throws-heater-beauty-even.trycloudflare.com/ 还是有差距的 继续补足差距」。

## G1 准入

裁决：PASS。延续已有个人规划工作区的计划、执行、回顾行为。用户要求继续补齐；Web 优先是本对话 Web 上下文下的实施顺序，已异步询问端偏好。现有核心的数据与权限边界不扩张。

## Discovery / G2

裁决：PASS（本批范围）。参考页确认为 LifeNav，非 AI 聊天页。只读看到完整侧栏、七天切换、今日重点与四时段同源任务；当前 Web 只有横向标签/日期输入/表单。完整十二页的媒体与结构化记录缺口也存在，明确保留，不以 UI 仿制宣称功能全部完成。来源工具包只读解包，无执行附件代码。System Map selector 不索引组件目录，回源码调查；使用项目 Python 的中央检查通过。

规格与规划合并见 [本批 tech-spec](../specs/active/2026-10-10-lifenav-web-reference-alignment.md)。无新 API/DB/自动写入；属于单 Web surface 的 Quick Flow。保持显式保存、409、epoch、备份白名单。侧栏、日期、任务与撤销均可在现有契约实现。

## 研发任务

run_path：`docs/_generated/harness-runs/5f7afccf1211.jsonl`。

root：日期与草稿撤销状态、集成、验收；frontend engineer：工作区 UI/CSS 与相关回归；独立 reviewer：固定最终 diff 的 G4。共享 main，按文件划分，禁止碰其他 dirty 文件。上一轮聊天页 Logo 改动单独保留。

## G3 / G4 / G5 / G6

G3 PASS（本批 Web 范围）；G4 GO（独立 reviewer 对当前 diff 的保存、账号隔离、历史与 CAS 审查）；G5 未部署；G6 未做线上验收。完整十二页功能对齐仍有 tech-spec 所列缺口，不宣称项目整体交付完成。

## 本批交付与证据

- 分组侧栏、首页入口、窄屏折叠、固定保存栏、七日导航和周切换；今日重点、同源四时段任务、任务锚点、周表直接添加对应日期/时段事项。
- 有界内存撤销/重做；编辑分支清除 redo；保存/重新读取成功清空历史，失败和 409 保留草稿与历史；切换账号销毁历史；写入期间禁用撤销。计时及归档失败也可撤销本次草稿更改。
- 2026-10-10 11:03 最新验证：`cd frontend && DEBUG_PRINT_LIMIT=300 npx vitest run src/components/life-navigation src/services/lifeNavigation.test.ts`，6 文件 / 32 测试通过；`npx tsc --noEmit` 通过。对应文件 ESLint 无错误，保留既有 requestEpoch cleanup 的 1 条 warning。
- `PATH="$PWD/backend/venv/bin:$PATH" ./scripts/system-map-check.sh` 通过；本批没有需要变更的架构生成结构。
- 全仓 Dossier 检查未通过：其他任务的 `2026-10-10-external-agent-record-grants.md` 缺状态/阶段字段与 G1 段；本 dossier 未被列为失败项。未修改该文件，不能据本批检查宣称全仓发布 Gate 全绿。
- 浏览器使用真实组件与明确标注的本地合成账号/API fixture，验收 1280px 桌面及 390px/320px 窄屏，无整页横向溢出；执行愿景编辑→撤销→重做→保存→重新读取，以及周表新增→今日定位→填写→保存。此 fixture 的刷新持久化不能代表生产 API 或 PostgreSQL 验证。
- 合成截图：`/tmp/lifenav-web-alignment-desktop-20261010.jpg`、`/tmp/lifenav-web-alignment-mobile-20261010.jpg`。预览 fixture 只在忽略的 node_modules 缓存中，不纳入产品代码。
- 独立审查发现的站内导航离页保护、计时/归档历史捕获、重新读取后残余派生状态均已修正并复审 GO。首页离页确认依赖现有 beforeunload，未把浏览器未显示的确认弹窗记为验收通过。
- 没有 commit、push、merge 或部署；共享工作树的其他变更保持原样。生产精确 SHA CI/部署/验收尚未执行。

统一owner固定ea86f74fe审查发现全局顶栏Link和客户端返回未受原beforeunload保护，裁决NO-GO；新增真实Navigation+workspace取消/确认/返回测试4项RED。统一离页capture guard修正后，与原导航测试共8项GREEN；新候选仍需固定SHA独立复审，不能沿用之前局部GO。取消返回恢复原route/tree，确认才允许App Router；同页hash及新标签不阻断。
