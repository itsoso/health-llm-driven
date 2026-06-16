import SwiftUI

/// 关键提醒屏(Reva 深色面):每条 push 一个圆角行,左侧 tier 竖条(P0=risk 红 / P1=caution 黄)。
/// 标题 ink1 + detail ink2。空态「暂无提醒」。
struct PushListView: View {
    @ObservedObject var store: WatchStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                let items = store.summary?.pushItems ?? []
                if items.isEmpty {
                    emptyState
                } else {
                    ForEach(items) { item in
                        pushRow(item)
                    }
                }
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
        }
        .background(RevaWatch.focusBg)
        .navigationTitle("提醒")
    }

    private var emptyState: some View {
        VStack(spacing: 6) {
            Image(systemName: "bell.slash")
                .font(.title3)
                .foregroundStyle(RevaWatch.ink2)
            Text("暂无提醒")
                .font(.footnote)
                .foregroundStyle(RevaWatch.ink2)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
    }

    private func pushRow(_ item: WatchPushItem) -> some View {
        HStack(alignment: .top, spacing: 10) {
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(tierColor(item))
                .frame(width: 4)
            VStack(alignment: .leading, spacing: 3) {
                Text(item.title)
                    .font(.body)
                    .foregroundStyle(RevaWatch.ink1)
                    .fixedSize(horizontal: false, vertical: true)
                if let d = item.detail, !d.isEmpty {
                    Text(d)
                        .font(.caption2)
                        .foregroundStyle(RevaWatch.ink2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: RevaWatch.radiusRow, style: .continuous)
                .fill(RevaWatch.focusBg2)
        )
        .overlay(
            RoundedRectangle(cornerRadius: RevaWatch.radiusRow, style: .continuous)
                .stroke(RevaWatch.focusLine, lineWidth: 1)
        )
    }

    private func tierColor(_ item: WatchPushItem) -> Color {
        item.isUrgent ? RevaWatch.risk : RevaWatch.caution
    }
}
