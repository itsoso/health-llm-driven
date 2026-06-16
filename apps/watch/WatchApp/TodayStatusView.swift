import SwiftUI

/// 今日状态屏:状态灯 + headline + readiness + 待办计数。腕上一眼看完。
struct TodayStatusView: View {
    @ObservedObject var store: WatchStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                if let st = store.summary?.status {
                    HStack(spacing: 8) {
                        Circle().fill(tone(st.light)).frame(width: 14, height: 14)
                        if let score = st.readinessScore, score > 0 {
                            Text("恢复 \(score)").font(.headline)
                        } else {
                            Text(toneText(st.light)).font(.headline)
                        }
                    }
                    Text(st.headline).font(.footnote).foregroundStyle(.secondary)
                }
                if let a = store.summary?.topAction {
                    Divider()
                    Text("最该做").font(.caption2).foregroundStyle(.secondary)
                    Text(a.title).font(.body)
                }
                if let ag = store.summary?.agenda, ag.pending > 0 {
                    Text("待打点 \(ag.pending) 项").font(.caption).foregroundStyle(.secondary)
                }
                if store.loading { ProgressView() }
                if let err = store.lastError {
                    Text(err).font(.caption2).foregroundStyle(.red)
                }
            }
            .padding(.horizontal, 4)
        }
        .navigationTitle("今日")
    }

    private func tone(_ t: ComplicationTone) -> Color {
        switch t {
        case .green: return .green
        case .yellow: return .yellow
        case .red: return .red
        case .gray: return .gray
        }
    }

    private func toneText(_ t: ComplicationTone) -> String {
        switch t {
        case .green: return "状态好"
        case .yellow: return "适度"
        case .red: return "宜休息"
        case .gray: return "无数据"
        }
    }
}
