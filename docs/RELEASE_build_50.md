# Build 50 — Phase 2 优化 + 用户反馈批

## 给 TestFlight 用户看的 What's New

### 🆕 新功能
- **位置设置** (设置 → 位置设置)
  - 手动指定城市 (18 个常用城市快选)
  - 自动 IP 检测 + 重新检测按钮
  - 改地点立即清天气/空气质量缓存
- **家庭邀请码** (设置 → 家庭健康 → 邀请家人)
  - 一键生成 6 位码，30 分钟内有效
  - 系统分享 sheet 直接发微信
  - 家人输入码 + 选关系 (爸爸/妈妈/...) 一键加入
- **声音笔记 summary 卡** — 关闭对话时弹「本次记了 N 项: ...」让你 review
- **写库前确认** 体重/血压/生病自动跳出「我准备记 X，是这样吗?」防 AI 错记

### 🛠️ Bug 修复
- 语音对话同一句发两遍 (`justSubmittedRef` + 后端 3 秒 dup cache 双重防御)
- AI 分析卡片空白但能听 (cache_only 端点 fallback 看 WorkoutAnalysisResult)
- AI 分析按钮挤压标题 → 移到内容上方 toolbar
- 莫米松等用药点击 done 后再点没视觉反馈 → toast 改"再记一次"

### 🎙️ 后台改进
- 私享女声切换到新复刻 voice ID (用户重新训练的音色)
- LLM tool schema 加厚说明 (减少选错 dimension)

---

## 内部备忘

### 累积 commit (build 49 → 50)
- **dup 双发修复**: client `justSubmittedRef` + server in-memory dup cache 3s 窗
- **AI 分析渲染**: cache_only 端点桥接 WorkoutAnalysisResult.aggregation
- **UI 修**: workout-detail toolbar / aiToolbar 重排
- **mobile**: medications 用药管理页 / family.tsx 邀请流 / location.tsx 位置设置
- **后端**: agent_executor `_confirm_or_describe` helper, weight/bp/illness 走确认
- **后端**: weather_service `invalidate_cache_for` + air_quality_service 同
- **后端**: family/invitation/create + accept (内存 30min TTL)
- **TTS**: voice id 切到 `cosyvoice-v3.5-plus-bailian-0ecf848a...`

### Runtime
- `runtimeVersion = appVersion = 1.1.0` — build 47-50 共享 OTA channel
- 0 native 改动, 全部 OTA 可下 — 但仍发 build 减少新装等待

### 已知限制
- GPS 自动定位 (要 expo-location native, 下次 build 加)
- 微信原生 SDK 分享 (要 native + 微信开放平台 AppID)
- proximity 自动听筒 (要 native AVAudioSession 扩展)

### 等待用户验证 (重启 app 拉 OTA → 装 build 50)
- 语音双发是否消失
- 卡路里数值 (Garmin 设备级偏低 20-30%, 不是我们 bug)
- 微信分享 sheet 里是否出现微信选项 (取决于 iOS 系统)
