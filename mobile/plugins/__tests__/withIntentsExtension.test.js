const fs = require('fs');
const path = require('path');
const { _buildSiriSwift } = require('../withIntentsExtension');

const APP_GROUP = 'group.life.executor.health';
const GENERATED_SWIFT_PATH = path.join(
  __dirname,
  '..',
  '..',
  'ios',
  'HealthPilot',
  'SiriIntents',
  'HealthPilotSiri.swift',
);

describe('withIntentsExtension buildSiriSwift — Siri SSE parsing fix (P0 假成功)', () => {
  const swift = _buildSiriSwift(APP_GROUP);

  it('parses the SSE wire format via event/data.content, not top-level content', () => {
    // 新解析: 逐行 data: 后 JSON, 按 event 分派, token 累积 data.content
    expect(swift).toContain('let eventType = json["event"] as? String');
    expect(swift).toContain('let payload = json["data"] as? [String: Any]');
    expect(swift).toContain('if eventType == "token", let c = payload?["content"] as? String');

    // 旧的 top-level content 读取必须彻底消失 (它永远取不到值 → 假成功根因)
    expect(swift).not.toContain('let c = json["content"] as? String');
    expect(swift).not.toContain('json["content"]');
  });

  it('treats event=="error" as a failed run and never claims success', () => {
    expect(swift).toContain('if eventType == "error"');
    expect(swift).toContain('sawError = true');
    // 失败话术出现, 且不再无条件返回"已记录"
    expect(swift).toContain('记录失败，请打开健康助理 App 确认');
    expect(swift).toContain('记录失败, 请打开健康助理 App 确认');
  });

  it('QuickWaterIntent no longer discards the body and only reports success on real reply', () => {
    // 旧写法: let (_, response) 丢弃 body → 无条件成功。修复后必须捕获 data。
    expect(swift).not.toContain('let (_, response) = try await URLSession.shared.data(for: request)');
    // 空回复保守按失败 (绝不假报成功)
    expect(swift).toContain('accumulated.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty');
  });

  it('SSE record bodies send channel=siri and drop the backend-ignored stream flag', () => {
    // 两条走 /agent/stream (SSE) 的记录意图: message + channel=siri, 无 stream 标志。
    expect(swift).toContain('["message": content.text, "channel": "siri"]');
    expect(swift).toContain('["message": "记录我喝了一杯水(约250毫升)", "channel": "siri"]');
    // 记录路径不再夹带被后端忽略的 stream:false
    expect(swift).not.toContain('content.text, "stream": false');
    expect(swift).not.toContain('250毫升)", "stream": false');
    // HealthAnalysisIntent 走 /orchestrator/chat (非 SSE JSON), 本次不动, 其 body 原样保留。
    expect(swift).toContain('["query": query.text, "stream": false, "source": "siri"]');
  });

  it('renders byte-for-byte identical to the on-disk generated Swift file', () => {
    // 模板是真源; 二者必须逐字一致, 否则下次 prebuild 会把手改回退。
    const onDisk = fs.readFileSync(GENERATED_SWIFT_PATH, 'utf-8');
    expect(swift).toBe(onDisk);
  });
});
