import SwiftUI

/// 今日状态屏(Reva 深色面):就绪度大数字 + 环 + 状态灯 + headline + 最该做 + 待打点。
/// 数据全来自 store.summary,无值显示「待同步」而不瞎填。腕上一眼可读。
struct TodayStatusView: View {
    @ObservedObject var store: WatchStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                readinessHeader

                if let st = store.summary?.status {
                    Text(st.headline)
                        .font(.footnote)
                        .foregroundStyle(RevaWatch.ink2)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if let action = store.summary?.topAction {
                    topActionRow(action)
                }

                dueItemsSection

                if let ag = store.summary?.agenda, ag.pending > 0 {
                    pendingRow(ag.pending)
                }

                if store.loading {
                    ProgressView()
                        .tint(RevaWatch.greenBright)
                        .frame(maxWidth: .infinity)
                }
                if let err = store.lastError {
                    Text(err)
                        .font(.caption2)
                        .foregroundStyle(RevaWatch.risk)
                }
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
        }
        .background(RevaWatch.focusBg)
        .navigationTitle("今日")
    }

    // MARK: - Readiness header (大数字 + 环 + 状态灯)

    private var readinessHeader: some View {
        let tone = store.summary?.status.light ?? .gray
        let freshness = store.summary?.status.freshness
        let isFresh = freshness?.isFresh ?? true
        let score = isFresh ? store.summary?.status.readinessScore : nil
        return HStack(spacing: 14) {
            readinessRing(tone: tone, score: score)
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Circle()
                        .fill(RevaWatch.tone(tone))
                        .frame(width: 8, height: 8)
                    Text("今日就绪")
                        .font(.caption2)
                        .foregroundStyle(RevaWatch.ink2)
                }
                if let s = score, s > 0 {
                    Text("\(s)")
                        .font(RevaWatch.monoNumber(30, weight: .semibold))
                        .foregroundStyle(RevaWatch.greenBright)
                } else {
                    Text(freshness?.shortText ?? "待同步")
                        .font(.footnote)
                        .foregroundStyle(RevaWatch.ink2)
                }
                if let freshness, !freshness.isFresh {
                    freshnessBadge(freshness)
                }
            }
            Spacer(minLength: 0)
        }
    }

    private func freshnessBadge(_ freshness: WatchFreshness) -> some View {
        Label(freshness.label, systemImage: freshnessIcon(for: freshness.state))
            .font(.caption2)
            .foregroundStyle(freshnessColor(for: freshness.state))
            .lineLimit(1)
            .minimumScaleFactor(0.75)
    }

    private func readinessRing(tone: ComplicationTone, score: Int?) -> some View {
        let value = Double(score ?? 0)
        return Gauge(value: value, in: 0...100) {
            EmptyView()
        } currentValueLabel: {
            EmptyView()
        }
        .gaugeStyle(.accessoryCircularCapacity)
        .tint(RevaWatch.tone(tone))
        .frame(width: 52, height: 52)
    }

    // MARK: - Top action (醒目圆角行)
    // 可完成项(有 action_id 且 health_protocol 域)→ 可点 tile,点击「一键已做」;
    // 非可完成项(action_id=null,如复查/训练)→ 只读行,不给完成按钮(对齐后端边界)。

    @ViewBuilder
    private func topActionRow(_ action: WatchTopAction) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("最该做")
                .font(.caption2)
                .foregroundStyle(RevaWatch.ink2)
            if action.isCompletable {
                completableTile(action)
            } else {
                readonlyActionTile(action)
            }
            if store.lastRecordOK == true, let msg = store.lastRecordMessage {
                Label(msg, systemImage: "checkmark.circle.fill")
                    .font(.caption2)
                    .foregroundStyle(RevaWatch.greenBright)
            }
        }
        // tile 出现即上报曝光(分母)。仅可完成项发(WatchEventClient 内已 guard action_id)。
        .onAppear {
            if action.isCompletable {
                store.reportActionShown(action)
            }
        }
    }

    private func completableTile(_ action: WatchTopAction) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: iconName(for: action.kind))
                    .font(.footnote)
                    .foregroundStyle(RevaWatch.greenBright)
                    .frame(width: 18)
                VStack(alignment: .leading, spacing: 4) {
                    Text(action.title)
                        .font(.body)
                        .foregroundStyle(RevaWatch.ink1)
                        .fixedSize(horizontal: false, vertical: true)
                    actionMetaLine(action)
                }
                Spacer(minLength: 0)
            }

            HStack(spacing: 6) {
                miniButton(
                    title: store.completing ? "..." : "已做",
                    icon: store.completing ? "hourglass" : "checkmark.circle.fill",
                    color: RevaWatch.greenBright,
                    disabled: store.completing || store.skipping || store.snoozing
                ) {
                    Task { await store.completeAction(action) }
                }
                miniButton(
                    title: store.snoozing ? "..." : "稍后",
                    icon: "clock",
                    color: RevaWatch.caution,
                    disabled: store.completing || store.skipping || store.snoozing
                ) {
                    Task { await store.snoozeAction(action) }
                }
                miniButton(
                    title: store.skipping ? "..." : "跳过",
                    icon: "xmark.circle",
                    color: RevaWatch.ink2,
                    disabled: store.completing || store.skipping || store.snoozing
                ) {
                    Task { await store.skipAction(action, reason: "no_time") }
                }
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 9)
        .background(
            RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
                .fill(RevaWatch.focusBg2)
        )
        .overlay(
            RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
                .stroke(RevaWatch.greenBright.opacity(0.5), lineWidth: 1)
        )
    }

    private func readonlyActionTile(_ action: WatchTopAction) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: iconName(for: action.kind))
                .font(.footnote)
                .foregroundStyle(RevaWatch.greenBright)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 4) {
                Text(action.title)
                    .font(.body)
                    .foregroundStyle(RevaWatch.ink1)
                    .fixedSize(horizontal: false, vertical: true)
                actionMetaLine(action)
            }
            Spacer(minLength: 4)
            Image(systemName: "chevron.right")
                .font(.caption2)
                .foregroundStyle(RevaWatch.ink2)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 9)
        .background(
            RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
                .fill(RevaWatch.focusBg2)
        )
        .overlay(
            RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
                .stroke(RevaWatch.focusLine, lineWidth: 1)
            )
    }

    @ViewBuilder
    private func actionMetaLine(_ action: WatchTopAction) -> some View {
        let window = timeWindowLabel(action.timeWindow)
        let rationale = action.rationaleShort
        if window != nil || rationale != nil {
            VStack(alignment: .leading, spacing: 2) {
                if let window {
                    Label(window, systemImage: "clock")
                        .font(.caption2)
                        .foregroundStyle(RevaWatch.ink2)
                }
                if let rationale, !rationale.isEmpty {
                    Text(rationale)
                        .font(.caption2)
                        .foregroundStyle(RevaWatch.ink2)
                        .lineLimit(2)
                }
            }
        }
    }

    private func miniButton(
        title: String,
        icon: String,
        color: Color,
        disabled: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Label(title, systemImage: icon)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(color)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
                .background(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(RevaWatch.focusBg)
                )
        }
        .buttonStyle(.plain)
        .disabled(disabled)
    }

    // MARK: - Due items

    @ViewBuilder
    private var dueItemsSection: some View {
        let topId = store.summary?.topAction?.actionId
        let items = (store.summary?.dueItems ?? [])
            .filter { $0.actionId != topId }
            .prefix(3)

        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text("接下来")
                    .font(.caption2)
                    .foregroundStyle(RevaWatch.ink2)
                ForEach(Array(items)) { item in
                    dueItemRow(item)
                }
            }
        }
    }

    private func dueItemRow(_ item: WatchDueItem) -> some View {
        HStack(alignment: .center, spacing: 8) {
            Image(systemName: iconName(for: item.kind))
                .font(.caption)
                .foregroundStyle(RevaWatch.ink2)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title)
                    .font(.caption)
                    .foregroundStyle(RevaWatch.ink1)
                    .lineLimit(2)
                if let window = timeWindowLabel(item.timeWindow) {
                    Text(window)
                        .font(.caption2)
                        .foregroundStyle(RevaWatch.ink2)
                }
            }
            Spacer(minLength: 4)
            if item.isCompletable {
                Button {
                    Task { await store.completeDueItem(item) }
                } label: {
                    Image(systemName: store.completing ? "hourglass" : "checkmark.circle")
                        .font(.caption)
                        .foregroundStyle(RevaWatch.greenBright)
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(.plain)
                .disabled(store.completing)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: RevaWatch.radiusRow, style: .continuous)
                .fill(RevaWatch.focusBg2)
        )
        .overlay(
            RoundedRectangle(cornerRadius: RevaWatch.radiusRow, style: .continuous)
                .stroke(RevaWatch.focusLine, lineWidth: 1)
        )
    }

    // MARK: - Pending count

    private func pendingRow(_ pending: Int) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "checklist")
                .font(.caption2)
                .foregroundStyle(RevaWatch.ink2)
            Text("待打点")
                .font(.caption)
                .foregroundStyle(RevaWatch.ink2)
            Text("\(pending)")
                .font(RevaWatch.monoNumber(13, weight: .semibold))
                .foregroundStyle(RevaWatch.ink1)
            Text("项")
                .font(.caption)
                .foregroundStyle(RevaWatch.ink2)
        }
    }

    private func freshnessIcon(for state: WatchFreshnessState) -> String {
        switch state {
        case .fresh:
            return "checkmark.circle"
        case .error:
            return "exclamationmark.triangle.fill"
        case .stale, .missing, .unknown:
            return "arrow.clockwise.circle"
        }
    }

    private func freshnessColor(for state: WatchFreshnessState) -> Color {
        switch state {
        case .fresh:
            return RevaWatch.normal
        case .error:
            return RevaWatch.risk
        case .stale, .missing, .unknown:
            return RevaWatch.caution
        }
    }

    private func timeWindowLabel(_ value: String?) -> String? {
        guard let value, !value.isEmpty else { return nil }
        switch value {
        case "morning": return "上午"
        case "noon": return "午间"
        case "afternoon": return "下午"
        case "evening": return "晚间"
        case "bedtime": return "睡前"
        case "anytime": return "任意时间"
        default: return value
        }
    }

    private func iconName(for kind: String) -> String {
        switch kind {
        case "training", "activity", "exercise":
            return "figure.strengthtraining.traditional"
        case "medication":
            return "pills.fill"
        case "supplement":
            return "leaf.fill"
        case "hydration":
            return "drop.fill"
        case "diet":
            return "fork.knife"
        default:
            return "target"
        }
    }
}
