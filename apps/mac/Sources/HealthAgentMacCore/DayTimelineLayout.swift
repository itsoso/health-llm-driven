import Foundation

/// 单日时间轴的纯布局逻辑(无 SwiftUI / 无副作用,可单测)。
/// 镜像 mobile `timelineLayout.ts` + `calendar.tsx` 的合并/着色规则。
/// 坐标系:一天 0..1440 分钟,top = startMin * pxPerMin。

public enum DayTimelineLayout {
    public static let dayMinutes = 24 * 60

    /// 时点(无真实时长)的默认块时长。点类(药/补剂)→ 细 marker;其余(餐/复查)→ 30min。
    public static let defaultBlockMinutes = 30
    public static let markerMinutes = 10
    /// 处方缺 duration 时 movement 的兜底时长。
    public static let movementFallbackMinutes = 30

    /// "HH:MM" → 当天分钟数;非法返回 nil。
    public static func minutes(fromHHMM hhmm: String) -> Int? {
        let trimmed = hhmm.trimmingCharacters(in: .whitespaces)
        let parts = trimmed.split(separator: ":")
        guard parts.count == 2,
              let h = Int(parts[0]),
              let m = Int(parts[1]),
              (0...23).contains(h),
              (0...59).contains(m) else {
            return nil
        }
        return h * 60 + m
    }

    /// ISO datetime → 当天分钟数(本地时区的 H*60+M)。跨天由调用方裁剪。非法返回 nil。
    public static func minutes(fromISO iso: String?, calendar: Calendar = .current) -> Int? {
        guard let iso, let date = isoDate(iso) else { return nil }
        let comps = calendar.dateComponents([.hour, .minute], from: date)
        guard let h = comps.hour, let m = comps.minute else { return nil }
        return h * 60 + m
    }

    /// 解析后端 ISO 串。先试带秒+时区,再退化几种常见格式。
    public static func isoDate(_ iso: String) -> Date? {
        let withFractional = ISO8601DateFormatter()
        withFractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = withFractional.date(from: iso) { return date }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        if let date = plain.date(from: iso) { return date }
        // 无时区的 "yyyy-MM-dd'T'HH:mm:ss" / "yyyy-MM-dd HH:mm:ss"
        let fallback = DateFormatter()
        fallback.locale = Locale(identifier: "en_US_POSIX")
        fallback.timeZone = .current
        for format in ["yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd HH:mm"] {
            fallback.dateFormat = format
            if let date = fallback.date(from: iso) { return date }
        }
        return nil
    }

    public static func clampDayMinute(_ minute: Int) -> Int {
        if minute < 0 { return 0 }
        if minute > dayMinutes { return dayMinutes }
        return minute
    }

    public static func hhmm(fromMinutes minute: Int) -> String {
        let m = clampDayMinute(minute)
        let h = (m / 60) % 24
        return String(format: "%02d:%02d", h, m % 60)
    }

    /// 一个待定位的块(已归一成分钟)。
    public struct Block: Equatable, Sendable {
        public let key: String
        public let startMin: Int
        public let endMin: Int

        public init(key: String, startMin: Int, endMin: Int) {
            self.key = key
            self.startMin = startMin
            self.endMin = endMin
        }
    }

    /// 泳道布局结果:块占第 lane 列(共 lanes 列,同一重叠簇内)。
    public struct Placement: Equatable, Sendable {
        public let key: String
        public let lane: Int
        public let lanes: Int

        public init(key: String, lane: Int, lanes: Int) {
            self.key = key
            self.lane = lane
            self.lanes = lanes
        }
    }

    /// 贪心泳道分配:块按 start 升序,收集时间上互相交叠的簇,簇内为每块分配最小空闲列。
    /// 簇内所有块共享列数(列宽 = 1/lanes)。返回与输入 key 一一对应(无序,按 key 对回)。
    public static func assignLanes(_ blocks: [Block]) -> [Placement] {
        let sorted = blocks.sorted { a, b in
            if a.startMin != b.startMin { return a.startMin < b.startMin }
            return a.endMin < b.endMin
        }
        var result: [Placement] = []
        var i = 0
        while i < sorted.count {
            var cluster: [Block] = [sorted[i]]
            var clusterEnd = sorted[i].endMin
            var j = i + 1
            while j < sorted.count && sorted[j].startMin < clusterEnd {
                cluster.append(sorted[j])
                clusterEnd = max(clusterEnd, sorted[j].endMin)
                j += 1
            }
            var laneEnds: [Int] = []
            var placedLanes: [(key: String, lane: Int)] = []
            for block in cluster {
                var lane = laneEnds.firstIndex { $0 <= block.startMin } ?? -1
                if lane == -1 {
                    lane = laneEnds.count
                    laneEnds.append(block.endMin)
                } else {
                    laneEnds[lane] = block.endMin
                }
                placedLanes.append((block.key, lane))
            }
            let lanes = laneEnds.count
            for placed in placedLanes {
                result.append(Placement(key: placed.key, lane: placed.lane, lanes: lanes))
            }
            i = j
        }
        return result
    }

    // MARK: - Domain colors (mirror mobile DOMAIN_COLOR + meeting/source)

    /// 域 → hex 颜色(与 mobile calendar.tsx DOMAIN_COLOR 对齐;meeting 走日历源/会议色)。
    public static func colorHex(forDomain domain: String) -> String {
        switch domain {
        case "medication": return "#2E9E6B"
        case "supplement": return "#1F8A5B"
        case "diet": return "#C98A1E"
        case "movement": return "#2A6FDB"
        case "sleep": return "#7A5AF0"
        case "checkup": return "#D5503A"
        case "meeting", "event", "calendar": return "#0E7C86"
        default: return "#6B7280"
        }
    }

    public static func label(forDomain domain: String, language: AppLanguage) -> String {
        switch domain {
        case "medication": return L10n.text("Medication", language: language)
        case "supplement": return L10n.text("Supplement", language: language)
        case "diet": return L10n.text("Diet", language: language)
        case "movement": return L10n.text("Workout", language: language)
        case "sleep": return L10n.text("Sleep", language: language)
        case "checkup": return L10n.text("Checkup", language: language)
        case "meeting", "event", "calendar": return L10n.text("Meeting", language: language)
        default: return domain
        }
    }

    private static let pointDomains: Set<String> = ["medication", "supplement"]

    // MARK: - Unified entry model

    public enum EntrySource: Equatable, Sendable {
        case schedule(domain: String)
        case calendar
    }

    /// 时间轴渲染用条目:布局字段 + 展示字段(已合并 schedule + calendar)。
    public struct Entry: Equatable, Identifiable, Sendable {
        public let key: String
        public let startMin: Int
        public let endMin: Int
        public let title: String
        public let timeLabel: String
        public let subtitle: String?
        public let colorHex: String
        public let isPoint: Bool
        public let source: EntrySource

        public var id: String { key }

        public init(
            key: String,
            startMin: Int,
            endMin: Int,
            title: String,
            timeLabel: String,
            subtitle: String?,
            colorHex: String,
            isPoint: Bool,
            source: EntrySource
        ) {
            self.key = key
            self.startMin = startMin
            self.endMin = endMin
            self.title = title
            self.timeLabel = timeLabel
            self.subtitle = subtitle
            self.colorHex = colorHex
            self.isPoint = isPoint
            self.source = source
        }

        public var block: Block { Block(key: key, startMin: startMin, endMin: endMin) }
    }

    /// 全天事件(顶部 strip,不进网格)。
    public struct AllDayEntry: Equatable, Identifiable, Sendable {
        public let key: String
        public let title: String
        public let colorHex: String

        public var id: String { key }

        public init(key: String, title: String, colorHex: String) {
            self.key = key
            self.title = title
            self.colorHex = colorHex
        }
    }

    public struct Merged: Equatable, Sendable {
        public let entries: [Entry]
        public let allDay: [AllDayEntry]

        public init(entries: [Entry], allDay: [AllDayEntry]) {
            self.entries = entries
            self.allDay = allDay
        }
    }

    /// 把健康日程 + 日历事件合并成统一时间轴条目。
    /// - schedule 仅当看今天(`includeSchedule`)才并入(timing-solver 是「今日」端点)。
    /// - calendar 全天 → allDay strip;有效 start 才进网格,end 缺失或不晚于 start 用默认时长。
    public static func merge(
        schedule: TodaySchedule?,
        events: [CalendarEvent],
        includeSchedule: Bool,
        language: AppLanguage,
        calendar: Calendar = .current
    ) -> Merged {
        var entries: [Entry] = []
        var allDay: [AllDayEntry] = []

        for ev in events {
            let key = "ev:\(ev.id)"
            let title = nonEmpty(ev.title) ?? L10n.text("Untitled", language: language)
            let color = colorHex(forDomain: "meeting")
            if ev.allDay {
                allDay.append(AllDayEntry(key: key, title: title, colorHex: color))
                continue
            }
            guard let startMin = minutes(fromISO: ev.start, calendar: calendar) else { continue }
            let rawEnd = minutes(fromISO: ev.end, calendar: calendar)
            let endMin: Int
            if let rawEnd, rawEnd > startMin {
                endMin = rawEnd
            } else {
                endMin = startMin + defaultBlockMinutes
            }
            let startLabel = hhmm(fromMinutes: startMin)
            let endLabel = hhmm(fromMinutes: min(endMin, dayMinutes))
            entries.append(Entry(
                key: key,
                startMin: clampDayMinute(startMin),
                endMin: clampDayMinute(endMin),
                title: title,
                timeLabel: "\(startLabel)–\(endLabel)",
                subtitle: nonEmpty(ev.location),
                colorHex: color,
                isPoint: false,
                source: .calendar
            ))
        }

        if includeSchedule {
            for item in schedule?.scheduled ?? [] {
                guard let startMin = minutes(fromHHMM: item.time) else { continue }
                let key = "hs:\(item.id)"
                let duration = item.prescription?.durationMin
                let hasMovementDuration = item.domain == "movement"
                let isPoint = pointDomains.contains(item.domain) && duration == nil
                let span: Int
                if let duration {
                    span = duration
                } else if hasMovementDuration {
                    span = movementFallbackMinutes
                } else if isPoint {
                    span = markerMinutes
                } else {
                    span = defaultBlockMinutes
                }
                let endMin = startMin + span
                let timeLabel: String
                if let duration {
                    timeLabel = "\(item.time)–\(hhmm(fromMinutes: startMin + duration))"
                } else {
                    timeLabel = item.time
                }
                let subtitle = item.prescription?.displaySummary ?? label(forDomain: item.domain, language: language)
                entries.append(Entry(
                    key: key,
                    startMin: clampDayMinute(startMin),
                    endMin: clampDayMinute(endMin),
                    title: nonEmpty(item.title) ?? label(forDomain: item.domain, language: language),
                    timeLabel: timeLabel,
                    subtitle: subtitle,
                    colorHex: colorHex(forDomain: item.domain),
                    isPoint: isPoint,
                    source: .schedule(domain: item.domain)
                ))
            }
        }

        return Merged(entries: entries, allDay: allDay)
    }

    private static func nonEmpty(_ value: String?) -> String? {
        guard let value, !value.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
        return value
    }
}
