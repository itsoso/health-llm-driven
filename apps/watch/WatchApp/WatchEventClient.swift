import Foundation

/// watch action 埋点轻量出口。复用 WatchConnectivity 中继到 /client-events(经 iPhone 携 token)。
/// 覆盖 tile 出现、完成、稍后、跳过等轻量事件。
/// meta 仅 {action_id, kind, priority_tier}(无症状/用药名等敏感内容,对齐后端白名单/size limit)。
///
/// fire-and-forget:埋点失败绝不阻塞 UI / 不冒泡成用户错误(埋点是旁路,不是业务诚实点)。
@MainActor
final class WatchEventClient {
    static let shared = WatchEventClient()

    private let connectivity: WatchConnectivityClient

    init(connectivity: WatchConnectivityClient = .shared) {
        self.connectivity = connectivity
    }

    /// 从 top_action 构造 meta(缺字段不发,避免脏埋点)。priority_tier 缺省给 "unknown"。
    static func meta(actionId: String, kind: String, priorityTier: String?) -> [String: String] {
        [
            "action_id": actionId,
            "kind": kind,
            "priority_tier": priorityTier ?? "unknown",
        ]
    }

    /// 可完成 tile 出现时上报曝光(分母)。无 action_id 不发。
    func actionShown(_ action: WatchTopAction) {
        guard let id = action.actionId, !id.isEmpty else { return }
        emit("watch_action_shown",
             Self.meta(actionId: id, kind: action.kind, priorityTier: action.priorityTier))
    }

    /// 完成成功后上报(分子)。无 action_id 不发。
    func actionCompleted(_ action: WatchTopAction) {
        guard let id = action.actionId, !id.isEmpty else { return }
        actionCompleted(actionId: id, kind: action.kind, priorityTier: action.priorityTier)
    }

    func actionCompleted(actionId: String, kind: String, priorityTier: String? = nil) {
        emit("watch_action_completed",
             Self.meta(actionId: actionId, kind: kind, priorityTier: priorityTier))
    }

    func actionSnoozed(_ action: WatchTopAction, minutes: Int) {
        guard let id = action.actionId, !id.isEmpty else { return }
        actionSnoozed(actionId: id, kind: action.kind, priorityTier: action.priorityTier, minutes: minutes)
    }

    func actionSnoozed(actionId: String, kind: String, priorityTier: String? = nil, minutes: Int) {
        var meta = Self.meta(actionId: actionId, kind: kind, priorityTier: priorityTier)
        meta["minutes"] = String(minutes)
        emit("watch_action_snoozed", meta)
    }

    func actionSkipped(_ action: WatchTopAction, reason: String) {
        guard let id = action.actionId, !id.isEmpty else { return }
        actionSkipped(actionId: id, kind: action.kind, priorityTier: action.priorityTier, reason: reason)
    }

    func actionSkipped(actionId: String, kind: String, priorityTier: String? = nil, reason: String) {
        var meta = Self.meta(actionId: actionId, kind: kind, priorityTier: priorityTier)
        meta["reason"] = reason
        emit("watch_action_skipped", meta)
    }

    func smartReminderVisible(_ summary: WatchSummary) {
        for meta in watchSmartReminderVisibleEventMetas(summary) {
            emit("watch_smart_reminder_visible", meta)
        }
    }

    private func emit(_ name: String, _ meta: [String: String]) {
        Task { [connectivity] in
            // 埋点失败静默吞——但这是「旁路诚实」例外:埋点不是业务结果,失败不该让用户看到错误。
            // (业务完成本身的失败由 completeAction 链路 fail-loud,见 WatchStore.completeAction。)
            try? await connectivity.sendEvent(name: name, meta: meta)
        }
    }
}
