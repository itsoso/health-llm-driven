import SwiftUI
import HealthAgentMacCore

struct HealthOperatingReviewView: View {
    let client: HealthOperatingReviewClient
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var review: HealthOperatingReview?
    @State private var selectedWindowDays = 30
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var loaded = false

    private let windowOptions = [7, 30, 90]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                content
            }
            .frame(maxWidth: 1120, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(28)
        }
        .background(backgroundGradient.ignoresSafeArea())
        .task {
            guard !loaded else { return }
            loaded = true
            await reload()
        }
    }

    private var backgroundGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color(nsColor: .windowBackgroundColor),
                Color.teal.opacity(0.045),
                Color(nsColor: .windowBackgroundColor)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text(appText("Prediction Review", appLanguageRaw))
                    .font(.largeTitle.bold())
                Text(appText("Daily plan execution, prediction backtest, confidence changes, and next steps.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Picker(appText("Window", appLanguageRaw), selection: $selectedWindowDays) {
                ForEach(windowOptions, id: \.self) { days in
                    Text("\(days)\(appText("days", appLanguageRaw))").tag(days)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 210)
            .onChange(of: selectedWindowDays) { _, _ in
                Task { await reload() }
            }
            if isLoading {
                ProgressView().controlSize(.small)
            }
            Button(appText("Refresh", appLanguageRaw)) {
                Task { await reload() }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if let errorMessage {
            Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                .font(.callout)
                .foregroundStyle(.red)
        }

        if let review {
            summaryCard(review)
            predictionBacktestCard(review)
        } else if !isLoading && errorMessage == nil {
            emptyState
        }
    }

    private var emptyState: some View {
        VStack(alignment: .center, spacing: 10) {
            Image(systemName: "chart.xyaxis.line")
                .font(.system(size: 34))
                .foregroundStyle(.secondary)
            Text(appText("No review loaded yet.", appLanguageRaw))
                .font(.headline)
            Text(appText("Refresh after daily plan execution data is available.", appLanguageRaw))
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, minHeight: 190, alignment: .center)
        .appCard()
    }

    private func summaryCard(_ review: HealthOperatingReview) -> some View {
        HStack(spacing: 12) {
            ReviewSummaryPill(
                title: appText("Completion", appLanguageRaw),
                value: "\(HealthOperatingReviewPresentation.completionPercent(review))%",
                systemImage: "checkmark.seal.fill",
                tone: review.execution.completionRate >= 0.7 ? "green" : "orange"
            )
            ReviewSummaryPill(
                title: appText("Completed", appLanguageRaw),
                value: "\(review.execution.completedEvents)/\(review.execution.totalEvents)",
                systemImage: "list.bullet.clipboard",
                tone: "blue"
            )
            ReviewSummaryPill(
                title: appText("Predictions", appLanguageRaw),
                value: "\(review.predictionBacktest?.readyCandidateCount ?? 0)",
                systemImage: "chart.line.uptrend.xyaxis",
                tone: "teal"
            )
            ReviewSummaryPill(
                title: appText("Window", appLanguageRaw),
                value: "\(review.windowDays)\(appText("days", appLanguageRaw))",
                systemImage: "calendar",
                tone: "secondary"
            )
        }
        .appCard()
    }

    @ViewBuilder
    private func predictionBacktestCard(_ review: HealthOperatingReview) -> some View {
        let backtest = review.predictionBacktest
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center, spacing: 10) {
                Label(appText("Prediction Backtest", appLanguageRaw), systemImage: "scope")
                    .font(.title3.bold())
                Spacer()
                Text(statusLabel(backtest?.status))
                    .font(.caption.weight(.bold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(statusColor(backtest?.status).opacity(0.14), in: Capsule())
                    .foregroundStyle(statusColor(backtest?.status))
            }

            if let backtest, backtest.status == "ready", !backtest.results.isEmpty {
                LazyVStack(spacing: 12) {
                    ForEach(backtest.results) { result in
                        PredictionResultCard(
                            result: result,
                            boundary: HealthOperatingReviewPresentation.boundary(for: backtest),
                            appLanguageRaw: appLanguageRaw,
                            onAskAgent: onAskAgent
                        )
                    }
                }
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    Text(appText("Prediction backtest is not ready yet.", appLanguageRaw))
                        .font(.headline)
                    Text(HealthOperatingReviewPresentation.boundary(for: backtest))
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(14)
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
        .appCard()
    }

    private func reload() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            review = try await client.fetchReview(windowDays: selectedWindowDays)
        } catch {
            review = nil
            errorMessage = appText("Could not load health review. Try refresh.", appLanguageRaw)
        }
    }

    private func statusLabel(_ status: String?) -> String {
        switch status {
        case "ready": appText("Ready", appLanguageRaw)
        case "not_ready": appText("Not Ready", appLanguageRaw)
        default: status ?? appText("Unknown", appLanguageRaw)
        }
    }

    private func statusColor(_ status: String?) -> Color {
        switch status {
        case "ready": .green
        case "not_ready": .orange
        default: .secondary
        }
    }
}

private struct ReviewSummaryPill: View {
    let title: String
    let value: String
    let systemImage: String
    let tone: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .foregroundStyle(toneColor(tone))
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(value)
                    .font(.title3.bold().monospacedDigit())
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
        .background(toneColor(tone).opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct PredictionResultCard: View {
    let result: HealthReviewPredictionBacktestResult
    let boundary: String
    let appLanguageRaw: String
    var onAskAgent: ((String, AgentContextItem?) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: statusIcon)
                    .font(.title2)
                    .foregroundStyle(statusColor)
                    .frame(width: 32)
                VStack(alignment: .leading, spacing: 4) {
                    Text(result.actionTitle.isEmpty ? result.metric : result.actionTitle)
                        .font(.headline)
                    Text("\(result.metric) · \(result.verdict)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text(result.verdict)
                    .font(.caption.weight(.bold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(statusColor.opacity(0.14), in: Capsule())
                    .foregroundStyle(statusColor)
            }

            if let summary = HealthOperatingReviewPresentation.nextStepSummary(for: result) {
                Label(summary, systemImage: "arrow.forward.circle.fill")
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(.primary)
            }

            if let reason = result.inconclusiveReason, !reason.isEmpty {
                Label(reason, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout)
                    .foregroundStyle(.orange)
            }

            if let nextStep = result.nextStep {
                VStack(alignment: .leading, spacing: 6) {
                    Text(nextStep.reason)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                    if let hint = nextStep.replanHint, !hint.isEmpty {
                        Text(hint)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            if !result.confidenceHistory.isEmpty {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 10)], spacing: 10) {
                    ForEach(result.confidenceHistory, id: \.stage) { entry in
                        VStack(alignment: .leading, spacing: 5) {
                            Text(entry.confidence)
                                .font(.callout.weight(.semibold))
                            Text(entry.stage)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(entry.reason)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, minHeight: 78, alignment: .topLeading)
                        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    }
                }
            }

            HStack(alignment: .center, spacing: 10) {
                Label(boundary, systemImage: "info.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                if let onAskAgent {
                    Button {
                        onAskAgent(askPrompt, nil)
                    } label: {
                        Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                    }
                    .buttonStyle(.borderless)
                }
            }
        }
        .padding(14)
        .background(Color.secondary.opacity(0.065), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var statusColor: Color {
        switch result.verdict {
        case "met": .green
        case "not_met": .orange
        default: .secondary
        }
    }

    private var statusIcon: String {
        switch result.verdict {
        case "met": "checkmark.seal.fill"
        case "not_met": "arrow.triangle.2.circlepath"
        default: "questionmark.circle.fill"
        }
    }

    private var askPrompt: String {
        let next = result.nextStep?.label ?? "暂无下一步"
        return "请解释这条健康预测复盘：行动=\(result.actionTitle)，指标=\(result.metric)，结论=\(result.verdict)，下一步=\(next)。请强调这是观察性复盘，不是诊断或处方。"
    }
}
