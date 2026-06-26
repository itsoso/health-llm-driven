# `design/` —— Claude Design ↔ Claude Code 的共享真相

Claude Design(claude.ai 的设计会话)和 Claude Code(仓库内的工程会话)**互不共享记忆**,唯一的接口是产物。
这个目录就是那个接口:**别在两个聊天框之间手工搬运 blob,东西都过这里,git 是集成层。**

```
design/
├── README.md          # 本文件:回路说明 + 分工
├── fixtures/          # Code→Design 的真实数据(export_design_fixture.py 产出)
│   └── SAMPLE-user.json   # 字段结构示例(假值,可提交)
└── screenshots/       # 真实 App 截图(ground truth,给 Design 对齐布局/信息层级)
```

> 设计方向/产品范围的权威在 [`docs/prd/reva-personal-health-os-prd.md`](../docs/prd/reva-personal-health-os-prd.md)。
> 本目录只管 Design↔Code 的**数据与产物交换**,不复述 PRD。

---

## 回路

```
Design  →  在真实数据上做视觉探索 / 信息层级 / 配色排版(它最强)
   │ 产物落 design/(HTML 文件 或 Pencil .pen),别停留在 claude.ai 沙箱里的 .dc.html
   ▼
Code   →  ① 渲染+截图验证  ② 和真实 App 并排 diff  ③ 翻译成 mobile/ 真 RN 组件
   │      ④ 模拟器/真机跑真账号截真图 → 回填 screenshots/
   ▼
模拟器/真机截图 = 唯一 ground truth(HTML mock 不算数)
```

## 分工

| 角色 | 干什么 |
|---|---|
| **Claude Design** | 视觉探索、信息层级、配色排版。读 `fixtures/` 的真数据,读 `screenshots/` 对齐真实布局。 |
| **Claude Code** | 拉真数据(`export_design_fixture.py`)、渲染/diff 设计产物、翻成 `mobile/` 真 RN、跑模拟器/真机截图。 |

## 工作流

### 1. Code→Design:导真实数据(每轮设计前刷新)

```bash
# 在 prod 上跑(本地 SQLite 多数账号是空的)
ssh root@39.98.206.178 "cd /opt/health-app/backend && source venv/bin/activate && \
  python3 scripts/export_design_fixture.py --user 3" > design/fixtures/user3.json
```

产出含:`persona`(年龄/性别/城市)+ `active_medications` + `health_problems` +
`headline`(原型写死的"就绪度86/LDL3.8/AQI62"对应的真值)+ 完整 14 分区 `twin`。
把 `user3.json` 贴进 Design 会话,告诉它"按这份真值重构 data-layer"。

### 2. Design→Code:产物落地

Design 把设计存成 `design/reva-mobile.html`(或 Pencil `.pen`)提交进来。
Code 即可渲染、截图、和真实 App diff,并翻译成 `mobile/` 的 RN 组件。

### 3. Code→Design:真实 App 截图回填

Code 跑真机(模拟器构建被设备专用 Rokid 框架挡死,见 CLAUDE.md / 工程记忆)截各屏,
放进 `screenshots/`,供 Design 下一轮对齐真实信息层级。

---

## ⚠️ 隐私

`fixtures/` 里的真实导出含 **Tier-5 健康数据 + PII**。
`.gitignore` 已挡掉 `design/fixtures/*.json`(只放行 `SAMPLE-*`)——
**真实 fixture 留在本地,绝不提交进仓库。**
