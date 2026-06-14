import SwiftUI
import HealthAgentMacCore

struct OperatingReviewSummaryView: View {
    let summary: OperatingReviewSummary?
    let isLoading: Bool
    let onOpen: () -> Void

    private var strongExecution: Bool {
        summary?.items.contains(where: { $0.key == "completion_rate" && $0.accent }) == true
    }

    var body: some View {
        Button(action: onOpen) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .center, spacing: 10) {
                    Image(systemName: "checkmark.circle")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(strongExecution ? .blue : .secondary)
                        .frame(width: 34, height: 34)
                        .background(Color.blue.opacity(0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("执行复盘")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.blue)
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
                        Text(highlight.label)
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(.secondary)
                        Text(highlight.value)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(highlight.positive ? .green : .orange)
                            .lineLimit(1)
                        Text(highlight.detail)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 7)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background((highlight.positive ? Color.green : Color.orange).opacity(0.10), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                }

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 74), spacing: 8)], spacing: 8) {
                    ForEach(items) { item in
                        VStack(spacing: 3) {
                            Text(item.value)
                                .font(.callout.weight(.bold))
                                .foregroundStyle(item.accent ? .blue : .primary)
                                .lineLimit(1)
                            Text(item.label)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        .padding(.vertical, 7)
                        .frame(maxWidth: .infinity)
                        .background(item.accent ? Color.blue.opacity(0.09) : Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                    }
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .appCard(padding: 14)
        .help("Ask Agent about execution review")
    }

    private var title: String {
        if let summary { return summary.title }
        return isLoading ? "执行复盘检查中" : "执行复盘未加载"
    }

    private var subtitle: String {
        if let summary { return summary.subtitle }
        return isLoading ? "正在读取最近行动完成情况。" : "点击让 Agent 复盘最近执行。"
    }

    private var items: [OperatingReviewSummaryItem] {
        if let summary { return summary.items }
        let value = isLoading ? "…" : "—"
        return [
            OperatingReviewSummaryItem(key: "completion_rate", label: "完成率", value: value, accent: false),
            OperatingReviewSummaryItem(key: "completed", label: "已完成", value: value, accent: false),
            OperatingReviewSummaryItem(key: "total", label: "总行动", value: value, accent: false),
            OperatingReviewSummaryItem(key: "learnable", label: "可学习", value: value, accent: false)
        ]
    }
}
