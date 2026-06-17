import SwiftUI
#if canImport(WatchKit)
import WatchKit
#endif

private enum QuickRecordDialFocus: Hashable {
    case water
    case pushups
    case run
}

/// 打点屏(Reva 深色面):圆角 tile 按钮一键记录(喝水/运动/语音记餐)。
/// 校验走 WatchCompanionCore.QuickRecord;成功显绿、失败显 store.lastError(fail loud)。
struct QuickRecordView: View {
    @ObservedObject var store: WatchStore
    @State private var waterAmountML = QuickRecordDials.waterML.defaultValue
    @State private var pushupReps = QuickRecordDials.pushupReps.defaultValue
    @State private var runDurationMin = QuickRecordDials.runDurationMin.defaultValue
    @FocusState private var focusedDial: QuickRecordDialFocus?

    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                adjustableRecordTile(
                    icon: "drop.fill",
                    title: "喝水",
                    value: "\(QuickRecordDials.waterML.intValue(waterAmountML))",
                    unit: "ml",
                    amount: $waterAmountML,
                    spec: QuickRecordDials.waterML,
                    focus: .water
                ) {
                    let ml = QuickRecordDials.waterML.intValue(waterAmountML)
                    Task { await store.submit { try QuickRecord.water(amountML: ml) } }
                }

                adjustableRecordTile(
                    icon: "figure.strengthtraining.traditional",
                    title: "俯卧撑",
                    value: "\(QuickRecordDials.pushupReps.intValue(pushupReps))",
                    unit: "次",
                    amount: $pushupReps,
                    spec: QuickRecordDials.pushupReps,
                    focus: .pushups
                ) {
                    let reps = QuickRecordDials.pushupReps.intValue(pushupReps)
                    Task { await store.submit { try QuickRecord.exercise(type: "俯卧撑", reps: reps) } }
                }

                adjustableRecordTile(
                    icon: "figure.run",
                    title: "跑步",
                    value: "\(QuickRecordDials.runDurationMin.intValue(runDurationMin))",
                    unit: "分钟",
                    amount: $runDurationMin,
                    spec: QuickRecordDials.runDurationMin,
                    focus: .run
                ) {
                    let minutes = QuickRecordDials.runDurationMin.snapped(runDurationMin)
                    Task { await store.submit { try QuickRecord.exercise(type: "跑步", durationMin: minutes) } }
                }

                tile(icon: "mic.fill", label: "语音记一餐") {
                    Task {
                        let text = await dictate()
                        guard let text, !text.isEmpty else { return }
                        await store.submit { try QuickRecord.dietVoice(rawText: text) }
                    }
                }

                tile(icon: "waveform.path.ecg", label: store.symptomSubmitting ? "记录中..." : "语音记症状") {
                    Task {
                        guard !store.symptomSubmitting else { return }
                        let text = await dictate()
                        guard let text, !text.isEmpty else { return }
                        await store.submitSymptom(rawText: text)
                        if let result = store.symptomResult {
                            playSymptomHaptic(result.hapticKind)
                        }
                    }
                }

                if let draft = store.pendingDietDraft {
                    dietDraftPanel(draft)
                }

                if let result = store.symptomResult {
                    symptomSafetyPanel(result)
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

    private func adjustableRecordTile(
        icon: String,
        title: String,
        value: String,
        unit: String,
        amount: Binding<Double>,
        spec: QuickRecordDialSpec,
        focus: QuickRecordDialFocus,
        action: @escaping () -> Void
    ) -> some View {
        let isFocused = focusedDial == focus
        return VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 10) {
                Image(systemName: icon)
                    .font(.body)
                    .foregroundStyle(RevaWatch.greenBright)
                    .frame(width: 22)
                Text(title)
                    .font(.body)
                    .foregroundStyle(RevaWatch.ink1)
                    .lineLimit(1)
                Spacer(minLength: 4)
                HStack(alignment: .firstTextBaseline, spacing: 2) {
                    Text(value)
                        .font(RevaWatch.monoNumber(17, weight: .semibold))
                        .foregroundStyle(RevaWatch.greenBright)
                    Text(unit)
                        .font(.caption2)
                        .foregroundStyle(RevaWatch.ink2)
                }
            }

            HStack(spacing: 8) {
                dialAdjustButton(systemImage: "minus.circle", focus: focus) {
                    amount.wrappedValue = spec.snapped(amount.wrappedValue - spec.step)
                }
                Button {
                    focusedDial = focus
                    amount.wrappedValue = spec.snapped(amount.wrappedValue)
                    action()
                } label: {
                    Label("记录", systemImage: "checkmark.circle.fill")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(RevaWatch.greenBright)
                        .lineLimit(1)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: RevaWatch.radiusRow, style: .continuous)
                                .fill(RevaWatch.focusBg)
                        )
                }
                .buttonStyle(.plain)
                dialAdjustButton(systemImage: "plus.circle", focus: focus) {
                    amount.wrappedValue = spec.snapped(amount.wrappedValue + spec.step)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
                .fill(RevaWatch.focusBg2)
        )
        .overlay(
            RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
                .stroke(isFocused ? RevaWatch.greenBright.opacity(0.75) : RevaWatch.focusLine, lineWidth: 1)
        )
        .focusable(true)
        .focused($focusedDial, equals: focus)
        .digitalCrownRotation(
            amount,
            from: spec.lowerBound,
            through: spec.upperBound,
            by: spec.step,
            sensitivity: .medium,
            isContinuous: false,
            isHapticFeedbackEnabled: true
        )
    }

    private func dialAdjustButton(
        systemImage: String,
        focus: QuickRecordDialFocus,
        action: @escaping () -> Void
    ) -> some View {
        Button {
            focusedDial = focus
            action()
        } label: {
            Image(systemName: systemImage)
                .font(.caption)
                .foregroundStyle(RevaWatch.ink2)
                .frame(width: 32, height: 28)
                .background(
                    RoundedRectangle(cornerRadius: RevaWatch.radiusRow, style: .continuous)
                        .fill(RevaWatch.focusBg)
                )
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

    /// 安全裁决面板。**tone 完全由 Core.displayBanner 决定,View 不自判绿灯。**
    /// critical → 红底大字 + 大「拨打 120」行;评估未完成(caution)→ 橙底,绝不绿;
    /// 仅 isReassuringSafe(=tone .safe)才中性绿调。
    @ViewBuilder
    private func symptomSafetyPanel(_ result: SymptomEvalResult) -> some View {
        let banner = result.displayBanner
        let tone = banner.tone
        let isCrit = result.isCritical
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: symptomIcon(for: tone))
                    .font(isCrit ? .body : .caption)
                    .foregroundStyle(symptomColor(for: tone))
                Text(symptomToneLabel(for: tone))
                    .font(.caption2)
                    .fontWeight(.semibold)
                    .foregroundStyle(symptomColor(for: tone))
                Spacer(minLength: 0)
                Button {
                    store.clearSymptomResult()
                } label: {
                    Image(systemName: "xmark")
                        .font(.caption2)
                        .foregroundStyle(RevaWatch.ink2)
                        .frame(width: 24, height: 22)
                }
                .buttonStyle(.plain)
            }

            Text(banner.title)
                .font(isCrit ? .headline : .caption)
                .fontWeight(isCrit ? .bold : .semibold)
                .foregroundStyle(tone == .safe ? RevaWatch.ink1 : symptomColor(for: tone))
                .lineLimit(isCrit ? 3 : 2)

            if let action = banner.action, !action.isEmpty {
                Text(action)
                    .font(isCrit ? .caption : .caption2)
                    .foregroundStyle(RevaWatch.ink1)
                    .lineLimit(isCrit ? 6 : 4)
                    .fixedSize(horizontal: false, vertical: true)
            }

            // critical 冗余强调「拨打 120」立成大动作行,不依赖用户读完长句。
            if isCrit {
                Label("情况紧急请拨打 120", systemImage: "phone.fill")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: RevaWatch.radiusRow, style: .continuous)
                            .fill(RevaWatch.risk)
                    )
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(symptomPanelBackground(for: tone))
    }

    private func symptomPanelBackground(for tone: SymptomBanner.Tone) -> some View {
        RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
            .fill(symptomPanelFill(for: tone))
            .overlay(
                RoundedRectangle(cornerRadius: RevaWatch.radiusTile, style: .continuous)
                    .stroke(symptomPanelStroke(for: tone), lineWidth: tone == .critical ? 2 : 1)
            )
    }

    private func symptomPanelStroke(for tone: SymptomBanner.Tone) -> Color {
        switch tone {
        case .critical:
            return RevaWatch.risk
        case .high, .caution:
            return RevaWatch.caution
        case .safe:
            return RevaWatch.focusLine
        }
    }

    private func symptomPanelFill(for tone: SymptomBanner.Tone) -> Color {
        switch tone {
        case .critical:
            return RevaWatch.risk.opacity(0.16)
        case .high, .caution:
            return RevaWatch.caution.opacity(0.12)
        case .safe:
            return RevaWatch.focusBg2
        }
    }

    private func symptomColor(for tone: SymptomBanner.Tone) -> Color {
        switch tone {
        case .critical:
            return RevaWatch.risk
        case .high, .caution:
            return RevaWatch.caution
        case .safe:
            return RevaWatch.normal
        }
    }

    private func symptomIcon(for tone: SymptomBanner.Tone) -> String {
        switch tone {
        case .critical:
            return "cross.case.fill"
        case .high, .caution:
            return "exclamationmark.triangle.fill"
        case .safe:
            return "checkmark.circle.fill"
        }
    }

    private func symptomToneLabel(for tone: SymptomBanner.Tone) -> String {
        switch tone {
        case .critical:
            return "需要立即关注"
        case .high:
            return "安全提醒"
        case .caution:
            return "需复核"
        case .safe:
            return "已记录"
        }
    }

    private func playSymptomHaptic(_ haptic: SymptomHaptic) {
        #if canImport(WatchKit)
        let type: WKHapticType
        switch haptic {
        case .strong:
            type = .failure
        case .notify:
            type = .notification
        case .click:
            type = .click
        }
        WKInterfaceDevice.current().play(type)
        #endif
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
