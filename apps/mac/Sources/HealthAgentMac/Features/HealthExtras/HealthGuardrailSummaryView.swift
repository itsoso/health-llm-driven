import SwiftUI
import HealthAgentMacCore

struct HealthGuardrailSummaryView: View {
    let summary: HealthGuardrailSummary?
    let isLoading: Bool
    let onOpen: () -> Void

    private var hasAttention: Bool {
        (summary?.attentionCount ?? 0) > 0
    }

    var body: some View {
        Button(action: onOpen) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .center, spacing: 10) {
                    Image(systemName: "shield.checkered")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(hasAttention ? .orange : .teal)
                        .frame(width: 34, height: 34)
                        .background((hasAttention ? Color.orange : Color.teal).opacity(0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("健康守门")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(hasAttention ? .orange : .teal)
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

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 8)], spacing: 8) {
                    ForEach(items) { item in
                        VStack(alignment: .leading, spacing: 3) {
                            HStack(spacing: 4) {
                                Image(systemName: item.attention ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                                    .font(.caption2)
                                    .foregroundStyle(item.attention ? .orange : .teal)
                                Text(item.label)
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                            Text(item.value)
                                .font(.caption.weight(.bold))
                                .foregroundStyle(item.attention ? .orange : .primary)
                                .lineLimit(1)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 7)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(item.attention ? Color.orange.opacity(0.09) : Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 9, style: .continuous)
                                .stroke((item.attention ? Color.orange : Color.primary).opacity(0.08), lineWidth: 1)
                        )
                    }
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .appCard(padding: 14)
        .help("Open Health Extras")
    }

    private var title: String {
        if let summary { return summary.title }
        return isLoading ? "健康守门检查中" : "健康守门未加载"
    }

    private var subtitle: String {
        if let summary { return summary.subtitle }
        return isLoading ? "正在检查数据可信度、用药梳理和慢病维护项。" : "打开健康进阶查看完整自检。"
    }

    private var items: [HealthGuardrailSummaryItem] {
        if let summary { return summary.items }
        let value = isLoading ? "检查中" : "未加载"
        return [
            HealthGuardrailSummaryItem(key: "data_integrity", label: "数据自检", value: value, attention: false),
            HealthGuardrailSummaryItem(key: "deprescribing", label: "用药梳理", value: value, attention: false),
            HealthGuardrailSummaryItem(key: "connection", label: "社会连接", value: value, attention: false),
            HealthGuardrailSummaryItem(key: "causal_links", label: "指标关联", value: value, attention: false)
        ]
    }
}
