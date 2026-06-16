import SwiftUI

/// 关键推送屏:该到手腕的重要信息(运动/补剂/睡眠/复查),P0 标红在前。
struct PushListView: View {
    @ObservedObject var store: WatchStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text("关键提醒").font(.headline)
                let items = store.summary?.pushItems ?? []
                if items.isEmpty {
                    Text("暂无").font(.caption).foregroundStyle(.secondary)
                } else {
                    ForEach(items) { item in
                        HStack(alignment: .top, spacing: 6) {
                            Circle()
                                .fill(item.isUrgent ? Color.red : Color.orange)
                                .frame(width: 8, height: 8)
                                .padding(.top, 5)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(item.title).font(.body)
                                if let d = item.detail, !d.isEmpty {
                                    Text(d).font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
            .padding(.horizontal, 4)
        }
        .navigationTitle("提醒")
    }
}
