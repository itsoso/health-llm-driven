# 小巴本地优先私有模式设计

> Updated: 2026-07-18
> Status: approved product direction; technical G2 pending
> PRD: `docs/prd/2026-07-18-local-first-private-mode.md`
> Feature Spec: `docs/specs/active/2026-07-18-local-first-private-mode.md`

## 1. 设计结论

采用“本地优先 + 可选同步”，以完全离线饮食记录作为第一条垂直切片。设备是本地身份的数据真源；服务端只在用户主动开启时承担两个相互独立的角色：保存客户端加密后的同步密文，或执行一次明确授权的云模型请求。

本地模式不追求立即复制整个服务端 Health OS。先建立可复用的 Local Health Kernel，再迁移一个有现成状态机、人工确认和验证面的域。

## 2. 方案比较

| 方案 | 优点 | 缺点 | 裁决 |
|---|---|---|---|
| 轻量游客模式 | 改动小 | 仍以云端为真源，隐私承诺弱，离线不可持续 | 不采用 |
| 完整本地一次性重写 | 目标纯粹 | 同时重写认证、全部数据域、Safety、Twin、同步和模型，风险不可控 | 不采用 |
| 本地内核 + 饮食纵切 + 可选同步 | 能真实证明价值，架构可扩展，失败成本可控 | 阶段内存在双仓储路径 | **采用** |

## 3. 架构

```text
                           explicit opt-in only
                    +-------------------------------+
                    |                               |
Capture -> CapabilityRouter -> Draft -> Confirm -> LocalHealthStore
   |            |                    |              |
   |            +-> deterministic    |              +-> local projections
   |            +-> Apple model      |              +-> audit events
   |            +-> downloaded model |              +-> encrypted export
   |            +-> manual           |              +-> encrypted sync outbox
   |                                                   |
   +-> camera / text / voice / barcode                 +-> ciphertext sync service
                    |
                    +------------------------------------> one-shot cloud inference
                                                        minimal disclosed payload
```

### 3.1 App mode

`AppModeProvider` replaces the binary assumption that `isAuthenticated` means “can enter the app”. It exposes:

```ts
type AppMode = 'strict_local' | 'local_first' | 'cloud_account';

interface AppSession {
  mode: AppMode;
  localIdentityId?: string;
  cloudUser?: User;
  canUseCloudInference: boolean;
  canSync: boolean;
}
```

The root shell routes a local identity into the same Mobile navigation surfaces but supplies local repositories only for capabilities explicitly migrated. Non-migrated screens display an honest “requires cloud account” boundary; they do not trigger login in the background.

### 3.2 Local Health Kernel

The first kernel owns:

- local identity lifecycle;
- device-held encryption key;
- versioned local schema;
- local repository transactions;
- append-only execution/audit events;
- privacy egress policy;
- export/restore envelope;
- capability and model availability probes.

Health payloads use application-layer AES-GCM encryption through a Swift/CryptoKit bridge. Minimal non-content indexes such as local ID, record date, meal type, lifecycle status and schema version remain queryable. The key lives in Keychain; export derives a separate recovery key and never exports the device key directly.

The design deliberately does not require SQLCipher in the first slice. A G2 threat-model spike must confirm that protected files plus encrypted payloads meet the intended risk boundary. If not, the storage implementation can move behind the same repository interface.

### 3.3 Repository seam

UI and hooks consume domain repositories rather than importing HTTP services directly:

```ts
interface DietRepository {
  listDay(date: string): Promise<DailyDietSummary>;
  createConfirmed(input: ConfirmedDietInput): Promise<DietRecordReceipt>;
  update(id: string, patch: DietRecordPatch): Promise<DietRecordReceipt>;
  remove(id: string): Promise<void>;
  frequentFoods(): Promise<FrequentFood[]>;
}
```

`RemoteDietRepository` wraps the existing `mobile/services/diet.ts`; `LocalDietRepository` uses the kernel. Selection happens once from `AppSession`, not through scattered `if local` branches.

## 4. 完全本地饮食数据流

```text
capture
  -> deterministic parser/history lookup
  -> optional on-device model candidate
  -> sanitation and bounded typed draft
  -> local licensed food-table lookup
  -> visible provenance + missing fields
  -> user correction/confirmation
  -> encrypted LocalDietRecord
  -> LocalExecutionEvent
  -> deterministic daily totals
```

The model is an extractor, not a nutrition authority. It may identify “米饭” and parse “半碗”; the food table supplies nutrient density; portion conversion only occurs for supported units or a user-confirmed household measure. Unknown stays unknown.

The current photo flow can be reused conceptually but not directly: it sends Base64 to `/diet/recognize` and stores a server draft token. Local mode instead stores a private local photo reference and a local draft ID. Existing sanitation, idempotency and manual-confirm behavior remain invariants.

## 5. 端侧模型路由

### 5.1 Universal path

All supported devices get deterministic parsing, recent/frequent food matching, local food-table lookup, manual correction, barcode and OCR where available. This is the guaranteed offline product.

### 5.2 Apple system model

On eligible devices, Foundation Models performs typed Chinese text extraction and narrow clarification. Availability is checked at runtime. Prompt and output contracts are versioned by OS/model profile because Apple updates the system model with OS releases.

Apple references:

- Foundation Models supports on-device language understanding, guided structured output and tool calling: <https://developer.apple.com/documentation/FoundationModels>
- System model availability depends on an eligible device and Apple Intelligence being enabled.
- The June 2026 framework adds newer model and multimodal capabilities, which require separate versioned evaluation: <https://developer.apple.com/documentation/Updates/FoundationModels>

### 5.3 Vision and optional downloaded model

Vision supplies on-device OCR, barcode, classification and custom Core ML integration: <https://developer.apple.com/documentation/vision>. Core ML supports private on-device execution and runtime model download: <https://developer.apple.com/documentation/coreml>.

A downloadable food vision model is an experiment behind a benchmark gate, not part of the base promise. It ships only if it improves corrected-draft completion over Vision/history/manual baselines within memory, thermal and download budgets. It never estimates authoritative nutrients.

### 5.4 Explicit cloud enhancement

Cloud inference is a separate capability. Before a call, Mobile shows what leaves the device, whether a photo is included, retention semantics and the expected benefit. Strict-local mode rejects the call at the network policy layer even if a UI bug attempts it.

## 6. 本地食物数据库

The local nutrition database is the main accuracy asset. It needs:

- a reviewed source and redistribution license;
- canonical food identity and approved aliases;
- per-100g nutrients and household-unit conversions;
- source/version metadata;
- Chinese prepared-food coverage;
- local incremental updates that do not contain user data;
- correction provenance and reversible migrations.

The existing seed is useful for interface tests, not production coverage. Model selection must not proceed as if database coverage were solved.

## 7. Sync design

Sync is deferred until single-device correctness is proven.

- Client-generated stable IDs.
- Append-only encrypted envelopes and tombstones.
- Per-object version, device ID and monotonic local sequence.
- Server stores opaque ciphertext and account/device metadata only.
- Recovery secret is user-controlled; server cannot silently recover plaintext.
- Conflict resolution preserves audit history and never duplicates a confirmed meal.

Because the server cannot compute over ciphertext, cloud Health Twin generation for local-first users requires a separate, explicit decrypted inference request. That trade-off is surfaced, not hidden.

## 8. Privacy and failure behavior

- Strict-local mode denies authenticated health APIs, analytics content, Sentry health payloads, push registration and remote config.
- Offline or unavailable models fall back to manual/deterministic capture, never forced login.
- Key loss without export/sync is unrecoverable and must be explained during onboarding.
- Corrupt or unsupported local schema opens read-only recovery/export rather than deleting data.
- Model output parse failure preserves the raw user input locally and offers manual completion.
- Low storage disables retained photos before it blocks text records.
- Rollback must preserve existing local records and export access.

## 9. Testing strategy

### Product truth

- Fresh install in airplane mode.
- Record, restart and re-open a meal without an account.
- Model unavailable/disabled paths.
- Zero prohibited requests under packet capture.
- Export, delete app data, restore and verify stable IDs.

### Model evaluation

- Chinese text, colloquial quantities and mixed meals.
- Common single foods, Chinese composite dishes, cafeteria trays, packaged foods, hotpot/noodles/rice bowls.
- Blurred, low-light, occluded and non-food images.
- Metrics: valid typed draft, food identity precision, missing-item rate, correction burden, latency, memory, thermal behavior and crash-free completion.

### Safety and privacy

- No model candidate persists before confirmation.
- Unknown nutrients stay unknown.
- Photos and prompts never enter logs.
- Egress policy fails closed.
- Existing authenticated cloud flow remains unchanged.

## 10. G2 conditions

Implementation must not start until these are adjudicated:

1. A production nutrition dataset has a valid redistribution license.
2. The CryptoKit envelope, Keychain lifecycle and export recovery threat model pass security review.
3. Apple model and Vision spikes establish supported device/OS profiles.
4. A real-device memory and latency baseline proves the native path does not degrade existing iOS users.
5. Product accepts that strict-local photo recognition may be unavailable or lower quality on older devices.
