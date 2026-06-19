import SwiftUI
import HealthAgentMacCore

/// 今日时间线(只读)—— 一条 24h 垂直网格,聚合两层:
/// ① 外部日历事件(GET /calendar/events,真实 start→end 块);
/// ② 健康日程(GET /schedule/today 的药/补剂/餐/运动时点,movement 用处方时长,其余渲成 marker)。
/// 全天事件 → 顶部 strip;"现在"线仅今天。点块 → 右侧 inspector 展开明细。只读,不建/不改/不写回。
///
/// 防卡死(本仓库实测):时间轴块在 GeometryReader 给的**确定宽度**里绝对定位,
/// 不用 fixedSize/ViewThatFits 探测范围宽度(已知 100% CPU 冻结)。
struct DayTimelineView: View {
    let scheduleClient: ScheduleClient
    let calendarClient: CalendarClient
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var schedule: TodaySchedule?
    @State private var events: [CalendarEvent] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var selectedKey: String?
    @State private var didInitialLoad = false

    private var language: AppLanguage { AppLanguage(storedValue: appLanguageRaw) }

    private var merged: DayTimelineLayout.Merged {
        DayTimelineLayout.merge(
            schedule: schedule,
            events: events,
            includeSchedule: true,
            language: language
        )
    }

    private var selectedEntry: DayTimelineLayout.Entry? {
        guard let selectedKey else { return nil }
        return merged.entries.first { $0.key == selectedKey }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            allDayStrip
            content
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .task {
            if !didInitialLoad {
                didInitialLoad = true
                await refresh()
            }
        }
    }

    private var header: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 4) {
                Text(appText("Today Timeline", appLanguageRaw))
                    .font(.largeTitle.weight(.bold))
                Text("\(todayDateLabel) · \(merged.entries.count) \(appText("Timeline Items", appLanguageRaw))")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                Task { await refresh() }
            } label: {
                Label(appText("Refresh", appLanguageRaw), systemImage: isLoading ? "arrow.triangle.2.circlepath" : "arrow.clockwise")
            }
            .disabled(isLoading)
        }
    }

    @ViewBuilder
    private var allDayStrip: some View {
        if !merged.allDay.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(merged.allDay) { entry in
                        HStack(spacing: 6) {
                            Text(appText("All-day", appLanguageRaw))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text(entry.title)
                                .font(.caption)
                                .lineLimit(1)
                        }
                        .padding(.leading, 8)
                        .padding(.trailing, 12)
                        .padding(.vertical, 6)
                        .background(.regularMaterial, in: Capsule())
                        .overlay(alignment: .leading) {
                            Capsule()
                                .fill(hexColor(entry.colorHex))
                                .frame(width: 3)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if isLoading && schedule == nil && events.isEmpty {
            ProgressView(appText("Loading timeline...", appLanguageRaw))
                .frame(maxWidth: .infinity, minHeight: 260)
        } else if let errorMessage {
            ContentUnavailableView(
                appText("Timeline failed to load", appLanguageRaw),
                systemImage: "exclamationmark.triangle",
                description: Text(errorMessage)
            )
            .frame(maxWidth: .infinity, minHeight: 260)
        } else if merged.entries.isEmpty && merged.allDay.isEmpty {
            ContentUnavailableView(
                appText("No timeline items today", appLanguageRaw),
                systemImage: "calendar",
                description: Text(appText("No schedule item or calendar event is on today's timeline.", appLanguageRaw))
            )
            .frame(maxWidth: .infinity, minHeight: 260)
        } else {
            HStack(alignment: .top, spacing: 14) {
                TimelineGrid(
                    entries: merged.entries,
                    selectedKey: selectedKey,
                    onSelect: { key in selectedKey = (selectedKey == key) ? nil : key }
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)

                if let selectedEntry {
                    TimelineInspector(
                        entry: selectedEntry,
                        language: language,
                        onClose: { selectedKey = nil }
                    )
                    .frame(width: 300)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var todayDateLabel: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: language == .zh ? "zh_CN" : "en_US")
        formatter.dateFormat = language == .zh ? "M月d日 EEEE" : "EEE, MMM d"
        return formatter.string(from: Date())
    }

    private func refresh() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        let today = Self.ymd(Date())
        do {
            // 两路并发拉取;任一成功就有内容。schedule 失败不该埋掉 calendar(反之亦然),
            // 但两路都失败才报错 —— 不假装成功。
            async let scheduleResult = scheduleClient.fetchToday()
            async let eventsResult = calendarClient.fetchEvents(from: today, to: today)
            let loadedSchedule = try? await scheduleResult
            let loadedEvents = try? await eventsResult
            if loadedSchedule == nil && loadedEvents == nil {
                // 两路都失败:重抛 schedule 的错给用户看真因。
                _ = try await scheduleClient.fetchToday()
            }
            schedule = loadedSchedule
            events = loadedEvents ?? []
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }

    private static func ymd(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }
}

// MARK: - Grid

private struct TimelineGrid: View {
    let entries: [DayTimelineLayout.Entry]
    let selectedKey: String?
    let onSelect: (String) -> Void

    private static let pxPerMin: CGFloat = 56.0 / 60.0
    private static let hourPx: CGFloat = 60 * pxPerMin
    private static let minBlockPx: CGFloat = 22
    private static let gutterWidth: CGFloat = 52
    private static let blockGap: CGFloat = 3
    private static let rightInset: CGFloat = 8

    private var placements: [String: DayTimelineLayout.Placement] {
        var map: [String: DayTimelineLayout.Placement] = [:]
        for placement in DayTimelineLayout.assignLanes(entries.map(\.block)) {
            map[placement.key] = placement
        }
        return map
    }

    private var nowMinutes: Int {
        let comps = Calendar.current.dateComponents([.hour, .minute], from: Date())
        return (comps.hour ?? 0) * 60 + (comps.minute ?? 0)
    }

    private var totalHeight: CGFloat {
        CGFloat(DayTimelineLayout.dayMinutes) * Self.pxPerMin
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                // 钉死 track 宽度 = 容器宽度,块在确定宽度里绝对定位,避免范围宽度探测卡死。
                GeometryReader { geo in
                    let trackWidth = max(geo.size.width - Self.gutterWidth, 200)
                    ZStack(alignment: .topLeading) {
                        hourLines(trackWidth: trackWidth)
                        hourLabels
                        blocks(trackWidth: trackWidth)
                        nowLine(trackWidth: trackWidth)
                        // 自动滚动锚点:放在 ~现在(或首个事件前 1h)
                        Color.clear
                            .frame(width: 1, height: 1)
                            .offset(y: scrollAnchorY)
                            .id("timeline-anchor")
                    }
                    .frame(width: geo.size.width, height: totalHeight, alignment: .topLeading)
                }
                .frame(height: totalHeight)
            }
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
            .onAppear {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                    withAnimation(.none) {
                        proxy.scrollTo("timeline-anchor", anchor: .center)
                    }
                }
            }
        }
    }

    private var scrollAnchorY: CGFloat {
        let target: Int
        if let firstStart = entries.map(\.startMin).min() {
            target = min(nowMinutes, max(firstStart - 60, 0))
        } else {
            target = nowMinutes
        }
        return CGFloat(DayTimelineLayout.clampDayMinute(target)) * Self.pxPerMin
    }

    private func hourLines(trackWidth: CGFloat) -> some View {
        ForEach(0...24, id: \.self) { hour in
            Rectangle()
                .fill(Color.secondary.opacity(0.16))
                .frame(width: trackWidth - Self.rightInset, height: 1)
                .offset(x: Self.gutterWidth, y: CGFloat(hour) * Self.hourPx)
        }
    }

    private var hourLabels: some View {
        ForEach(0..<24, id: \.self) { hour in
            Text(String(format: "%02d:00", hour))
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(.tertiary)
                .frame(width: Self.gutterWidth - 8, alignment: .trailing)
                .offset(x: 0, y: CGFloat(hour) * Self.hourPx - 7)
        }
    }

    private func blocks(trackWidth: CGFloat) -> some View {
        let placementMap = placements
        let usable = trackWidth - Self.rightInset
        return ForEach(entries) { entry in
            let placement = placementMap[entry.key] ?? DayTimelineLayout.Placement(key: entry.key, lane: 0, lanes: 1)
            let lanes = max(placement.lanes, 1)
            let colWidth = (usable - Self.blockGap * CGFloat(lanes - 1)) / CGFloat(lanes)
            let top = CGFloat(entry.startMin) * Self.pxPerMin
            let height = max(CGFloat(entry.endMin - entry.startMin) * Self.pxPerMin, Self.minBlockPx)
            let left = Self.gutterWidth + CGFloat(placement.lane) * (colWidth + Self.blockGap)
            TimelineBlockView(
                entry: entry,
                width: max(colWidth, 24),
                height: height,
                isActive: selectedKey == entry.key,
                onTap: { onSelect(entry.key) }
            )
            .offset(x: left, y: top)
        }
    }

    @ViewBuilder
    private func nowLine(trackWidth: CGFloat) -> some View {
        let y = CGFloat(DayTimelineLayout.clampDayMinute(nowMinutes)) * Self.pxPerMin
        HStack(spacing: 0) {
            Circle()
                .fill(Color.red)
                .frame(width: 7, height: 7)
            Rectangle()
                .fill(Color.red)
                .frame(height: 1.5)
        }
        .frame(width: trackWidth - Self.rightInset + 4)
        .offset(x: Self.gutterWidth - 3, y: y)
        .allowsHitTesting(false)
    }
}

private struct TimelineBlockView: View {
    let entry: DayTimelineLayout.Entry
    let width: CGFloat
    let height: CGFloat
    let isActive: Bool
    let onTap: () -> Void

    var body: some View {
        let color = hexColor(entry.colorHex)
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 1) {
                Text(entry.title)
                    .font(.system(size: entry.isPoint ? 11.5 : 12.5, weight: .semibold))
                    .lineLimit(entry.isPoint ? 1 : 2)
                if !entry.isPoint && height >= 34 {
                    Text(entry.timeLabel)
                        .font(.system(size: 10.5, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                if !entry.isPoint, height >= 52, let subtitle = entry.subtitle {
                    Text(subtitle)
                        .font(.system(size: 10.5))
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, 7)
            .padding(.vertical, entry.isPoint ? 2 : 5)
            .frame(width: width, height: height, alignment: entry.isPoint ? .leading : .topLeading)
            .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            .overlay(alignment: .leading) {
                RoundedRectangle(cornerRadius: 8)
                    .fill(color)
                    .frame(width: 3)
            }
            .overlay {
                RoundedRectangle(cornerRadius: 8)
                    .stroke(color, lineWidth: isActive ? 1 : 0)
            }
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Inspector

private struct TimelineInspector: View {
    let entry: DayTimelineLayout.Entry
    let language: AppLanguage
    let onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                Text(entry.title)
                    .font(.headline)
                    .lineLimit(3)
                Spacer()
                Button(action: onClose) {
                    Image(systemName: "xmark.circle.fill")
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
            }
            detailLine(L10n.text("Time", language: language), entry.timeLabel)
            detailLine(L10n.text("Source", language: language), sourceLabel)
            if let subtitle = entry.subtitle, !subtitle.isEmpty {
                detailLine(L10n.text("Details", language: language), subtitle)
            }
            Spacer()
        }
        .padding(16)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
        .overlay {
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private var sourceLabel: String {
        switch entry.source {
        case .schedule(let domain):
            return DayTimelineLayout.label(forDomain: domain, language: language)
        case .calendar:
            return L10n.text("Calendar", language: language)
        }
    }

    private func detailLine(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.callout)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - Hex color helper

@MainActor
private func hexColor(_ hex: String) -> Color {
    var cleaned = hex.trimmingCharacters(in: .whitespaces)
    if cleaned.hasPrefix("#") {
        cleaned.removeFirst()
    }
    guard cleaned.count == 6, let value = UInt32(cleaned, radix: 16) else {
        return .secondary
    }
    let r = Double((value >> 16) & 0xFF) / 255.0
    let g = Double((value >> 8) & 0xFF) / 255.0
    let b = Double(value & 0xFF) / 255.0
    return Color(red: r, green: g, blue: b)
}
