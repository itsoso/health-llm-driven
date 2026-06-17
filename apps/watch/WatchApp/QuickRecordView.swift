import SwiftUI

/// 打点屏(Reva 深色面):圆角 tile 按钮一键记录(喝水/运动/语音记餐)。
/// 校验走 WatchCompanionCore.QuickRecord;成功显绿、失败显 store.lastError(fail loud)。
struct QuickRecordView: View {
    @ObservedObject var store: WatchStore

    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                HStack(spacing: 8) {
                    waterTile(250)
                    waterTile(500)
                }

                tile(icon: "figure.strengthtraining.traditional", label: "俯卧撑 +20") {
                    Task { await store.submit { try QuickRecord.exercise(type: "俯卧撑", reps: 20) } }
                }

                tile(icon: "figure.run", label: "跑步 30 分钟") {
                    Task { await store.submit { try QuickRecord.exercise(type: "跑步", durationMin: 30) } }
                }

                tile(icon: "mic.fill", label: "语音记一餐") {
                    Task {
                        let text = await dictate()
                        guard let text, !text.isEmpty else { return }
                        await store.submit { try QuickRecord.dietVoice(rawText: text) }
                    }
                }

                if let draft = store.pendingDietDraft {
                    dietDraftPanel(draft)
                }

                statusLine
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
        }
        .background(RevaWatch.focusBg)
        .navigationTitle("打点")
    }

    // MARK: - Status feedback (fail loud)

    @ViewBuilder
    private var statusLine: some View {
        if store.lastRecordOK == true {
            Label(store.lastRecordMessage ?? "已记录", systemImage: "checkmark.circle.fill")
                .font(.caption)
                .foregroundStyle(RevaWatch.normal)
        } else if let message = store.lastRecordMessage {
            Label(message, systemImage: "text.badge.checkmark")
                .font(.caption2)
                .foregroundStyle(RevaWatch.caution)
        } else if store.lastRecordOK == false, let e = store.lastError {
            Label(e, systemImage: "exclamationmark.triangle.fill")
                .font(.caption2)
                .foregroundStyle(RevaWatch.risk)
        }
    }

    // MARK: - Tiles

    private func waterTile(_ ml: Int) -> some View {
        Button {
            Task { await store.submit { try QuickRecord.water(amountML: ml) } }
        } label: {
            VStack(spacing: 4) {
                Image(systemName: "drop.fill")
                    .font(.title3)
                    .foregroundStyle(RevaWatch.greenBright)
                HStack(alignment: .firstTextBaseline, spacing: 2) {
                    Text("\(ml)")
                        .font(RevaWatch.monoNumber(16, weight: .semibold))
                        .foregroundStyle(RevaWatch.ink1)
                    Text("ml")
                        .font(.caption2)
                        .foregroundStyle(RevaWatch.ink2)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(tileBackground)
        }
        .buttonStyle(.plain)
    }

    private func tile(icon: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.body)
                    .foregroundStyle(RevaWatch.greenBright)
                    .frame(width: 22)
                Text(label)
                    .font(.body)
                    .foregroundStyle(RevaWatch.ink1)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity)
            .background(tileBackground)
        }
        .buttonStyle(.plain)
    }

    private func dietDraftPanel(_ draft: VoiceFoodDraft) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(draft.summaryLine)
                .font(.caption)
                .foregroundStyle(RevaWatch.ink1)
                .lineLimit(3)
            if let question = draft.clarifyingQuestion, !question.isEmpty {
                Text(question)
                    .font(.caption2)
                    .foregroundStyle(RevaWatch.caution)
                    .lineLimit(2)
            }
            HStack(spacing: 8) {
                Button {
                    Task { await store.confirmDietDraft() }
                } label: {
                    Label("保存", systemImage: "checkmark.circle.fill")
                        .font(.caption2)
                }
                .buttonStyle(.borderedProminent)

                Button {
                    store.clearDietDraft()
                } label: {
                    Image(systemName: "xmark")
                        .font(.caption2)
                        .frame(width: 28, height: 24)
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tileBackground)
    }

    private var tileBackground: some View {
        RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
            .fill(RevaWatch.focusBg2)
            .overlay(
                RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
                    .stroke(RevaWatch.focusLine, lineWidth: 1)
            )
    }

    /// 腕上听写(WKExtension/Dictation)。真机用 presentTextInputController 取语音转写。
    private func dictate() async -> String? {
        await WatchDictation.present()
    }
}
