const fs = require('fs');
const os = require('os');
const path = require('path');
jest.mock('uuid', () => ({
  v4: jest.fn(() => '123e4567-e89b-12d3-a456-426614174000'),
}));
const xcode = require('xcode');
const {
  _buildSiriSwift,
  _resolveMainTarget,
  _ensureSiriIntentsGroup,
} = require('../withIntentsExtension');

const APP_GROUP = 'group.life.executor.health';
const IOS_ROOT = path.join(__dirname, '..', '..', 'ios');

// The plugin now writes under the resolved project dir (e.g. ios/app/SiriIntents);
// scan every generated copy instead of hardcoding the legacy HealthPilot path.
function findGeneratedSiriSwiftFiles() {
  if (!fs.existsSync(IOS_ROOT)) return [];
  return fs.readdirSync(IOS_ROOT, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(IOS_ROOT, entry.name, 'SiriIntents', 'HealthPilotSiri.swift'))
    .filter((candidate) => fs.existsSync(candidate));
}

// Minimal real pbxProject (same xcode lib the plugin runs against — a hand-rolled
// fake would only prove parsing, not that the lib calls behave as assumed).
function makePbxProject({ targets = {} } = {}) {
  const project = new xcode.project('test.pbxproj');
  project.hash = {
    project: {
      objects: {
        PBXNativeTarget: targets,
        PBXGroup: {
          MAINGROUP: { isa: 'PBXGroup', children: [], sourceTree: '"<group>"' },
          MAINGROUP_comment: 'MainGroup',
        },
        PBXProject: {
          PROJROOT: { isa: 'PBXProject', mainGroup: 'MAINGROUP' },
        },
        PBXFileReference: {},
        PBXBuildFile: {},
        PBXSourcesBuildPhase: {},
        PBXVariantGroup: {},
      },
    },
  };
  return project;
}

const APP_TARGETS = {
  APPTARGETUUID: { isa: 'PBXNativeTarget', name: 'app' },
  APPTARGETUUID_comment: 'app',
};

describe('withIntentsExtension buildSiriSwift — Siri SSE parsing fix (P0 假成功)', () => {
  const swift = _buildSiriSwift(APP_GROUP);

  it('loads the auth token from shared Keychain only', () => {
    expect(swift).toContain('SecItemCopyMatching');
    expect(swift).not.toContain('UserDefaults(suiteName: appGroup)');
    expect(swift).not.toContain('Writes & reads both App Group UserDefaults');
  });

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

  // 模板是真源; 生成文件与模板必须逐字一致, 否则下次 prebuild 会把手改回退。
  // ios/ 是 gitignored 的 prebuild 产物 — 没跑过 prebuild 的 checkout 无物可比, 显式 skip
  // (旧版硬编码 ios/HealthPilot/... 在这种 checkout 里直接 ENOENT 崩, 不是护栏是坏测试)。
  const generatedCopies = findGeneratedSiriSwiftFiles();
  (generatedCopies.length > 0 ? it : it.skip)(
    'renders byte-for-byte identical to every on-disk generated Swift file',
    () => {
      for (const onDiskPath of generatedCopies) {
        expect(swift).toBe(fs.readFileSync(onDiskPath, 'utf-8'));
      }
    },
  );
});

describe('withIntentsExtension target resolution — Siri silent-skip fix', () => {
  it('resolves the Expo generated "app" target via modRequest.projectName', () => {
    const project = makePbxProject({ targets: APP_TARGETS });

    expect(_resolveMainTarget(project, { projectName: 'app' }))
      .toEqual({ name: 'app', uuid: 'APPTARGETUUID' });
  });

  it('resolves quoted pbxproj target names', () => {
    const project = makePbxProject({
      targets: {
        APPTARGETUUID: { isa: 'PBXNativeTarget', name: '"app"' },
        APPTARGETUUID_comment: 'app',
      },
    });

    expect(_resolveMainTarget(project, { projectName: 'app' }).uuid).toBe('APPTARGETUUID');
  });

  it('falls back to the on-disk *.xcodeproj name when projectName is absent', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'siri-xcodeproj-'));
    try {
      fs.mkdirSync(path.join(tmpDir, 'app.xcodeproj'), { recursive: true });
      const project = makePbxProject({ targets: APP_TARGETS });

      expect(_resolveMainTarget(project, { platformProjectRoot: tmpDir }))
        .toEqual({ name: 'app', uuid: 'APPTARGETUUID' });
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('keeps legacy HealthPilot only as last-resort fallback', () => {
    const project = makePbxProject({
      targets: {
        LEGACYUUID: { isa: 'PBXNativeTarget', name: 'HealthPilot' },
        LEGACYUUID_comment: 'HealthPilot',
      },
    });

    expect(_resolveMainTarget(project, {}))
      .toEqual({ name: 'HealthPilot', uuid: 'LEGACYUUID' });
  });

  it('throws loud when no main target can be found (never silently skips)', () => {
    const project = makePbxProject({ targets: {} });

    expect(() => _resolveMainTarget(project, { projectName: 'app' }))
      .toThrow(/could not find main app target/);
  });

  it('never hardcodes the legacy write path nor silently skips addSourceFile', () => {
    const pluginSource = fs.readFileSync(path.join(__dirname, '..', 'withIntentsExtension.js'), 'utf8');

    expect(pluginSource).toContain('resolveMainTarget(');
    expect(pluginSource).toContain('could not find main app target');
    // 旧 bug 根因: 硬编码路径 + if (mainTargetUuid) 静默跳过 addSourceFile
    expect(pluginSource).not.toContain("path.join(proj, 'ios', 'HealthPilot', 'SiriIntents')");
    expect(pluginSource).not.toContain('if (mainTargetUuid)');
  });
});

describe('withIntentsExtension SiriIntents group — idempotent on repeated prebuild', () => {
  it('does not duplicate the SiriIntents group on second run', () => {
    const project = makePbxProject({ targets: APP_TARGETS });

    const firstKey = _ensureSiriIntentsGroup(project, 'app/SiriIntents');
    const secondKey = _ensureSiriIntentsGroup(project, 'app/SiriIntents');

    expect(secondKey).toBe(firstKey);

    const groups = project.hash.project.objects.PBXGroup;
    const siriGroups = Object.entries(groups).filter(([key, group]) => (
      !key.endsWith('_comment') && group && group.name === 'SiriIntents'
    ));
    expect(siriGroups).toHaveLength(1);

    // main group references it exactly once
    const mainChildren = groups.MAINGROUP.children.filter((child) => child.value === firstKey);
    expect(mainChildren).toHaveLength(1);
  });

  it('registers the group under the resolved project dir path', () => {
    const project = makePbxProject({ targets: APP_TARGETS });

    const key = _ensureSiriIntentsGroup(project, 'app/SiriIntents');

    expect(project.hash.project.objects.PBXGroup[key].path).toBe('app/SiriIntents');
  });

  it('heals a stale legacy HealthPilot group path instead of duplicating', () => {
    const project = makePbxProject({ targets: APP_TARGETS });
    project.hash.project.objects.PBXGroup.STALEGROUP = {
      isa: 'PBXGroup',
      children: [],
      name: 'SiriIntents',
      path: '"HealthPilot/SiriIntents"',
      sourceTree: '"<group>"',
    };
    project.hash.project.objects.PBXGroup.STALEGROUP_comment = 'SiriIntents';

    const key = _ensureSiriIntentsGroup(project, 'app/SiriIntents');

    expect(key).toBe('STALEGROUP');
    expect(project.hash.project.objects.PBXGroup.STALEGROUP.path).toBe('app/SiriIntents');
    const siriGroups = Object.entries(project.hash.project.objects.PBXGroup).filter(([k, g]) => (
      !k.endsWith('_comment') && g && g.name === 'SiriIntents'
    ));
    expect(siriGroups).toHaveLength(1);
  });
});
