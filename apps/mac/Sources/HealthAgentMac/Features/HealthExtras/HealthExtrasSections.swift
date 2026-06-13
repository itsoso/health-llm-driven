import SwiftUI
import HealthAgentMacCore

// MARK: - ② Social connection section
//
// UCLA-3 三题(各 1–3 分,合计 3–9)+ 2 个连接结构 Toggle + 提交。
// 后端 GET 拿当前状态(含 interpretation),POST 提交一次自评。
// 文案诚实:这是自评解读,非诊断。

struct ConnectionSection: View {
    let client: HealthExtrasClient
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var status: ConnectionStatus?
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var loaded = false

    // 三题各 1–3 分,默认 1(最少孤独感)。
    @State private var lackCompanionship = 1
    @State private var feltLeftOut = 1
    @State private var feltIsolated = 1
    @State private var hasConfidant = true
    @State private var inStableGroup = true
    @State private var isSubmitting = false
    @State private var submitError: String?

    private var uclaScore: Int { lackCompanionship + feltLeftOut + feltIsolated }

    var body: some View {
        SectionPanel(
            title: appText("Social Connection", appLanguageRaw),
            systemImage: "person.2.wave.2"
        ) {
            content
        }
        .task {
            guard !loaded else { return }
            loaded = true
            await reload()
        }
    }

    @ViewBuilder
    private var content: some View {
        if let loadError {
            ErrorLine(message: loadError)
        } else {
            statusBlock
            Divider()
            formBlock
        }
    }

    // MARK: Current status

    @ViewBuilder
    private var statusBlock: some View {
        if let status {
            VStack(alignment: .leading, spacing: 6) {
                if status.hasCheckin {
                    HStack(spacing: 10) {
                        if let score = status.uclaScore {
                            CountBadge(
                                value: "\(score)",
                                label: appText("UCLA-3 (3–9)", appLanguageRaw),
                                tint: scoreTint(score)
                            )
                        }
                        if status.due {
                            Label(appText("Due for a new check-in", appLanguageRaw), systemImage: "clock.badge.exclamationmark")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.orange)
                        }
                        Spacer()
                    }
                    if let days = status.daysSince {
                        Text(daysSinceText(days, lastDate: status.lastDate))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                if !status.interpretation.isEmpty {
                    Text(status.interpretation)
                        .font(.callout)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        } else if isLoading {
            ProgressView().controlSize(.small)
        }
    }

    private func daysSinceText(_ days: Int, lastDate: String?) -> String {
        let template = appText("Last check-in %d day(s) ago.", appLanguageRaw)
        let base = String(format: template, days)
        if let lastDate, !lastDate.isEmpty {
            return base + " (\(lastDate))"
        }
        return base
    }

    private func scoreTint(_ score: Int) -> Color {
        // 3–4 低孤独 绿;5–6 中 橙;7–9 高 红。仅自评着色,非诊断。
        if score <= 4 { return .green }
        if score <= 6 { return .orange }
        return .red
    }

    // MARK: Self-assessment form

    private var formBlock: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(appText("Quick self-assessment", appLanguageRaw))
                .font(.headline)
            uclaPicker(
                title: appText("How often do you feel you lack companionship?", appLanguageRaw),
                value: $lackCompanionship
            )
            uclaPicker(
                title: appText("How often do you feel left out?", appLanguageRaw),
                value: $feltLeftOut
            )
            uclaPicker(
                title: appText("How often do you feel isolated from others?", appLanguageRaw),
                value: $feltIsolated
            )
            Toggle(appText("I have someone I can confide in.", appLanguageRaw), isOn: $hasConfidant)
            Toggle(appText("I belong to a stable group or community.", appLanguageRaw), isOn: $inStableGroup)

            HStack {
                Text(String(format: appText("Score: %d / 9", appLanguageRaw), uclaScore))
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(scoreTint(uclaScore))
                Spacer()
                if isSubmitting {
                    ProgressView().controlSize(.small)
                }
                Button {
                    Task { await submit() }
                } label: {
                    Label(appText("Submit Check-in", appLanguageRaw), systemImage: "paperplane")
                }
                .buttonStyle(.borderedProminent)
                .disabled(isSubmitting)
            }
            if let submitError {
                ErrorLine(message: submitError)
            }
            Label(appText("Self-assessment interpretation, not a diagnosis.", appLanguageRaw), systemImage: "info.circle")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func uclaPicker(title: String, value: Binding<Int>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.callout)
                .frame(maxWidth: .infinity, alignment: .leading)
            Picker(title, selection: value) {
                Text(appText("Hardly ever", appLanguageRaw)).tag(1)
                Text(appText("Some of the time", appLanguageRaw)).tag(2)
                Text(appText("Often", appLanguageRaw)).tag(3)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
        }
    }

    // MARK: Networking

    private func reload() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            let fetched = try await client.fetchConnectionStatus()
            status = fetched
            applyToForm(fetched)
        } catch {
            status = nil
            loadError = appText("Could not load social connection. Try again.", appLanguageRaw)
        }
    }

    /// 把已有 check-in 回填到表单(总分平均拆三题,仅作初值,提交以三题为准)。
    private func applyToForm(_ status: ConnectionStatus) {
        if let confidant = status.hasConfidant { hasConfidant = confidant }
        if let group = status.inStableGroup { inStableGroup = group }
        guard let total = status.uclaScore else { return }
        let clamped = min(9, max(3, total))
        let base = clamped / 3
        var remainder = clamped - base * 3
        var values = [base, base, base]
        var index = 0
        while remainder > 0 {
            values[index] += 1
            remainder -= 1
            index += 1
        }
        lackCompanionship = min(3, max(1, values[0]))
        feltLeftOut = min(3, max(1, values[1]))
        feltIsolated = min(3, max(1, values[2]))
    }

    private func submit() async {
        isSubmitting = true
        submitError = nil
        defer { isSubmitting = false }
        do {
            let response = try await client.submitConnectionCheckin(
                uclaScore: uclaScore,
                hasConfidant: hasConfidant,
                inStableGroup: inStableGroup,
                notes: nil
            )
            if let updated = response.status {
                status = updated
            } else {
                await reload()
            }
        } catch {
            submitError = appText("Could not submit check-in. Try again.", appLanguageRaw)
        }
    }
}

// MARK: - ③ Causal links section

struct CausalLinksSection: View {
    let client: HealthExtrasClient
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var report: CausalLinksReport?
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var loaded = false

    var body: some View {
        SectionPanel(
            title: appText("Causal Links", appLanguageRaw),
            systemImage: "arrow.triangle.branch"
        ) {
            content
        }
        .task {
            guard !loaded else { return }
            loaded = true
            await reload()
        }
    }

    @ViewBuilder
    private var content: some View {
        if let loadError {
            ErrorLine(message: loadError)
        } else if let report {
            if report.interventionEffects.isEmpty {
                Text(appText("No medication-metric associations yet.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(report.interventionEffects) { effect in
                    EffectRow(effect: effect, appLanguageRaw: appLanguageRaw)
                }
            }
            if !report.note.isEmpty {
                Label(report.note, systemImage: "info.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            askButton(report)
        } else if isLoading {
            ProgressView().controlSize(.small)
        }
    }

    @ViewBuilder
    private func askButton(_ report: CausalLinksReport) -> some View {
        if let onAskAgent, !report.interventionEffects.isEmpty {
            HStack {
                Spacer()
                Button {
                    onAskAgent(askPrompt(report), nil)
                } label: {
                    Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                }
                .buttonStyle(.borderless)
            }
        }
    }

    private func askPrompt(_ report: CausalLinksReport) -> String {
        var parts: [String] = ["请解读这些用药前后的指标变化(描述性关联,非严格因果):"]
        for effect in report.interventionEffects {
            let before = effect.beforeMean.map { String(format: "%.2f", $0) } ?? "?"
            let after = effect.afterMean.map { String(format: "%.2f", $0) } ?? "?"
            parts.append("• \(effect.medication) → \(effect.metricLabel):\(before) → \(after)")
        }
        parts.append("这些可能含饮食/运动等其他因素,非严格因果。请说明哪些值得关注。")
        return parts.joined(separator: "\n")
    }

    private func reload() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            report = try await client.fetchCausalLinks()
        } catch {
            report = nil
            loadError = appText("Could not load causal links. Try again.", appLanguageRaw)
        }
    }
}

/// 一条用药→指标变化行。before → after + delta/pct + 样本数。
private struct EffectRow: View {
    let effect: InterventionEffect
    let appLanguageRaw: String

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: effect.isDecrease ? "arrow.down.right.circle.fill" : "arrow.up.right.circle.fill")
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 3) {
                Text("\(effect.medication) → \(effect.metricLabel)")
                    .font(.callout.weight(.semibold))
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(changeDetail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var changeDetail: String {
        let before = effect.beforeMean.map { String(format: "%.2f", $0) } ?? "—"
        let after = effect.afterMean.map { String(format: "%.2f", $0) } ?? "—"
        var detail = "\(before) → \(after)"
        if let pct = effect.pct {
            detail += String(format: " (%+.0f%%)", pct)
        }
        let template = appText("n=%d → %d", appLanguageRaw)
        detail += "  " + String(format: template, effect.nBefore, effect.nAfter)
        return detail
    }
}
