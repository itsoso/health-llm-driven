# P0-3 冷启动包 — 后端契约 (wk1/c1-coldstart-backend)

后端半已实现。以下是 mobile-engineer 需要对齐的**唯一契约**（endpoint 无 `response_model`，
`api.generated.ts` 不会生成这些字段，必须在 `mobile/services/conversationOpener.ts` 手写类型）。

## Endpoint
`GET /api/v1/agent/conversation-starters` → `{ opener, suggestions, onboarding? }`

## 1) 顶层 `onboarding` 字段（仅冷启动用户）
- 零信号冷启动用户：响应含 `"onboarding": true`。
- 老用户：**该 key 不出现**（不是 `false`，是 absent）。判定复用既有零信号判定
  （`is_cold_start_user` → `_collect_signals` + `_has_any_user_signal`），与 onboarding chips 分支同源，永不打架。

## 2) 冷启动合成 opener（走既有 `opener` 字段）
冷启动用户的 `opener` 非空，形如：
```json
{
  "text": "嗨，我是小巴，你的健康参谋 🐾。这里还看不到你的健康数据，我们从记录一件小事开始吧——拍张今天的饭、记一下体重，或连上你的手表，有了第一笔，我就能陪你一起往下看。",
  "source": "cold_start",
  "source_id": null,
  "quick_replies": [
    { "label": "拍一张今天的饭", "action": "photo_meal" },
    { "label": "记一下体重",   "action": "record_weight" },
    { "label": "连接手表数据",  "action": "connect_device" }
  ],
  "deep_link": null,
  "priority": 100
}
```

### quick_replies item 形状（关键）
- item 现在可以是 **string（既有，send-as-text）** 或 **`{ label, action }`（新，本地导航）**。
- `action` 枚举（closed set）：`"photo_meal" | "record_weight" | "connect_device"`。
- **带 `action` 的 quick reply 由客户端本地导航处理，不发文本**（拍照 picker / 体重录入 sheet / 连设备）。
- 不带 `action` 的 item（老 opener 的 `["做到了 ✅", ...]`）行为**零变化**。
- `source: "cold_start"` 是新增枚举值；老 4 类 source 不变。

### mobile 侧类型改动建议（conversationOpener.ts）
```ts
export type OpenerSource =
  | 'action_card_due' | 'anomaly' | 'case_thread' | 'memory_fact'
  | 'cold_start';                                  // 新增

export type OpenerAction = 'photo_meal' | 'record_weight' | 'connect_device';
export interface OpenerActionReply { label: string; action: OpenerAction; }
export type OpenerQuickReply = string | OpenerActionReply;  // 既有 string 或带 action 的对象

export interface ConversationOpener {
  // ...
  quick_replies: OpenerQuickReply[];               // string[] → (string | {label,action})[]
}
export interface ConversationStarters {
  opener: ConversationOpener | null;
  suggestions: SuggestionMeta[] | null;
  onboarding?: boolean;                            // 新增，冷启动才有
}
```
渲染 quick reply 时：`typeof qr === 'string'` → 老路径发文本；否则读 `qr.label` 显示、按 `qr.action`
本地导航（不发文本）。`buildConversationOpenerReplyContext/Message` 只对 string reply 调用即可。

## 3) starter item shape 零变化
`suggestions[]` 仍是 `{ text, key, priority, polished }`；冷启动时 key 全为 `"onboarding"`（既有行为）。

## 后端改动文件
- `backend/app/services/conversation_opener.py` — `OpenerQuickReply` dataclass + `synthesize_cold_start_opener()` + `COLD_START_ACTIONS`
- `backend/app/services/conversation_starters.py` — `is_cold_start_user()`（复用 `_has_any_user_signal`）
- `backend/app/api/agent.py` — starters endpoint 注入 `onboarding` + 冷启动 opener

## LLM 润色说明
本版冷启动 opener 是**确定性模板**（无 LLM），已过 `guidance_validator` R4 红线。starter chips 仍走既有 `starter_polish` 管线不变。
