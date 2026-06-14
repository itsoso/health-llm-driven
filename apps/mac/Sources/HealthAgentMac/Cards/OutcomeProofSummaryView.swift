import SwiftUI
import HealthAgentMacCore

struct OutcomeProofSummaryView: View {
    let summary: OutcomeProofSummary?
    let isLoading: Bool
    let onOpen: () -> Void

    private var hasWin: Bool {
        summary?.items.contains(where: { $0.key == "improved" && $0.value != "0" }) == true
    }

    var body: some View {
        Button(action: onOpen) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .center, spacing: 10) {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(hasWin ? .green : .teal)
                        .frame(width: 34, height: 34)
                        .background((hasWin ? Color.green : Color.teal).opacity(0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("个人证据")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(hasWin ? .green : .teal)
                        Text(title)
                            .font(.headline.weight(.semibold))
                            .foregroundStyle(.primary)
                            .lineLimit(2)
                    }
                    Spacer()
                    if isLoading {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.secondary)
                    }
                }

                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)

                if let highlight = summary?.highlight {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(highlight.title)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                        Text(highlight.detail)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(hasWin ? .green : .teal)
                            .lineLimit(1)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 7)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background((hasWin ? Color.green : Color.teal).opacity(0.10), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                }

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 74), spacing: 8)], spacing: 8) {
                    ForEach(items) { item in
                        VStack(spacing: 3) {
                            Text(item.value)
                                .font(.callout.weight(.bold))
                                .foregroundStyle(item.accent ? (hasWin ? .green : .teal) : .primary)
                                .lineLimit(1)
                            Text(item.label)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        .padding(.vertical, 7)
                        .frame(maxWidth: .infinity)
                        .background(item.accent ? Color.green.opacity(0.09) : Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                    }
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .appCard(padding: 14)
        .help("Ask Agent about personal outcome proof")
    }

    private var title: String {
        if let summary { return summary.title }
        return isLoading ? "个人证据检查中" : "个人证据未加载"
    }

    private var subtitle: String {
        if let summary { return summary.subtitle }
        return isLoading ? "正在读取 AI 建议的验证结果。" : "点击让 Agent 解释最近闭环。"
    }

    private var items: [OutcomeProofSummaryItem] {
        if let summary { return summary.items }
        let value = isLoading ? "…" : "—"
        return [
            OutcomeProofSummaryItem(key: "graded", label: "已验证", value: value, accent: false),
            OutcomeProofSummaryItem(key: "improved", label: "已改善", value: value, accent: false),
            OutcomeProofSummaryItem(key: "verifying", label: "验证中", value: value, accent: false),
            OutcomeProofSummaryItem(key: "rate", label: "改善率", value: value, accent: false)
        ]
    }
}
