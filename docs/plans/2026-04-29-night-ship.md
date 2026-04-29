# 2026-04-29 夜战 Ship 归档

> **战果**: 20 个 commit 一夜上线 · 测试 1145 → 1201 (+56 零回归) · 健康度 37/60 PASS · OTA 17 次 · 生产部署 12 次 · 最终线上 commit **`cf6ed09`**

---

## 一、按功能分类

### A. STRATEGY 阶段 1-4 v1 完整 ship

| Commit | 范围 | 测试 |
|---|---|---|
| `acf5c4e` | 断舍离清理 — 删除 12 类支线业务 + 11 处 STALE | — |
| `1e40478` | tool_call_validator 中间件（6 工具 + bypass-safe） | +38 |
| `571e372` | set_caller 补全 + 4 处 raw OpenAI client 重构 | — |
| `4c93aeb` | Open-Loop Manager v1（plan_deviation + mobile 反馈） | +24 |
| `17c54f7` | Clinical Journal v1 收口（briefing SOAP + specialist context） | +9 |
| `ce741f0` | Doctor Weekly Report v1（Telegram 版激活） | +11 |

### B. UI/UX 修复

| Commit | 修什么 |
|---|---|
| `4a4e33d` | 首页键盘遮挡（offset 0→90） |
| `c79b631` | 聊天三 bug — 新建按钮 hitSlop / 历史加载态 / 语音 focus |
| `73abb04` | 首页卡片可收缩 + TodayCoach 按钮溢出 |
| `6c16c6e` | 强化 collapse 交互 — chevron 圆形按钮 + 整卡片可点 |
| `3c93de1` | alertBanner 去重 + DataFreshness 默认收起 + 后台续接对话 |
| `5b68b4f` | 隐藏 tool_call 技术文本 "🔧 health_record (第1轮)" |
| `2f6fbf7` | TodayCoach 按钮文字溢出 — 拆 "建议段落 + 短 CTA" |
| `f1a7b96` | keyboard offset 改成 `useSafeAreaInsets` 动态 |
| `7c72ebc` | 语音转文字不自动弹键盘 + 按钮文案"查看详情" |

### C. 后端路径/数据 bug

| Commit | 修什么 |
|---|---|
| `269b267` | exercise 记录 404 — `/exercise/records` → `/daily-health/exercise` |
| `f4f88ef` | rhinitis 记录路径 — 症状计数转 illness_episode |
| `737e0a1` | Twin 数据新鲜度标签 — STRATEGY 弱点 A |
| `cf6ed09` | 线上 500 双 bug — action_cards migration + data-health tz |

---

## 二、明早验证清单（按优先级）

### ⭐ 必做（5 分钟）

- [ ] 冷启 TestFlight App **2 次**（第一次下载 bundle，第二次应用）
- [ ] 看 Telegram 收 **09:15 Doctor weekly 首推**，严格 check 合规 tone（"不构成医疗建议" 标注在；关注点措辞非诊断性）

### 🟡 用户侧验证

- [ ] **键盘空白**：点输入框 → 软键盘紧贴输入框（过去 offset 硬编码 90 多留空白）
- [ ] **"记录十个俯卧撑"**：AI 应回 "已记录 …"，不是"操作未成功"
- [ ] **"刚打了 3 个喷嚏鼻塞 5 分"**：AI 应回 "已记录鼻炎发作"
- [ ] **首页 TodayCoach 按钮**：不再溢出屏幕，按钮文案变"查看详情"
- [ ] **首页 3 卡片 collapse**：点 chevron 圆形按钮可收起
- [ ] **语音输入后不弹键盘**：按住说话松手 → 文字填入 → 软键盘不自动弹，可直接点右侧发送
- [ ] **App 后台回来续接对话**：AI 流式响应中切后台 → 回来消息完整（服务端继续跑，客户端重拉）
- [ ] **历史聊天加载错误态**：关 WiFi 点历史 → 显示"加载失败 + 重试"而非永远转圈

### 🟢 SQL 抽查（观察期数据）

```sql
-- 1. Open-Loop Manager 07:00 跑
SELECT kind, user_action, COUNT(*)
FROM open_loop_history
WHERE sent_at > NOW() - INTERVAL '1 day'
GROUP BY 1, 2;

-- 2. Clinical Journal briefing SOAP 07:30 跑
SELECT theme, COUNT(*)
FROM clinical_journal_entries
WHERE created_by = 'briefing_task'
  AND generated_at > NOW() - INTERVAL '1 day'
GROUP BY 1;

-- 3. tool_validator 命中了哪些幻觉
ssh root@39.98.206.178 \
  "journalctl -u health-backend --since '1 day ago' | grep 'tool_validator_coerced' | sort | uniq -c"

-- 4. Exercise / Rhinitis 记录是否真写入
SELECT record_date, exercise_type, reps, duration
FROM exercise_records
WHERE user_id = <YOUR_ID> ORDER BY created_at DESC LIMIT 5;

SELECT name, severity, notes, created_at
FROM illness_episodes
WHERE user_id = <YOUR_ID> AND name LIKE '鼻炎%'
ORDER BY created_at DESC LIMIT 5;
```

---

## 三、今晚没做的（等用户明早决策）

### 🔴 TestFlight Public Link

用户之前问"邀请兑换码"。需要你亲自：
1. App Store Connect → HealthPilot → TestFlight → External Testing
2. 新建组 → Enable Public Link → 首次走 Beta Review（24-48h）
3. 拿到 `testflight.apple.com/join/XXX` 发给父亲/朋友

### 🟡 Sentry / GlitchTip 观测

所有 metric 日志（tool_validator_coerced / LLM usage / set_caller 名字）堆在
`journalctl` 里没 sink。实际价值损失：本次两个 500 bug 是今晚巧碰到的，下次
silent 失败可能几天才发现。

三个选项:
- **Sentry.io 免费档**（10 min 注册 + 贴 DSN，医疗数据去美国）
- **GlitchTip 自建** on 39.98.206.178（1-2h docker compose，数据不出国）
- **跳过** 继续 log-only（现状）

推荐 Sentry.io；想合规就 GlitchTip。

### 🟡 大文件拆分

- `backend/app/services/data_collection/garmin_connect.py` ~2800 行
- `backend/app/tasks/notifications.py` ~1500+ 行

CLAUDE.md 复杂度预算红线 500 行。每次碰都在加债。

### 🟢 远期（月级）

- Apple HealthKit 集成
- 华为 Health Kit（账号服务审核中）
- STRATEGY 阶段 5 Household Twin
- STRATEGY 阶段 6 Reasoning Trace + B 端可解释性

---

## 四、关键数字

| 项 | 值 |
|---|---|
| Commit | 20 |
| 代码增 | ~1500 行（主要 schema + service + test） |
| 代码删 | ~35000 行（断舍离一次性大清理） |
| 测试 | 1145 → 1201（+56 零回归） |
| OTA | 17 次（Update Group 从 `dccffa9d` 到 `cf6ed09` 关联） |
| 生产部署 | 12 次（所有 PASS） |
| 健康度 | 最终 37/60 ✅（一度到 34 自回滚，已修 2 个 500 根因） |

## 五、线上当前状态

- **后端**: commit `cf6ed09` | systemd `health-backend.service` active
- **前端**: PM2 `health-frontend` online
- **TestFlight**: 最新 OTA 在 production channel（`cf6ed09` 对应 bundle）
- **Celery beat**: 新加 `doctor-weekly-report` Mon 09:15 北京; 其他照旧

---

*收工时间: 2026-04-30 01:35 (北京)*
