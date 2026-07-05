import SwiftUI
#if canImport(WidgetKit)
import WidgetKit
#endif

/// 表盘 Complication / Smart Stack(WidgetKit)。展示状态用 ComplicationState(已 swift test)。
/// 真机验证:数据经 App Group / WC 缓存的最近一次 WatchSummary 派生。
#if canImport(WidgetKit) && os(watchOS)

struct RevaComplicationEntry: TimelineEntry {
    let date: Date
    let state: ComplicationState
}

struct RevaComplicationProvider: TimelineProvider {
    func placeholder(in context: Context) -> RevaComplicationEntry {
        .init(date: Date(), state: .init(tone: .gray, shortText: "小巴", fullText: "小巴", urgentBadge: 0))
    }

    func getSnapshot(in context: Context, completion: @escaping (RevaComplicationEntry) -> Void) {
        completion(.init(date: Date(), state: ComplicationCache.load()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<RevaComplicationEntry>) -> Void) {
        let entry = RevaComplicationEntry(date: Date(), state: ComplicationCache.load())
        // 30 分钟后让系统再来取(WC/刷新会更新缓存)
        completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(1800))))
    }
}

struct RevaComplicationView: View {
    let entry: RevaComplicationEntry
    var body: some View {
        VStack(spacing: 1) {
            HStack(spacing: 3) {
                Circle().fill(color(entry.state.tone)).frame(width: 8, height: 8)
                if entry.state.urgentBadge > 0 {
                    Text("\(entry.state.urgentBadge)").font(.caption2).foregroundStyle(.red)
                }
            }
            Text(entry.state.shortText).font(.caption2).lineLimit(1)
        }
    }
    private func color(_ t: ComplicationTone) -> Color {
        switch t { case .green: .green; case .yellow: .yellow; case .red: .red; case .gray: .gray }
    }
}

@main
struct RevaComplication: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "RevaComplication", provider: RevaComplicationProvider()) { entry in
            RevaComplicationView(entry: entry)
        }
        .configurationDisplayName("小巴今日状态")
        .description("状态灯 + 紧急提醒数")
        .supportedFamilies([.accessoryCircular, .accessoryRectangular, .accessoryInline])
    }
}

#endif
