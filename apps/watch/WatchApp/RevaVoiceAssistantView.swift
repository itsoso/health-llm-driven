import SwiftUI
#if canImport(WatchKit)
import WatchKit
#endif

/// 腕上一问一答入口。只做短安全建议;复杂/医疗风险由后端 `/watch/ask`
/// 升级到 iPhone,本 View 不自行推理、不展开自由诊断长对话。
struct RevaVoiceAssistantView: View {
    @ObservedObject var store: WatchStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                header

                Button {
                    Task {
                        guard !store.askSubmitting else { return }
                        let text = await WatchDictation.present()
                        guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
                        await store.askReva(rawText: text)
                        playAskHaptic(store.askResult)
                    }
                } label: {
                    HStack(spacing: 10) {
                        Image(systemName: store.askSubmitting ? "waveform" : "mic.circle.fill")
                            .font(.title3)
                            .foregroundStyle(RevaWatch.greenBright)
                            .frame(width: 28)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(store.askSubmitting ? "思考中..." : "点 Reva 说一句")
                                .font(.headline)
                                .foregroundStyle(RevaWatch.ink1)
                                .lineLimit(1)
                            Text("饮食、运动、状态先问短答")
                                .font(.caption2)
                                .foregroundStyle(RevaWatch.ink2)
                                .lineLimit(1)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 12)
                    .frame(maxWidth: .infinity)
                    .background(tileBackground)
                }
                .buttonStyle(.plain)

                if let result = store.askResult {
                    askPanel(result)
                }

                if let error = store.lastError, store.askResult == nil {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption2)
                        .foregroundStyle(RevaWatch.risk)
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(tileBackground)
                }
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
        }
        .background(RevaWatch.focusBg)
        .navigationTitle("问 Reva")
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("腕上短答")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RevaWatch.greenBright)
            Text("复杂问题会转到 iPhone")
                .font(.caption2)
                .foregroundStyle(RevaWatch.ink2)
        }
        .padding(.horizontal, 4)
    }

    private func askPanel(_ result: WatchAskResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: icon(for: result.displayTone))
                    .font(.caption)
                    .foregroundStyle(color(for: result.displayTone))
                Text(label(for: result))
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(color(for: result.displayTone))
                Spacer(minLength: 0)
                Button {
                    store.clearAskResult()
                } label: {
                    Image(systemName: "xmark")
                        .font(.caption2)
                        .foregroundStyle(RevaWatch.ink2)
                        .frame(width: 24, height: 22)
                }
                .buttonStyle(.plain)
            }

            Text(result.answer)
                .font(result.requiresMedicalAttention ? .headline : .caption)
                .fontWeight(result.requiresMedicalAttention ? .bold : .semibold)
                .foregroundStyle(result.displayTone == .normal ? RevaWatch.ink1 : color(for: result.displayTone))
                .lineLimit(result.requiresMedicalAttention ? 5 : 4)
                .fixedSize(horizontal: false, vertical: true)

            if result.escalateToPhone {
                Label("去 iPhone 查看详情", systemImage: "iphone")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(RevaWatch.ink1)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: RevaWatch.radiusRow, style: .continuous)
                            .fill(RevaWatch.focusBg)
                    )
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(panelBackground(for: result.displayTone))
    }

    private func label(for result: WatchAskResponse) -> String {
        if result.requiresMedicalAttention { return "需要立即关注" }
        if result.escalateToPhone { return "需转手机" }
        return "短答"
    }

    private func icon(for tone: WatchAskDisplayTone) -> String {
        switch tone {
        case .normal: return "checkmark.circle.fill"
        case .caution: return "iphone"
        case .risk: return "cross.case.fill"
        }
    }

    private func color(for tone: WatchAskDisplayTone) -> Color {
        switch tone {
        case .normal: return RevaWatch.normal
        case .caution: return RevaWatch.caution
        case .risk: return RevaWatch.risk
        }
    }

    private func panelBackground(for tone: WatchAskDisplayTone) -> some View {
        RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
            .fill(fill(for: tone))
            .overlay(
                RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
                    .stroke(color(for: tone).opacity(tone == .normal ? 0.45 : 0.9), lineWidth: tone == .risk ? 2 : 1)
            )
    }

    private func fill(for tone: WatchAskDisplayTone) -> Color {
        switch tone {
        case .normal: return RevaWatch.focusBg2
        case .caution: return RevaWatch.caution.opacity(0.12)
        case .risk: return RevaWatch.risk.opacity(0.16)
        }
    }

    private var tileBackground: some View {
        RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
            .fill(RevaWatch.focusBg2)
            .overlay(
                RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
                    .stroke(RevaWatch.focusLine, lineWidth: 1)
            )
    }

    private func playAskHaptic(_ result: WatchAskResponse?) {
        #if canImport(WatchKit)
        guard let result else { return }
        if result.requiresMedicalAttention {
            WKInterfaceDevice.current().play(.failure)
        } else if result.escalateToPhone {
            WKInterfaceDevice.current().play(.notification)
        } else {
            WKInterfaceDevice.current().play(.click)
        }
        #endif
    }
}
