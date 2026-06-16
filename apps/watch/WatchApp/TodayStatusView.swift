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
        let score = store.summary?.status.readinessScore
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
                    Text("待同步")
                        .font(.footnote)
                        .foregroundStyle(RevaWatch.ink2)
                }
            }
            Spacer(minLength: 0)
        }
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
        Button {
            Task { await store.completeAction(action) }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: store.completing ? "hourglass" : "checkmark.circle")
                    .font(.footnote)
                    .foregroundStyle(RevaWatch.greenBright)
                Text(action.title)
                    .font(.body)
                    .foregroundStyle(RevaWatch.ink1)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
                Text("已做")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(RevaWatch.greenBright)
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
        .buttonStyle(.plain)
        .disabled(store.completing)
    }

    private func readonlyActionTile(_ action: WatchTopAction) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "target")
                .font(.footnote)
                .foregroundStyle(RevaWatch.greenBright)
            Text(action.title)
                .font(.body)
                .foregroundStyle(RevaWatch.ink1)
                .fixedSize(horizontal: false, vertical: true)
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

    // MARK: - Pending count

    private func pendingRow(_ pending: Int) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "checklist")
                .font(.caption2)
                .foregroundStyle(RevaWatch.ink2)
            Text("待打点 ")
                .font(.caption)
                .foregroundStyle(RevaWatch.ink2)
            + Text("\(pending)")
                .font(RevaWatch.monoNumber(13, weight: .semibold))
                .foregroundStyle(RevaWatch.ink1)
            + Text(" 项")
                .font(.caption)
                .foregroundStyle(RevaWatch.ink2)
        }
    }
}
