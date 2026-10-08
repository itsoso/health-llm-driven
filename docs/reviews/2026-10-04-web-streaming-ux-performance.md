# Web 流式阅读体验与性能验证

日期：2026-10-04（Asia/Taipei）。代码基线：本次 fetch 后的 `origin/main`，`a8853dea1207163aaa412974dddfbc050ce3eeea`。工作保留在独立 worktree，原主工作区未修改。

## 已实现

`frontend/src/components/assistant/MarkdownRenderer.tsx` 原先在每次更新时创建新的 Markdown 组件函数，React 会替换已有链接、表格等 DOM。流式回复过程中，这会丢失链接焦点和表格横向滚动位置。单段正文切换到正文加卡片时，另一条渲染分支也会卸载正文。

修改为按主题复用组件函数，统一带 key 的分段渲染树，并通过 React.memo 跳过内容、主题均未改变的正文段。正在生成的正文仍实时更新。没有增加依赖、网络请求或跨用户缓存；模块级常量只保存主题和组件函数，正文复用由各 React 组件实例管理。

## 测量范围与结果

环境：本机 macOS，Node 25.7.0，React 18.2.0，Vitest 3.2.7，jsdom，依赖由该 revision 的 package-lock 安装。

输入：固定的合成 Markdown，包括标题、链接、表格；每个场景回放 100 次连续追加文字，直接调用项目真实渲染器。分别测量纯正文增长、卡片后追加正文。没有访问真实健康记录或后端 API。耗时是测试环境中 rerender 至提交 DOM 的本地耗时，包含测试框架开销，不包含浏览器布局、绘制、网络或模型生成。

| 场景 | P50 前→后（ms） | P95 前→后（ms） | P99 前→后（ms） | 元素移除次数 前→后 |
| --- | --- | --- | --- | --- |
| 纯正文持续增长 | 3.6→2.26 | 4.83→3.19 | 5.83→3.71 | 3699→0 |
| 卡片后的正文增长 | 3.3→0.17 | 3.97→0.26 | 4.18→0.32 | 3699→0 |

这是同一输入在改动前后的单次本地回放。元素移除统计为 MutationObserver 的 removedNodes 中元素节点数，不是递归计算全部后代；耗时不是线上分位数，也不能推导线上整体提速比例。

本轮验收标准：已有链接/表格节点在追加文本及卡片完成时保留，焦点和横向滚动状态保留，已有安全渲染与卡片测试通过，本地 P95/P99 不恶化。以上条件通过。若出现正文遗漏、URL/主题更新失效、HTML 安全边界变化或相同回放下长尾持续恶化，应撤回该渲染器改动。

复现命令（仓库 frontend 目录）：

```bash
REVA_MARKDOWN_BENCH=1 npm test -- src/components/assistant/__tests__/MarkdownRenderer.streaming.test.tsx
npm test -- --maxWorkers=2
npx tsc --noEmit
npx eslint src/components/assistant/MarkdownRenderer.tsx src/components/assistant/__tests__/MarkdownRenderer.streaming.test.tsx
npm run build
```

新增回归测试在旧实现上有四项失败：三个主题的节点保留、卡片完成时的节点保留。修复后全部通过。前端完整测试：78 个文件通过，447 项通过，1 项显式跳过（按需性能回放，已另行执行）。TypeScript、改动文件 ESLint、System Map 检查及 Next.js 生产构建通过。全量测试仍有已有的 jsdom 网络及 React SSR warning；退出码为 0，不代表网络集成验证。

## 后续优化顺序

1. 检查聊天行交互的新鲜性。`ChatView.tsx::areMessageRowEqual` 忽略事件回调及 `card_actions`，源码显示存在保留旧按钮行为的风险。需先增加回调切换、卡片动作更新测试，再调整缓存边界，避免全历史消息随每个 token 重渲染。本轮未修改此处。
2. 测量仪表盘手动刷新。`dashboard/page.tsx::handleManualRefresh` 在同步调用之后固定等待 2 秒。先核实同步响应代表已完成还是仅入队，并记录真实请求的同步、查询、展示耗时；再决定去除等待或用同步状态驱动刷新。本轮没有把固定等待直接删掉，也没有声称能缩短线上 2 秒。

本轮交付边界：本地代码、回归测试和渲染回放。未提交、推送、部署；未采集生产请求分位数或完成浏览器/设备验收。
