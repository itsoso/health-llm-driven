# Rokid 俯卧撑真实数据接入规划

## 结论

当前 Reva iOS CXR-L bridge 没有直接接入“真实姿态流 / 视频 pose API”，不是产品上不想做，而是公开 iOS SDK 能力边界决定的。

本机检查到的 `RGCxrClient 1.0.1` Swift interface 有这些能力：

- `queryApp(packageName:callback:)`
- `openApp(packageName:activityName:url:callback:)`
- `stopApp(_:callback:)`
- `installApp(_:callback:)`
- CustomView 打开 / 更新 / 关闭
- 拍照、录音

但没有看到这些 iOS 公开 API：

- 眼镜相机实时视频帧回调
- pose landmark / skeleton stream
- iOS 侧接收 CustomApp 自定义指令的 callback
- 双向 `sendCustomCmd` / `setCustomCmdCallback` 等 Android CXR-L 示例里的能力

因此 Reva 的真实数据接入路线应当是：

1. iOS Reva 用 CXR-L 启动眼镜端 CustomApp。
2. 眼镜端 Android App 自己读取摄像头并做姿态识别。
3. 眼镜端 App 把 pose / rep / quality 事件写入 Reva 后端。
4. iOS Reva 轮询后端事件，更新手机 UI、保存运动记录、同步到 Health OS。

这条链路不依赖不存在的 iOS pose stream，也不把模拟按钮伪装成真实数据。

## 已实现的 Reva 侧能力

### 后端

新增 `/api/v1/devices/rokid/pushup-sessions`：

- `POST /pushup-sessions`
  - 需要用户登录。
  - 创建一次眼镜训练 session。
  - 返回 `ingest_token`、`ingest_url`、`open_url`。
  - 数据库只保存 token 的 SHA-256 hash，不保存明文 token。

- `POST /pushup-sessions/{session_id}/events`
  - 供眼镜端 App 写入。
  - 通过 `X-Reva-Rokid-Session-Token` 校验。
  - 接收 `pose`、`rep`、`session_state` 三类事件。

- `GET /pushup-sessions/{session_id}/events?after_id=...`
  - 需要用户登录。
  - 只允许 session owner 读取。

- `POST /pushup-sessions/{session_id}/finish`
  - 结束 session。

新增表：

- `rokid_pushup_sessions`
- `rokid_pushup_events`

### iOS / Mobile

新增 iOS bridge 方法：

- `queryRokidApp(packageName)`
- `openRokidApp({ packageName, activityName, url })`
- `stopRokidApp(packageName)`

新增 mobile service：

- `createRokidPushupSession`
- `listRokidPushupEvents`
- `finishRokidPushupSession`
- `applyRokidPushupEventToCoach`

`mobile/app/rokid-pushup-coach.tsx` 已新增“真实识别”入口：

1. 创建后端 session。
2. 检查眼镜端 push-up app 是否安装。
3. 用 CXR-L `openApp` 启动眼镜端 app。
4. 每 1 秒轮询 Reva 后端事件。
5. 用真实 pose / rep event 驱动现有计数和动作评价。

## 眼镜端 Android App 契约

建议包名：

```text
life.executor.health.rokid.pushup
```

建议入口：

```text
.MainActivity
```

iOS `openApp` 传入的 `url` 格式：

```text
reva://rokid/pushup?session_id=7&target_reps=20&ingest_url=https%3A%2F%2F...%2Fevents&ingest_token=...
```

眼镜端 App 启动后必须：

1. 解析 `session_id`、`target_reps`、`ingest_url`、`ingest_token`。
2. 请求相机权限。
3. 打开眼镜摄像头预览或后台帧流。
4. 用姿态识别模型输出肘角、身体线条角度、可见度。
5. 本地做动作状态机，或只发送 pose 由 Reva 端计数。
6. 每次事件 POST 到 `ingest_url`。

事件请求：

```http
POST {ingest_url}
X-Reva-Rokid-Session-Token: {ingest_token}
Content-Type: application/json
```

Pose event：

```json
{
  "event_type": "pose",
  "phase": "down",
  "reps": 0,
  "elbow_angle_deg": 84,
  "shoulder_hip_ankle_angle_deg": 174,
  "visibility": 0.94,
  "quality_score": 91,
  "payload": {
    "model": "glasses_pose_v1",
    "frame_id": "f-000123"
  }
}
```

Rep event：

```json
{
  "event_type": "rep",
  "phase": "up",
  "reps": 5,
  "quality_score": 88,
  "visibility": 0.97,
  "payload": {
    "suggestion": "保持节奏"
  }
}
```

## 眼镜端实现建议

第一版不要先追求复杂 AI，而是做稳定可验证的 pipeline：

1. 基于 Rokid CXR-S sample 新建 Android 工程。
2. 接入摄像头帧。
3. 接入轻量姿态模型，例如 MediaPipe Pose / MoveNet，或 Rokid 提供的原生 CV 能力。
4. 只识别俯卧撑所需的关键点：
   - shoulder
   - elbow
   - wrist
   - hip
   - ankle
5. 计算：
   - elbow angle
   - shoulder-hip-ankle body line angle
   - landmark visibility
6. 发送低频事件：
   - pose：建议 5-10 Hz，不要上传原始视频。
   - rep：每完成一个动作发送一次。
7. 眼镜端本地显示：
   - 当前 count
   - 当前质量提示
   - 视野不稳提示

## 真机验证顺序

1. 安装带 Rokid SDK 的 Reva iOS 包。
2. 在 Reva 完成 CXR-L 授权。
3. 在 Rokid 眼镜安装 `life.executor.health.rokid.pushup`。
4. 打开 Reva 的 Rokid 俯卧撑页，点“启动眼镜识别”。
5. iOS 调用 `queryApp`，必须返回 installed。
6. iOS 调用 `openApp`，眼镜端 App 前台启动。
7. 眼镜端 App POST 一条 `pose` 测试事件。
8. Reva 手机页面 1 秒内显示计数/反馈更新。
9. 完成一组后点保存，进入今日力量训练记录。

## 关键边界

- 不上传视频到 Reva 后端；只上传结构化 pose / rep 指标。
- `ingest_token` 是 session 级短 token，只给眼镜端写入，不给读取权限。
- 普通读取仍走用户 JWT，必须 user_id 隔离。
- 如果 Rokid 后续提供 iOS CXR-L 1.0.2/1.0.3 的 custom command callback 或 frame stream，可以新增直连路径，但不替代当前后端 ingest 路径。
