import HealthAgentMacCore
import AppKit
import SwiftUI
@preconcurrency import UserNotifications

@main
struct HealthAgentMacApp: App {
    @NSApplicationDelegateAdaptor(HealthAgentAppDelegate.self) private var appDelegate
    @State private var appServices = AppServices()
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @AppStorage(AppFontScale.defaultsKey) private var appFontScaleLevel = AppFontScale.defaultLevel

    var body: some Scene {
        WindowGroup(id: "main") {
            AppRootView(services: appServices)
                .appFontScale(AppFontScale(level: appFontScaleLevel))
                .fontScaleKeyboardShortcuts(level: $appFontScaleLevel)
        }
        MenuBarExtra {
            MenuBarRootView(
                viewModel: appServices.todayViewModel,
                navigation: appServices.navigation,
                recordClient: appServices.recordClient
            )
            .appFontScale(AppFontScale(level: appFontScaleLevel))
            .fontScaleKeyboardShortcuts(level: $appFontScaleLevel)
        } label: {
            // Menu-bar status glyph. Use a native SF Symbol so macOS sizes it to
            // standard menu-bar metrics (matches wifi/battery/input-source), at a
            // clean regular weight. A plain pulse/waveform reads best at this size —
            // the old baked 18pt template PNG (pulse + 3 sparkles) rendered heavier
            // and busier than its neighbors ("还是偏大一些"). Template/monochrome:
            // macOS auto-tints it white on the dark bar, so no color applies here.
            Label {
                Text(appText("Health Agent", appLanguageRaw))
            } icon: {
                Image(systemName: "waveform.path.ecg")
                    .font(.system(size: 15, weight: .regular))
            }
        }
        // MenuBarRootView 是按弹窗样式设计的(固定宽 250、状态芯片 HStack、ProgressView
        // 转子、多行 caption)。不设 style 会默认 .menu,把这些自定义布局降级成菜单项
        // (frame 被忽略、芯片挤压、转子不渲染)。显式用 .window 让它按设计渲染。
        .menuBarExtraStyle(.window)
        .commands {
            CommandMenu(appText("Health Agent", appLanguageRaw)) {
                Button(appText("Today", appLanguageRaw)) { appServices.navigation.selection = .today }
                    .keyboardShortcut("1", modifiers: [.command])
                Button(appText("Ask Agent", appLanguageRaw)) { appServices.navigation.selection = .agent }
                    .keyboardShortcut("l", modifiers: [.command, .shift])
                Button(appText("Record", appLanguageRaw)) { appServices.navigation.selection = .record }
                    .keyboardShortcut("r", modifiers: [.command, .shift])
                Button(appText("Import", appLanguageRaw)) { appServices.navigation.selection = .genetics }
                    .keyboardShortcut("i", modifiers: [.command, .shift])
                Button(appText("Jobs", appLanguageRaw)) { appServices.navigation.selection = .jobs }
                    .keyboardShortcut("j", modifiers: [.command, .shift])
                Button(appText("Trace", appLanguageRaw)) { appServices.navigation.selection = .trace }
                    .keyboardShortcut("t", modifiers: [.command, .shift])
                Button(appText("Settings", appLanguageRaw)) { appServices.navigation.selection = .settings }
                    .keyboardShortcut(",", modifiers: [.command])
                Divider()
                Button(appText("New Chat", appLanguageRaw)) {
                    appServices.navigation.selection = .agent
                    appServices.navigation.newConversationTick += 1
                }
                .keyboardShortcut("n", modifiers: [.command])
                Button(appText("Refresh", appLanguageRaw)) {
                    appServices.navigation.refreshTick += 1
                }
                .keyboardShortcut("r", modifiers: [.command])
                Button(appText("Command Palette", appLanguageRaw)) {
                    appServices.navigation.isCommandPalettePresented = true
                }
                .keyboardShortcut("k", modifiers: [.command])
                Divider()
                Button(appText("Increase Font Size", appLanguageRaw)) {
                    appFontScaleLevel = AppFontScale(level: appFontScaleLevel).increased().level
                }
                .keyboardShortcut("=", modifiers: [.command])
                Button(appText("Increase Font Size", appLanguageRaw)) {
                    appFontScaleLevel = AppFontScale(level: appFontScaleLevel).increased().level
                }
                .keyboardShortcut("=", modifiers: [.command, .shift])
                Button(appText("Decrease Font Size", appLanguageRaw)) {
                    appFontScaleLevel = AppFontScale(level: appFontScaleLevel).decreased().level
                }
                .keyboardShortcut("-", modifiers: [.command])
                Button(appText("Reset Font Size", appLanguageRaw)) {
                    appFontScaleLevel = AppFontScale(level: appFontScaleLevel).reset().level
                }
                .keyboardShortcut("0", modifiers: [.command])
            }
        }
    }
}

struct TodayView: View {
    @Bindable var viewModel: TodayViewModel
    var briefingClient: BriefingClient?
    var nocturnalClient: NocturnalTimeseriesClient?
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    var onAddContext: ((AgentContextItem) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var dashboardRange: DashboardRange = .sevenDays
    @State private var inputInboxFilter: InputInboxFilter = .all
    @State private var briefing: DailyBriefing?
    @State private var briefingLoaded = false
    @State private var spo2Week: [NocturnalWeekNight] = []
    @State private var spo2WeekLoaded = false

    var body: some View {
        GeometryReader { proxy in
            let layout = DesktopDashboardLayoutPolicy.metrics(forAvailableWidth: Double(proxy.size.width))

            ZStack {
                WarmPalette.paper
                    .ignoresSafeArea()

                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        if let presentation {
                            HStack(alignment: .top, spacing: CGFloat(layout.columnSpacing)) {
                                VStack(alignment: .leading, spacing: 18) {
                                    let hasBriefing = (briefing?.sections.isEmpty == false)
                                    let hasSpO2 = SpO2WeekCard.shouldShow(nights: spo2Week, loaded: spo2WeekLoaded)
                                    if hasBriefing || hasSpO2 {
                                        // 健康分组:今日简报 + 夜间 SpO2 归到一个带「健康」标题的板块,
                                        // 与下方任务/看板内容在视觉上分开。
                                        VStack(alignment: .leading, spacing: 12) {
                                            Label(appText("Health", appLanguageRaw), systemImage: "heart.text.square.fill")
                                                .font(.title3.bold())
                                                .foregroundStyle(.pink)
                                            if hasBriefing, let briefing {
                                                BriefingCardView(
                                                    briefing: briefing,
                                                    appLanguageRaw: appLanguageRaw,
                                                    onAskAgent: onAskAgent,
                                                    onAddContext: onAddContext,
                                                    onScheduleReminder: scheduleBriefingReminder
                                                )
                                            }
                                            if hasSpO2 {
                                                SpO2WeekCard(
                                                    nights: spo2Week,
                                                    appLanguageRaw: appLanguageRaw,
                                                    onAskAgent: onAskAgent
                                                )
                                            }
                                        }
                                    }
                                    PriorityActionHeroView(
                                        actions: presentation.actionRows,
                                        appLanguageRaw: appLanguageRaw,
                                        onStart: { askAgent($0, section: "priority_action_start") },
                                        onWhy: { row in
                                            let item = DesktopDashboardContextFactory.contextItem(for: row, section: "priority_action_why")
                                            onAskAgent?("为什么这件事现在最重要？给我一段简短解释和判断依据。", item)
                                        }
                                    )
                                    dashboardHero(presentation)
                                    inputInboxPanel(
                                        events: presentation.inputInboxEvents,
                                        summary: presentation.inputInboxSummary
                                    )
                                    actionPanel(presentation.actionRows)
                                    recentRecordsPanel(presentation.recentRecordRows)
                                }
                                .frame(minWidth: 620, maxWidth: .infinity, alignment: .topLeading)

                                VStack(alignment: .leading, spacing: 18) {
                                    RefreshPanelView(
                                        isLoading: viewModel.isLoading,
                                        appLanguageRaw: appLanguageRaw,
                                        onRefresh: { Task { await viewModel.refresh() } }
                                    )
                                    WearablePanelView(
                                        metrics: presentation.wearableMetrics,
                                        appLanguageRaw: appLanguageRaw,
                                        localizedTitle: localizedMetricTitle,
                                        localizedDetail: localizedMetricDetail,
                                        onTap: { askAgent($0, section: "wearable_today") }
                                    )
                                    memoryPanel(presentation.memoryRows)
                                    jobsPanel(presentation.activeJobRows)
                                }
                                .frame(width: CGFloat(layout.rightRailWidth), alignment: .topLeading)
                            }
                        } else {
                            loadingPanel
                        }
                    }
                    .frame(maxWidth: CGFloat(layout.contentMaxWidth), alignment: .leading)
                    .padding(.horizontal, CGFloat(layout.horizontalPadding))
                    .padding(.vertical, 22)
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                }
            }
        }
        .task {
            if viewModel.bootstrap == nil {
                await viewModel.refresh()
            }
            await loadBriefingIfNeeded()
            await loadSpO2WeekIfNeeded()
        }
    }

    private func loadBriefingIfNeeded() async {
        guard !briefingLoaded, let client = briefingClient else { return }
        briefingLoaded = true
        do {
            briefing = try await client.fetchMorningBriefing()
        } catch {
            AppLogger.briefing.error("morning briefing fetch failed: \(error.localizedDescription, privacy: .public)")
            briefing = nil
        }
    }

    private func loadSpO2WeekIfNeeded() async {
        guard !spo2WeekLoaded, let client = nocturnalClient else { return }
        spo2WeekLoaded = true
        spo2Week = await client.fetchSpO2WeekSummary()
    }

    private var presentation: DesktopDashboardPresentation? {
        viewModel.bootstrap.map(DesktopDashboardPresentation.init)
    }

    private var loadingPanel: some View {
        SectionPanel(title: appText("Health Dashboard", appLanguageRaw), systemImage: "heart.text.square.fill") {
            ProgressView(appText("Loading desktop context...", appLanguageRaw))
                .controlSize(.large)
                .frame(maxWidth: .infinity, minHeight: 220)
        }
    }

    private func scheduleBriefingReminder(_ section: BriefingSection) {
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            let content = UNMutableNotificationContent()
            content.title = section.title
            content.body = section.items.first ?? section.title
            content.sound = .default
            // Fire at next 09:00 — quiet hours rule still applies via system if user enabled DND.
            let now = Date()
            let calendar = Calendar.current
            var components = calendar.dateComponents([.year, .month, .day], from: now)
            components.hour = 9
            components.minute = 0
            if let target = calendar.date(from: components), target <= now {
                components = calendar.dateComponents([.year, .month, .day], from: calendar.date(byAdding: .day, value: 1, to: now) ?? now)
                components.hour = 9
                components.minute = 0
            }
            let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: false)
            let id = "briefing-\(section.title)-\(Int(now.timeIntervalSince1970))"
            let request = UNNotificationRequest(identifier: id, content: content, trigger: trigger)
            center.add(request, withCompletionHandler: nil)
        }
    }

    private func dashboardHero(_ presentation: DesktopDashboardPresentation) -> some View {
        let rangeMetrics = dashboardRange == .sevenDays ? presentation.sevenDayMetrics : presentation.thirtyDayMetrics
        let rangeTrends = dashboardRange == .sevenDays ? presentation.sevenDayTrends : presentation.thirtyDayTrends

        return VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 6) {
                Text(appText("Health Dashboard", appLanguageRaw))
                    .font(.title2.bold())
                HStack(spacing: 8) {
                    Text(presentation.heroTitle)
                        .font(.headline.weight(.semibold))
                    Text(localizedSubtitle(presentation.heroSubtitle))
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                .lineLimit(1)
                if !presentation.focusChips.isEmpty {
                    HStack(spacing: 8) {
                        ForEach(presentation.focusChips, id: \.self) { chip in
                            Text(chip)
                                .font(.caption.weight(.semibold))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .background(WarmPalette.claySoft, in: Capsule())
                                .foregroundStyle(WarmPalette.clayInk)
                        }
                    }
                    .padding(.top, 6)
                }
            }

            // 步数/睡眠/血氧/体重 hero 指标格删除:与右栏「今日穿戴」WearablePanel
            // 完全重复(同一批指标第三次出现)。本看板只保留下方独有的营养摄入趋势。
            Divider()

            HStack(spacing: 12) {
                Label(appText("Nutrition & Intake", appLanguageRaw), systemImage: "chart.xyaxis.line")
                    .font(.headline.weight(.semibold))
                Spacer()
                Picker("", selection: $dashboardRange) {
                    ForEach(DashboardRange.allCases) { range in
                        Text(appText(range.titleKey, appLanguageRaw)).tag(range)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 150)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 12)], spacing: 12) {
                ForEach(rangeMetrics) { metric in
                    Button {
                        askAgent(metric, section: dashboardRange == .sevenDays ? "today_intake_7d" : "today_intake_30d")
                    } label: {
                        SummaryMetricStrip(
                            metric: metric,
                            title: localizedMetricTitle(metric.titleKey),
                            detail: localizedMetricDetail(metric.detail),
                            showsDisclosure: true
                        )
                    }
                    .buttonStyle(.plain)
                    .help(appText("Ask Agent with Context", appLanguageRaw))
                }
            }

            TrendSparklineGrid(
                trends: rangeTrends,
                localizedTitle: localizedMetricTitle,
                localizedDetail: localizedMetricDetail,
                onSelect: { trend in
                    askAgent(trend, section: "today_trends", rangeDays: dashboardRange == .sevenDays ? 7 : 30)
                }
            )

            if let error = viewModel.errorMessage {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                    Text(error)
                }
                .font(.caption)
                .foregroundStyle(.red)
            }
        }
        .padding(AppCardStyle.padding)
        .background {
            RoundedRectangle(cornerRadius: AppCardStyle.cornerRadius, style: .continuous)
                .fill(WarmPalette.card)
                .overlay(alignment: .topTrailing) {
                    RoundedRectangle(cornerRadius: AppCardStyle.cornerRadius, style: .continuous)
                        .fill(
                            LinearGradient(
                                colors: [WarmPalette.claySoft.opacity(0.9), WarmPalette.amberSoft.opacity(0.55), Color.clear],
                                startPoint: .topTrailing,
                                endPoint: .bottomLeading
                            )
                        )
                }
        }
        .overlay(panelStroke())
        .shadow(color: Color.black.opacity(0.06), radius: 18, y: 10)
    }

    private func metricGrid(_ metrics: [DesktopDashboardMetric]) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 240), spacing: 14)], spacing: 14) {
            ForEach(metrics) { metric in
                DashboardMetricTile(
                    metric: metric,
                    title: localizedMetricTitle(metric.titleKey),
                    detail: localizedMetricDetail(metric.detail)
                )
            }
        }
    }

    private func actionPanel(_ actions: [DesktopDashboardRow]) -> some View {
        card {
            sectionHeader(title: appText("Priority Actions", appLanguageRaw), systemImage: "checklist")
            if actions.isEmpty {
                EmptyStateText(text: appText("No actions loaded yet.", appLanguageRaw))
            } else {
                VStack(spacing: 0) {
                    ForEach(actions) { row in
                        Button {
                            askAgent(row, section: "priority_actions")
                        } label: {
                            DashboardRowView(row: row, showsDisclosure: true)
                        }
                        .buttonStyle(.plain)
                        .help(appText("Ask Agent with Context", appLanguageRaw))
                        if row.id != actions.last?.id { Divider().padding(.leading, 34) }
                    }
                }
            }
        }
    }

    private func inputInboxPanel(
        events: [DesktopInputInboxEvent],
        summary: DesktopInputInboxSummary
    ) -> some View {
        let filteredEvents = inputInboxFilter.filter(events)
        return card {
            HStack(alignment: .center, spacing: 12) {
                Label(appText("Input Inbox", appLanguageRaw), systemImage: "tray.full")
                    .font(.headline.weight(.semibold))
                Spacer()
                Picker("", selection: $inputInboxFilter) {
                    ForEach(InputInboxFilter.allCases) { filter in
                        Text(appText(filter.titleKey, appLanguageRaw)).tag(filter)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 260)
            }

            HStack(spacing: 8) {
                inputInboxCountChip(title: "All", value: summary.totalCount, color: .secondary)
                inputInboxCountChip(title: "Needs Review", value: summary.needsReviewCount, color: .orange)
                inputInboxCountChip(title: "Auto Saved", value: summary.autoSavedCount, color: .teal)
                inputInboxCountChip(title: "Confirmed", value: summary.confirmedCount, color: .blue)
                Spacer()
                Text(appText("Silent capture, review when needed.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if filteredEvents.isEmpty {
                EmptyStateText(text: appText("No input events loaded.", appLanguageRaw))
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 10)], spacing: 10) {
                    ForEach(filteredEvents) { event in
                        InputInboxEventCard(
                            event: event,
                            onAddContext: onAddContext,
                            onAskAgent: onAskAgent
                        )
                    }
                }
            }
        }
    }

    private func inputInboxCountChip(title: String, value: Int, color: Color) -> some View {
        HStack(spacing: 5) {
            Text(appText(title, appLanguageRaw))
            Text("\(value)")
                .font(.caption.weight(.bold).monospacedDigit())
        }
        .font(.caption)
        .foregroundStyle(color)
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(color.opacity(0.10), in: Capsule())
    }

    private func recentRecordsPanel(_ records: [DesktopDashboardRow]) -> some View {
        card {
            sectionHeader(title: appText("Recent Health Records", appLanguageRaw), systemImage: "waveform.path.ecg")
            if records.isEmpty {
                EmptyStateText(text: appText("No recent health records loaded.", appLanguageRaw))
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 10)], spacing: 10) {
                    ForEach(records) { row in
                        Button {
                            askAgent(row, section: "recent_health_records")
                        } label: {
                            CompactRecordCard(row: row, showsDisclosure: true)
                        }
                        .buttonStyle(.plain)
                        .help(appText("Ask Agent with Context", appLanguageRaw))
                    }
                }
            }
        }
    }

    private func memoryPanel(_ memory: [DesktopDashboardRow]) -> some View {
        card {
            sectionHeader(title: appText("Recent Memory", appLanguageRaw), systemImage: "brain.head.profile")
            if memory.isEmpty {
                EmptyStateText(text: appText("No recent memory loaded.", appLanguageRaw))
            } else {
                VStack(spacing: 0) {
                    ForEach(memory) { row in
                        DashboardRowView(row: row)
                        if row.id != memory.last?.id { Divider().padding(.leading, 34) }
                    }
                }
            }
        }
    }

    private func jobsPanel(_ jobs: [DesktopDashboardRow]) -> some View {
        card {
            sectionHeader(title: appText("Active Jobs", appLanguageRaw), systemImage: "clock.arrow.circlepath")
            if jobs.isEmpty {
                EmptyStateText(text: appText("No active desktop jobs.", appLanguageRaw))
            } else {
                ForEach(jobs) { row in
                    VStack(alignment: .leading, spacing: 8) {
                        DashboardRowView(row: row)
                        if let progress = row.progress {
                            ProgressView(value: progress)
                        }
                    }
                }
            }
        }
    }

    private func askAgent(_ metric: DesktopDashboardMetric, section: String) {
        let item = DesktopDashboardContextFactory.contextItem(for: metric, section: section)
        let prompt = DesktopDashboardContextFactory.prompt(for: metric, section: section)
        onAskAgent?(prompt, item)
    }

    private func askAgent(_ trend: DesktopDashboardTrend, section: String, rangeDays: Int) {
        let item = DesktopDashboardContextFactory.contextItem(for: trend, section: section, rangeDays: rangeDays)
        let prompt = DesktopDashboardContextFactory.prompt(for: trend, section: section, rangeDays: rangeDays)
        onAskAgent?(prompt, item)
    }

    private func askAgent(_ row: DesktopDashboardRow, section: String) {
        let item = DesktopDashboardContextFactory.contextItem(for: row, section: section)
        let prompt = DesktopDashboardContextFactory.prompt(for: row, section: section)
        onAskAgent?(prompt, item)
    }

    private func localizedMetricTitle(_ key: String) -> String {
        appText(key, appLanguageRaw)
    }

    private func localizedMetricDetail(_ detail: String) -> String {
        detail
            .replacingOccurrences(of: "records", with: appText("records", appLanguageRaw))
            .replacingOccurrences(of: "No record", with: appText("No record", appLanguageRaw))
            .replacingOccurrences(of: "No wearable data", with: appText("No wearable data", appLanguageRaw))
            .replacingOccurrences(of: "Readiness", with: appText("Readiness", appLanguageRaw))
            .replacingOccurrences(of: "wearable", with: appText("wearable", appLanguageRaw))
            .replacingOccurrences(of: "Avg", with: appText("Avg", appLanguageRaw))
            .replacingOccurrences(of: "/day", with: appText("/day", appLanguageRaw))
            .replacingOccurrences(of: "Adherence", with: appText("Adherence", appLanguageRaw))
            .replacingOccurrences(of: "active", with: appText("active", appLanguageRaw))
    }

    private func localizedSubtitle(_ subtitle: String) -> String {
        subtitle
            .replacingOccurrences(of: "cards", with: appText("cards", appLanguageRaw))
            .replacingOccurrences(of: "memories", with: appText("memories", appLanguageRaw))
            .replacingOccurrences(of: "recent records", with: appText("recent records", appLanguageRaw))
    }
}

private enum DashboardRange: String, CaseIterable, Identifiable {
    case sevenDays
    case thirtyDays

    var id: String { rawValue }

    var titleKey: String {
        switch self {
        case .sevenDays: "7 days"
        case .thirtyDays: "30 days"
        }
    }
}

private enum InputInboxFilter: String, CaseIterable, Identifiable {
    case all
    case needsReview
    case autoSaved
    case confirmed

    var id: String { rawValue }

    var titleKey: String {
        switch self {
        case .all: "All"
        case .needsReview: "Needs Review"
        case .autoSaved: "Auto Saved"
        case .confirmed: "Confirmed"
        }
    }

    func filter(_ events: [DesktopInputInboxEvent]) -> [DesktopInputInboxEvent] {
        switch self {
        case .all:
            events
        case .needsReview:
            events.filter { $0.state == .needsReview }
        case .autoSaved:
            events.filter { $0.state == .autoSaved }
        case .confirmed:
            events.filter { $0.state == .confirmed }
        }
    }
}

private struct HeroMetricTile: View {
    let metric: DesktopDashboardMetric
    let title: String
    let detail: String
    var showsDisclosure = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: metric.systemImage)
                    .foregroundStyle(toneColor(metric.tone))
                Spacer()
                if showsDisclosure {
                    Image(systemName: "chevron.right.circle.fill")
                        .font(.callout)
                        .foregroundStyle(toneColor(metric.tone))
                }
            }
            Text(metric.value)
                .font(.system(size: 28, weight: .bold, design: .rounded))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.primary)
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 128, alignment: .topLeading)
        .background(toneColor(metric.tone).opacity(0.09), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

private struct SummaryMetricStrip: View {
    let metric: DesktopDashboardMetric
    let title: String
    let detail: String
    var showsDisclosure = false

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: metric.systemImage)
                .font(.callout.weight(.semibold))
                .foregroundStyle(toneColor(metric.tone))
                .frame(width: 30, height: 30)
                .background(toneColor(metric.tone).opacity(0.12), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(metric.value)
                    .font(.headline.weight(.bold).monospacedDigit())
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
            }
            Spacer(minLength: 6)
            Text(detail)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            if showsDisclosure {
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

private struct TrendSparklineGrid: View {
    let trends: [DesktopDashboardTrend]
    let localizedTitle: (String) -> String
    let localizedDetail: (String) -> String
    var onSelect: ((DesktopDashboardTrend) -> Void)?

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 210), spacing: 12)], spacing: 12) {
            ForEach(trends) { trend in
                if let onSelect {
                    Button {
                        onSelect(trend)
                    } label: {
                        TrendSparklineCard(
                            trend: trend,
                            title: localizedTitle(trend.titleKey),
                            detail: localizedDetail(trend.averageLabel),
                            showsDisclosure: true
                        )
                    }
                    .buttonStyle(.plain)
                } else {
                    TrendSparklineCard(
                        trend: trend,
                        title: localizedTitle(trend.titleKey),
                        detail: localizedDetail(trend.averageLabel)
                    )
                }
            }
        }
    }
}

private struct TrendSparklineCard: View {
    let trend: DesktopDashboardTrend
    let title: String
    let detail: String
    var showsDisclosure = false

    private var maxValue: Double {
        max(trend.points.map(\.value).max() ?? 0, 1)
    }

    private var latestValue: Double {
        trend.points.last?.value ?? 0
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                if showsDisclosure {
                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                }
            }

            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(formatted(latestValue))
                    .font(.title3.weight(.bold).monospacedDigit())
                Text(trend.unit)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(alignment: .bottom, spacing: 4) {
                ForEach(trend.points) { point in
                    Capsule()
                        .fill(toneColor(trend.tone).opacity(point.value > 0 ? 0.72 : 0.16))
                        .frame(height: max(6, CGFloat(point.value / maxValue) * 42))
                        .frame(maxWidth: .infinity)
                        .help("\(point.date): \(formatted(point.value)) \(trend.unit)")
                }
            }
            .frame(height: 46, alignment: .bottom)
        }
        .padding(12)
        .background(toneColor(trend.tone).opacity(0.07), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
    }

    private func formatted(_ value: Double) -> String {
        value.formatted(.number.grouping(.automatic).precision(.fractionLength(0...1)))
    }
}

private struct DashboardMetricTile: View {
    let metric: DesktopDashboardMetric
    let title: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center) {
                Image(systemName: metric.systemImage)
                    .font(.headline)
                    .foregroundStyle(toneColor(metric.tone))
                    .frame(width: 30, height: 30)
                    .background(toneColor(metric.tone).opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                Spacer()
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Text(title)
                .font(.callout.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(metric.value)
                .font(.system(size: 30, weight: .bold, design: .rounded))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .padding(18)
        .frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading)
        .background(.background, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(toneColor(metric.tone).opacity(0.18), lineWidth: 1)
        )
        .shadow(color: Color.black.opacity(0.04), radius: 12, y: 6)
    }
}

private struct MiniMetricTile: View {
    let metric: DesktopDashboardMetric
    let title: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: metric.systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Text(metric.value)
                .font(.title3.weight(.bold))
                .monospacedDigit()
                .lineLimit(1)
            Text(detail)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 96, alignment: .topLeading)
        .background(toneColor(metric.tone).opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct DashboardRowView: View {
    let row: DesktopDashboardRow
    var showsDisclosure = false

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: row.systemImage)
                .font(.callout)
                .foregroundStyle(toneColor(row.tone))
                .frame(width: 24, height: 24)
            VStack(alignment: .leading, spacing: 3) {
                Text(MarkdownRenderSupport.compactPreview(from: row.title, maxLines: 1))
                    .font(.callout.weight(.semibold))
                    .lineLimit(2)
                if let subtitle = row.subtitle, !subtitle.isEmpty {
                    Text(MarkdownRenderSupport.compactPreview(from: subtitle, maxLines: 1))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 12)
            if let value = row.value {
                Text(value)
                    .font(.callout.weight(.semibold).monospacedDigit())
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            if showsDisclosure {
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
                    .padding(.top, 3)
            }
        }
        .padding(.vertical, 9)
    }
}

private struct InputInboxEventCard: View {
    let event: DesktopInputInboxEvent
    let onAddContext: ((AgentContextItem) -> Void)?
    let onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: event.systemImage)
                    .font(.headline)
                    .foregroundStyle(.white)
                    .frame(width: 34, height: 34)
                    .background(toneColor(event.tone).opacity(0.86), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(event.title)
                            .font(.callout.weight(.semibold))
                            .lineLimit(1)
                        Text(appText(sourceText, appLanguageRaw))
                            .font(.caption2.weight(.bold))
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(toneColor(event.tone).opacity(0.12), in: Capsule())
                            .foregroundStyle(toneColor(event.tone))
                    }
                    Text(event.subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    if !event.detail.isEmpty {
                        Text(event.detail)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                    if !event.reviewHint.isEmpty {
                        Label(appText(event.reviewHint, appLanguageRaw), systemImage: "arrow.triangle.branch")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(stateColor)
                            .lineLimit(2)
                    }
                }
                Spacer(minLength: 0)
                stateBadge
            }

            HStack(spacing: 8) {
                if let onAddContext {
                    Button {
                        onAddContext(event.contextItem)
                    } label: {
                        Label(appText("Add Context", appLanguageRaw), systemImage: "tray.and.arrow.down")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
                if let onAskAgent {
                    Button {
                        onAskAgent(event.prompt, event.contextItem)
                    } label: {
                        Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 128, alignment: .topLeading)
        .background(toneColor(event.tone).opacity(0.07), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(toneColor(event.tone).opacity(0.12), lineWidth: 1)
        }
    }

    private var stateBadge: some View {
        Text(appText(stateText, appLanguageRaw))
            .font(.caption2.weight(.bold))
            .foregroundStyle(stateColor)
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(stateColor.opacity(0.12), in: Capsule())
    }

    private var sourceText: String {
        switch event.source {
        case .device: "Device"
        case .voice: "Voice"
        case .image: "Image"
        case .manual: "Manual"
        case .imported: "Import"
        }
    }

    private var stateText: String {
        switch event.state {
        case .autoSaved: "Auto Saved"
        case .needsReview: "Needs Review"
        case .confirmed: "Confirmed"
        }
    }

    private var stateColor: Color {
        switch event.state {
        case .autoSaved: .teal
        case .needsReview: .orange
        case .confirmed: .green
        }
    }
}

private struct CompactRecordCard: View {
    let row: DesktopDashboardRow
    var showsDisclosure = false

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            Image(systemName: row.systemImage)
                .foregroundStyle(toneColor(row.tone))
                .frame(width: 28, height: 28)
                .background(toneColor(row.tone).opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                Text(row.title)
                    .font(.callout.weight(.semibold))
                    .lineLimit(1)
                Text(row.subtitle ?? "")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            Text(row.value ?? "—")
                .font(.callout.weight(.semibold).monospacedDigit())
                .lineLimit(1)
            if showsDisclosure {
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct EmptyStateText: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.callout)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct WorkspaceOverviewView: View {
    @Bindable var viewModel: TodayViewModel
    let jobClient: DesktopJobClient
    let kind: DesktopWorkspaceKind
    var nocturnalClient: NocturnalTimeseriesClient?
    var garminTrendClient: GarminTrendClient?
    var labClient: LabClient?
    var interventionsClient: InterventionsClient?
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    var onAddContext: ((AgentContextItem) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var dataRange = "7d"
    @State private var selectedHealthTrend: DesktopHealthTrendContext?
    @State private var selectedVital: VitalMetricKind?
    @State private var selectedGenomicDetail: GenomicDetailRoute?
    @State private var selectedKnowledgeDocument: KnowledgeDocumentSummary?
    @State private var knowledgeSearchText = ""
    @State private var knowledgeDocumentFilter: KnowledgeDocumentFilter = .all
    @State private var guidanceActionStatus: String?
    @State private var runningGuidanceAction: DesktopWorkspaceGuidanceAction?
    @State private var nocturnalSpO2: NocturnalSpO2Summary?
    @State private var nocturnalNight: NocturnalNightSnapshot?
    @State private var nocturnalLoading = false
    @State private var nocturnalError: String?
    @State private var nocturnalLoadedDate: String?
    @State private var nocturnalWeek: [NocturnalWeekNight] = []
    @State private var nocturnalWeekLoading = false
    @State private var nocturnalWeekLoaded = false
    @State private var labSeries: [LabIndicatorSeries] = []
    @State private var labLoading = false
    @State private var labError: String?
    @State private var labLoaded = false
    @State private var selectedLabCode: String?
    @State private var interventionEvents: [InterventionEvent] = []
    @State private var interventionsLoaded = false
    @State private var garminRecords: [GarminDailyRecord] = []
    @State private var garminLoaded = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(appText(summary?.title ?? kind.title, appLanguageRaw))
                            .font(.largeTitle.bold())
                        Text(appText(summary?.subtitle ?? kind.subtitle, appLanguageRaw))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(appText("Refresh", appLanguageRaw)) {
                        Task { await viewModel.refresh() }
                    }
                }

                if viewModel.isLoading {
                    ProgressView(appText("Loading workspace...", appLanguageRaw))
                }
                if let error = viewModel.errorMessage {
                    Text(error)
                        .foregroundStyle(.red)
                }

                if let summary {
                    workspaceSummary(summary)
                } else {
                    ContentUnavailableView(appText("No workspace data loaded", appLanguageRaw), systemImage: "square.grid.2x2")
                }
            }
            .padding(28)
        }
        .background(
            LinearGradient(
                colors: [
                    Color(nsColor: .windowBackgroundColor),
                    (kind == .data ? Color.cyan : Color.accentColor).opacity(0.045),
                    Color(nsColor: .windowBackgroundColor)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()
        )
        .task {
            if viewModel.bootstrap == nil {
                await viewModel.refresh()
            }
            await loadNocturnalSpO2IfNeeded()
            await loadGarminTrendsIfNeeded()
            await loadLabTrendsIfNeeded()
            await loadInterventionsIfNeeded()
        }
        .sheet(item: $selectedGenomicDetail) { detail in
            switch detail {
            case .finding(let finding):
                GenomicFindingDetailSheet(
                    finding: finding,
                    onAddContext: onAddContext.map { add in
                        { add(genomicFindingContext(finding)) }
                    },
                    onAskAgent: onAskAgent.map { ask in
                        { ask(genomicFindingPrompt(finding), genomicFindingContext(finding)) }
                    }
                )
            case .category(let category):
                GenomicCategoryDetailSheet(
                    category: category,
                    findings: summary?.genomicSummary?.topFindings.filter { $0.category == category.category } ?? [],
                    onAddContext: onAddContext.map { add in
                        { add(genomicCategoryContext(category)) }
                    },
                    onAskAgent: onAskAgent.map { ask in
                        { ask(genomicCategoryPrompt(category), genomicCategoryContext(category)) }
                    }
                )
            }
        }
        .sheet(item: $selectedKnowledgeDocument) { document in
            KnowledgeDocumentDetailSheet(
                document: document,
                onAddContext: onAddContext.map { add in
                    { add(DesktopWorkspaceContextFactory.contextItem(for: document)) }
                },
                onAskAgent: onAskAgent.map { ask in
                    { ask(DesktopWorkspaceContextFactory.prompt(for: document), DesktopWorkspaceContextFactory.contextItem(for: document)) }
                }
            )
        }
        .sheet(item: $selectedHealthTrend) { trend in
            HealthTrendDetailSheet(
                context: trend,
                color: healthTrendColor(trend.kind),
                onAddContext: onAddContext.map { add in
                    { add(DesktopWorkspaceContextFactory.contextItem(for: trend)) }
                },
                onAskAgent: onAskAgent.map { ask in
                    { ask(DesktopWorkspaceContextFactory.prompt(for: trend), DesktopWorkspaceContextFactory.contextItem(for: trend)) }
                }
            )
        }
        .sheet(item: $selectedVital) { kind in
            VitalTrendDetailSheet(
                kind: kind,
                title: appText(kind.titleKey, appLanguageRaw),
                color: vitalColor(kind),
                initialRecords: garminRecords,
                initialRange: dataRange == "30d" ? 30 : 7,
                client: garminTrendClient,
                onAddContext: onAddContext.map { add in
                    { detail in add(DesktopWorkspaceContextFactory.contextItem(forVital: detail, title: appText(kind.titleKey, appLanguageRaw))) }
                },
                onAskAgent: onAskAgent.map { ask in
                    { detail in ask(DesktopWorkspaceContextFactory.prompt(forVital: detail, title: appText(kind.titleKey, appLanguageRaw)),
                                    DesktopWorkspaceContextFactory.contextItem(forVital: detail, title: appText(kind.titleKey, appLanguageRaw))) }
                }
            )
        }
    }

    private enum GenomicDetailRoute: Identifiable {
        case finding(GenomicFindingSummary)
        case category(GenomicCategorySummary)

        var id: String {
            switch self {
            case .finding(let finding):
                return "finding-\(finding.id)"
            case .category(let category):
                return "category-\(category.id)"
            }
        }
    }

    private var summary: DesktopWorkspaceSummary? {
        viewModel.bootstrap?.workspaceSummary(for: kind)
    }

    private func guidanceActionButton(_ row: DesktopWorkspaceGuidanceRow, summary: DesktopWorkspaceSummary) -> some View {
        Button {
            Task { await runGuidanceAction(row, summary: summary) }
        } label: {
            WorkspaceGuidanceCard(
                row: row,
                isWorking: runningGuidanceAction == row.action,
                ctaTitle: guidanceActionTitle(row.action)
            )
        }
        .buttonStyle(.plain)
        .disabled(runningGuidanceAction != nil)
        .help(guidanceActionTitle(row.action))
    }

    @ViewBuilder
    private var guidanceStatusView: some View {
        if let guidanceActionStatus {
            Text(guidanceActionStatus)
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.top, 4)
        }
    }

    @MainActor
    private func runGuidanceAction(_ row: DesktopWorkspaceGuidanceRow, summary: DesktopWorkspaceSummary) async {
        runningGuidanceAction = row.action
        guidanceActionStatus = nil
        defer { runningGuidanceAction = nil }

        do {
            switch row.action {
            case .refreshRecentHealthData:
                await viewModel.refresh()
                guidanceActionStatus = appText("Recent health data refreshed.", appLanguageRaw)
            case .importDedaoFolder:
                let job = try await createGuidanceJob(
                    jobType: "dedao_compile",
                    sourceKind: "dedao_folder",
                    sourceName: "down-dedao",
                    payload: [
                        "raw_upload_confirmed": true,
                        "source_url": .string(defaultDedaoFolderURL.path),
                        "source_hint": .string("local_down_dedao")
                    ]
                )
                guidanceActionStatus = "\(appText("Created desktop job", appLanguageRaw)) #\(job.id) · \(job.status)"
            case .rebuildSystemKnowledgeBase:
                let job = try await createGuidanceJob(
                    jobType: "system_kb_rebuild",
                    sourceKind: "system_knowledge_base",
                    sourceName: "system-kb",
                    payload: [
                        "source_root": .string(summary.knowledgeSummary?.localSourceSummary?.sourceRoot ?? defaultDedaoFolderURL.path),
                        "include_dedao_bridge": true,
                        "include_pubmed_sources": true
                    ]
                )
                guidanceActionStatus = "\(appText("Created desktop job", appLanguageRaw)) #\(job.id) · \(job.status)"
            case .auditSourceCoverage, .reviewWeeklyIntake, .reviewClinicalBoundary, .createMedicalImport, .importGenomeFile, .runRiskReanalysis:
                let item = DesktopWorkspaceContextFactory.contextItem(for: row, workspace: summary)
                onAskAgent?(DesktopWorkspaceContextFactory.prompt(for: row, workspace: summary), item)
                guidanceActionStatus = appText("Opened a fresh Agent draft with this workspace context.", appLanguageRaw)
            }

            if row.action == .importDedaoFolder || row.action == .rebuildSystemKnowledgeBase {
                await viewModel.refresh()
            }
        } catch {
            guidanceActionStatus = "\(appText("Action failed", appLanguageRaw)): \(error.localizedDescription)"
        }
    }

    private func createGuidanceJob(
        jobType: String,
        sourceKind: String,
        sourceName: String,
        payload: [String: JSONValue]
    ) async throws -> DesktopJobSummary {
        try await jobClient.createJob(.init(
            jobType: jobType,
            sourceKind: sourceKind,
            sourceName: sourceName,
            sourceHash: nil,
            requestPayload: payload
        ))
    }

    private var defaultDedaoFolderURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("work/personal/down-dedao", isDirectory: true)
    }

    private func guidanceActionTitle(_ action: DesktopWorkspaceGuidanceAction) -> String {
        switch action {
        case .refreshRecentHealthData:
            appText("Refresh", appLanguageRaw)
        case .importDedaoFolder:
            appText("Create Import Job", appLanguageRaw)
        case .rebuildSystemKnowledgeBase:
            appText("Create Rebuild Job", appLanguageRaw)
        case .auditSourceCoverage, .reviewWeeklyIntake, .reviewClinicalBoundary, .createMedicalImport, .importGenomeFile, .runRiskReanalysis:
            appText("Ask", appLanguageRaw)
        }
    }

    @ViewBuilder
    private func workspaceSummary(_ summary: DesktopWorkspaceSummary) -> some View {
        if kind == .data {
            dataWorkspaceSummary(summary)
        } else if kind == .knowledge {
            knowledgeWorkspaceSummary(summary)
        } else {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 12)], spacing: 12) {
                ForEach(summary.metrics) { metric in
                    WorkspaceMetricCard(metric: metric)
                }
            }

            SectionPanel(title: appText("Workspace Actions", appLanguageRaw), systemImage: "wand.and.stars") {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 10)], spacing: 10) {
                    ForEach(summary.guidanceRows) { row in
                        guidanceActionButton(row, summary: summary)
                    }
                }
                guidanceStatusView
            }

            SectionPanel(title: appText("Priority Actions", appLanguageRaw), systemImage: "checklist") {
                if summary.actionCards.isEmpty {
                    Text(appText("No actions loaded yet.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                } else {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 10)], spacing: 10) {
                        ForEach(summary.actionCards.prefix(6)) { card in
                            WorkspaceActionCard(
                                card: card,
                                color: kind == .genetics ? .purple : .teal,
                                systemImage: kind == .genetics ? "atom" : "books.vertical.fill"
                            )
                        }
                    }
                }
            }
        }

        if kind != .data {
            if kind == .genetics {
                geneticsWorkspaceDetails(summary)
            }
        }

        workspaceSideSections(summary)
    }

    @ViewBuilder
    private func dataWorkspaceSummary(_ summary: DesktopWorkspaceSummary) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .center) {
                Label(appText("Health Data Command Center", appLanguageRaw), systemImage: "chart.line.uptrend.xyaxis")
                    .font(.title3.bold())
                Spacer()
                Picker(appText("Range", appLanguageRaw), selection: $dataRange) {
                    Text(appText("7 days", appLanguageRaw)).tag("7d")
                    Text(appText("30 days", appLanguageRaw)).tag("30d")
                }
                .pickerStyle(.segmented)
                .frame(width: 180)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 205), spacing: 12)], spacing: 12) {
                ForEach(dataMetrics(summary)) { metric in
                    if let trend = dataTrendContext(for: metric) {
                        Button {
                            selectedHealthTrend = trend
                        } label: {
                            WorkspaceMetricCard(metric: metric, showsDisclosure: true)
                        }
                        .buttonStyle(.plain)
                        .help(appText("Click to inspect trend", appLanguageRaw))
                    } else {
                        WorkspaceMetricCard(metric: metric)
                    }
                }
            }

            dataTrendPanel

            if kind == .data {
                vitalsSnapshotPanel
                vitalsTrendPanel
                sleepStageTrendPanel
                nocturnalWeekStripPanel
                nocturnalSpO2Panel
                labTrendsPanel
            }

            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 16) {
                    dataGuidancePanel(summary)
                        .frame(minWidth: 520, maxWidth: .infinity, alignment: .topLeading)
                    dataRecordsPanel(summary)
                        .frame(width: 430, alignment: .topLeading)
                }
                VStack(alignment: .leading, spacing: 16) {
                    dataGuidancePanel(summary)
                    dataRecordsPanel(summary)
                }
            }

            dataActionPanel(summary)
        }
    }

    private func dataMetrics(_ summary: DesktopWorkspaceSummary) -> [DesktopWorkspaceMetric] {
        guard let recordsSummary = viewModel.bootstrap?.recentRecordsSummary else {
            return summary.metrics
        }
        let days = dataRange == "30d" ? 30 : 7
        // Plain if/else over single `??` chains — inline ternary-over-long-?? trips
        // the CI runner's stricter type-checker ("unable to type-check in
        // reasonable time"). See DesktopDashboardPresentation.rangeMetrics.
        let diet = recordsSummary.diet
        let water = recordsSummary.water
        let supp = recordsSummary.supplements
        let dietCalories: Double
        let waterMl: Int
        let supplements: Int
        if days == 30 {
            dietCalories = diet?.last30Calories ?? diet?.last7Calories ?? diet?.todayCalories ?? 0
            waterMl = water?.last30TotalMl ?? water?.last7TotalMl ?? water?.todayTotalMl ?? 0
            supplements = supp?.last30Count ?? supp?.last7Count ?? supp?.todayCount ?? 0
        } else {
            dietCalories = diet?.last7Calories ?? diet?.last30Calories ?? diet?.todayCalories ?? 0
            waterMl = water?.last7TotalMl ?? water?.last30TotalMl ?? water?.todayTotalMl ?? 0
            supplements = supp?.last7Count ?? supp?.last30Count ?? supp?.todayCount ?? 0
        }
        return [
            .init(id: "diet_calories", title: days == 30 ? "Diet 30d" : "Diet 7d", value: "\(formatCompactNumber(dietCalories)) kcal"),
            .init(id: "water_ml", title: days == 30 ? "Water 30d" : "Water 7d", value: "\(formatCompactNumber(Double(waterMl))) ml"),
            .init(id: "supplements", title: days == 30 ? "Supplements 30d" : "Supplements 7d", value: "\(supplements)"),
            .init(id: "latest_weight", title: "Latest Weight", value: recordsSummary.latestWeight?.displayValue ?? "—"),
            .init(id: "latest_bp", title: "Latest BP", value: recordsSummary.latestBloodPressure?.displayValue ?? "—"),
            .init(id: "steps", title: "Steps", value: recordsSummary.latestGarmin?.steps.map { formatCompactNumber(Double($0)) } ?? "—")
        ]
    }

    private var dataTrendPanel: some View {
        let is30Days = dataRange == "30d"
        let trends = primaryHealthTrendContexts()
        return VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label(appText("Trends", appLanguageRaw), systemImage: "chart.xyaxis.line")
                    .font(.headline)
                Spacer()
                Text(appText(is30Days ? "30 days" : "7 days", appLanguageRaw))
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 10)], spacing: 10) {
                ForEach(trends) { trend in
                    Button {
                        selectedHealthTrend = trend
                    } label: {
                        DataTrendCard(
                            title: appText(trend.title, appLanguageRaw),
                            value: trendAverageLabel(value: trend.average, unit: trend.unit),
                            color: healthTrendColor(trend.kind),
                            points: trend.points.map(\.value),
                            showsDisclosure: true
                        )
                    }
                    .buttonStyle(.plain)
                    .help(appText("Click to inspect trend", appLanguageRaw))
                }
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private func trendAverageLabel(value: Double?, unit: String) -> String {
        "\(appText("Avg", appLanguageRaw)) \(formatCompactNumber(value ?? 0))\(appText(unit, appLanguageRaw))"
    }

    private var nocturnalTargetDate: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone.current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    @MainActor
    private func loadNocturnalSpO2IfNeeded() async {
        guard kind == .data, let client = nocturnalClient else { return }
        let target = nocturnalTargetDate
        await loadNocturnalWeekIfNeeded(client: client)
        if nocturnalLoadedDate == target { return }
        nocturnalLoading = true
        nocturnalError = nil
        defer { nocturnalLoading = false }
        do {
            let snapshot = try await client.fetchNightly(date: target)
            nocturnalNight = snapshot
            nocturnalSpO2 = snapshot.spo2
            nocturnalLoadedDate = target
        } catch {
            nocturnalNight = nil
            nocturnalSpO2 = nil
            nocturnalError = error.localizedDescription
            nocturnalLoadedDate = target
        }
    }

    @MainActor
    private func loadNocturnalWeekIfNeeded(client: NocturnalTimeseriesClient) async {
        if nocturnalWeekLoaded || nocturnalWeekLoading { return }
        nocturnalWeekLoading = true
        defer { nocturnalWeekLoading = false }
        let nights = await client.fetchSpO2WeekSummary(endDate: Date(), days: 7)
        nocturnalWeek = nights
        nocturnalWeekLoaded = true
    }

    @MainActor
    private func loadGarminTrendsIfNeeded() async {
        guard kind == .data, !garminLoaded, let client = garminTrendClient else { return }
        garminLoaded = true
        garminRecords = await client.fetchDaily(limit: 30)
    }

    /// 当前 range (7/30 天) 对应的生理趋势快照。
    private var vitalsPresentation: VitalsTrendPresentation {
        VitalsTrendPresentation(records: garminRecords, lastDays: dataRange == "30d" ? 30 : 7)
    }

    /// 快照卡：当该指标有 ≥2 个趋势点时，可点击进入与趋势卡相同的详情 sheet。
    /// 点数不足时只展示静态卡（无法画出有意义的趋势）。
    @ViewBuilder
    private func vitalSnapshotTappable<Content: View>(
        _ kind: VitalMetricKind,
        points: Int,
        @ViewBuilder card: (Bool) -> Content
    ) -> some View {
        if points >= 2 {
            Button {
                selectedVital = kind
            } label: {
                card(true)
            }
            .buttonStyle(.plain)
            .help(appText("Click to inspect trend", appLanguageRaw))
        } else {
            card(false)
        }
    }

    @ViewBuilder
    private var vitalsSnapshotPanel: some View {
        let p = vitalsPresentation
        if p.hasData {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .firstTextBaseline) {
                    Label(appText("Vitals & Sleep", appLanguageRaw), systemImage: "heart.text.square.fill")
                        .font(.headline)
                        .foregroundStyle(.pink)
                    Spacer()
                    if let date = p.latestDate {
                        Text(date)
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 12)], spacing: 12) {
                    vitalSnapshotTappable(.hrv, points: p.hrvSeries.points.count) { tappable in
                        VitalSnapshotCard(icon: "waveform.path.ecg", color: .pink,
                                          title: appText("HRV", appLanguageRaw),
                                          value: p.latestHRV.map { "\(Int($0.rounded()))" } ?? "—",
                                          unit: p.latestHRV == nil ? "" : "ms",
                                          showsDisclosure: tappable)
                    }
                    vitalSnapshotTappable(.restingHR, points: p.restingHRSeries.points.count) { tappable in
                        VitalSnapshotCard(icon: "heart.fill", color: .red,
                                          title: appText("Resting HR", appLanguageRaw),
                                          value: p.latestRestingHR.map(String.init) ?? "—",
                                          unit: p.latestRestingHR == nil ? "" : "bpm",
                                          showsDisclosure: tappable)
                    }
                    vitalSnapshotTappable(.avgHR, points: p.avgHRSeries.points.count) { tappable in
                        VitalSnapshotCard(icon: "heart.circle.fill", color: .orange,
                                          title: appText("Avg HR", appLanguageRaw),
                                          value: p.latestAvgHR.map(String.init) ?? "—",
                                          unit: p.latestAvgHR == nil ? "" : "bpm",
                                          showsDisclosure: tappable)
                    }
                    vitalSnapshotTappable(.stress, points: p.stressSeries.points.count) { tappable in
                        VitalSnapshotCard(icon: "brain.head.profile", color: .purple,
                                          title: appText("Stress", appLanguageRaw),
                                          value: p.latestStress.map(String.init) ?? "—",
                                          unit: "",
                                          showsDisclosure: tappable)
                    }
                    vitalSnapshotTappable(.bodyBattery, points: p.bodyBatterySeries.points.count) { tappable in
                        VitalSnapshotCard(icon: "bolt.fill", color: .green,
                                          title: appText("Body Battery", appLanguageRaw),
                                          value: p.latestBodyBattery.map(String.init) ?? "—",
                                          unit: p.latestBodyBatteryLowest.map { "\(appText("low", appLanguageRaw)) \($0)" } ?? "",
                                          showsDisclosure: tappable)
                    }
                    vitalSnapshotTappable(.sleepHours, points: p.sleepHoursSeries.points.count) { tappable in
                        VitalSnapshotCard(icon: "bed.double.fill", color: .indigo,
                                          title: appText("Sleep", appLanguageRaw),
                                          value: p.latestSleepHours.map { String(format: "%.1f", $0) } ?? "—",
                                          unit: vitalsSleepUnit(p),
                                          showsDisclosure: tappable)
                    }
                }
                if let stages = p.sleepStages, stages.hasData {
                    SleepStagesBar(
                        stages: stages,
                        deepLabel: appText("Deep", appLanguageRaw),
                        lightLabel: appText("Light", appLanguageRaw),
                        remLabel: appText("REM", appLanguageRaw),
                        awakeLabel: appText("Awake", appLanguageRaw)
                    )
                }
            }
            .padding(18)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
            }
        }
    }

    private func vitalsSleepUnit(_ p: VitalsTrendPresentation) -> String {
        guard p.latestSleepHours != nil else { return "" }
        if let score = p.latestSleepScore {
            return "h · \(appText("score", appLanguageRaw)) \(score)"
        }
        return "h"
    }

    @ViewBuilder
    private var vitalsTrendPanel: some View {
        let p = vitalsPresentation
        let cards = vitalsTrendCards(p)
        if !cards.isEmpty {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Label(appText("Vitals & Sleep Trends", appLanguageRaw), systemImage: "chart.xyaxis.line")
                        .font(.headline)
                        .foregroundStyle(.pink)
                    Spacer()
                    Text(appText(dataRange == "30d" ? "30 days" : "7 days", appLanguageRaw))
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                }
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 10)], spacing: 10) {
                    ForEach(cards) { card in
                        Button {
                            selectedVital = card.kind
                        } label: {
                            DataTrendCard(
                                title: card.title,
                                value: card.value,
                                color: card.color,
                                points: card.points,
                                showsDisclosure: true
                            )
                        }
                        .buttonStyle(.plain)
                        .help(appText("Click to inspect trend", appLanguageRaw))
                    }
                }
            }
            .padding(18)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
            }
        }
    }

    private struct VitalsTrendCardModel: Identifiable {
        let id: String
        let kind: VitalMetricKind
        let title: String
        let value: String
        let color: Color
        let points: [Double]
    }

    private func vitalColor(_ kind: VitalMetricKind) -> Color {
        switch kind {
        case .hrv: return .pink
        case .restingHR: return .red
        case .avgHR: return .orange
        case .stress: return .purple
        case .bodyBattery: return .green
        case .sleepHours: return .indigo
        }
    }

    private func vitalsTrendCards(_ p: VitalsTrendPresentation) -> [VitalsTrendCardModel] {
        func avgLabel(_ series: VitalsTrendPresentation.Series, _ unit: String, decimals: Int = 0) -> String {
            guard let avg = series.average else { return "—" }
            let number = decimals > 0 ? String(format: "%.\(decimals)f", avg) : "\(Int(avg.rounded()))"
            return "\(appText("Avg", appLanguageRaw)) \(number)\(unit)"
        }
        func card(_ kind: VitalMetricKind, _ series: VitalsTrendPresentation.Series, _ unit: String, decimals: Int = 0) -> VitalsTrendCardModel? {
            guard series.points.count >= 2 else { return nil }
            return VitalsTrendCardModel(
                id: kind.rawValue,
                kind: kind,
                title: appText(kind.titleKey, appLanguageRaw),
                value: avgLabel(series, unit, decimals: decimals),
                color: vitalColor(kind),
                points: series.points
            )
        }
        return [
            card(.hrv, p.hrvSeries, "ms"),
            card(.restingHR, p.restingHRSeries, "bpm"),
            card(.avgHR, p.avgHRSeries, "bpm"),
            card(.stress, p.stressSeries, ""),
            card(.bodyBattery, p.bodyBatterySeries, ""),
            card(.sleepHours, p.sleepHoursSeries, "h", decimals: 1)
        ].compactMap { $0 }
    }

    @ViewBuilder
    private var sleepStageTrendPanel: some View {
        let days = vitalsPresentation.sleepStageDays
        if days.count >= 2 {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Label(appText("Sleep Stages", appLanguageRaw), systemImage: "bed.double.fill")
                        .font(.headline)
                        .foregroundStyle(.indigo)
                    Spacer()
                    Text(appText(dataRange == "30d" ? "30 days" : "7 days", appLanguageRaw))
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                }
                SleepStageTrendChart(
                    days: days,
                    deepLabel: appText("Deep", appLanguageRaw),
                    lightLabel: appText("Light", appLanguageRaw),
                    remLabel: appText("REM", appLanguageRaw),
                    awakeLabel: appText("Awake", appLanguageRaw)
                )
            }
            .padding(18)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
            }
        }
    }

    private var nocturnalSpO2Panel: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Label(appText("Nighttime SpO2", appLanguageRaw), systemImage: "lungs.fill")
                    .font(.headline)
                    .foregroundStyle(.cyan)
                Spacer()
                if let summary = nocturnalSpO2, !summary.samples.isEmpty {
                    Text(summary.date)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                Button {
                    Task {
                        nocturnalLoadedDate = nil
                        nocturnalWeekLoaded = false
                        nocturnalWeek = []
                        await loadNocturnalSpO2IfNeeded()
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.borderless)
                .help(appText("Refresh", appLanguageRaw))
            }

            if nocturnalLoading && nocturnalSpO2 == nil {
                HStack {
                    ProgressView()
                        .controlSize(.small)
                    Text(appText("Loading nightly SpO2...", appLanguageRaw))
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 80, alignment: .center)
            } else if let summary = nocturnalSpO2, !summary.samples.isEmpty {
                nocturnalSpO2Body(summary: summary)
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    Text(appText("No SpO2 data for last night.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                    Text(appText("Wear your Garmin during sleep to capture overnight SpO2.", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let nocturnalError {
                        Text(nocturnalError)
                            .font(.caption2)
                            .foregroundStyle(.red.opacity(0.8))
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 80, alignment: .leading)
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    @ViewBuilder
    private func nocturnalSpO2Body(summary: NocturnalSpO2Summary) -> some View {
        let sparkValues = summary.samples.compactMap { $0.value }

        HStack(alignment: .top, spacing: 24) {
            VStack(alignment: .leading, spacing: 6) {
                spo2Stat(
                    label: appText("Lowest", appLanguageRaw),
                    value: summary.minValue.map { String(format: "%.0f%%", $0) } ?? "—",
                    color: (summary.minValue ?? 100) < 90 ? .red : (summary.minValue ?? 100) < 94 ? .orange : .green
                )
                spo2Stat(
                    label: appText("Average", appLanguageRaw),
                    value: summary.avgValue.map { String(format: "%.1f%%", $0) } ?? "—",
                    color: .cyan
                )
                spo2Stat(
                    label: appText("Below 90%", appLanguageRaw),
                    value: summary.percentBelow90.map { String(format: "%.1f%%", $0) } ?? "—",
                    color: (summary.percentBelow90 ?? 0) > 1 ? .red : .secondary
                )
                spo2Stat(
                    label: appText("Samples", appLanguageRaw),
                    value: "\(summary.samples.count)",
                    color: .secondary
                )
            }
            .frame(width: 180, alignment: .leading)

            SpO2Sparkline(values: sparkValues)
                .frame(maxWidth: .infinity, minHeight: 120)
        }

        if let snapshot = nocturnalNight {
            nocturnalMultiMetricOverlay(snapshot: snapshot)
        }

        if !summary.lowestEpisodes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text(appText("Lowest episodes", appLanguageRaw))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                ForEach(Array(summary.lowestEpisodes.enumerated()), id: \.offset) { _, point in
                    HStack(spacing: 8) {
                        Image(systemName: "arrow.down.circle.fill")
                            .foregroundStyle(.red)
                        Text(point.sampleTime)
                            .font(.caption.monospacedDigit())
                        Text(point.value.map { String(format: "%.0f%%", $0) } ?? "—")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.red)
                    }
                }
            }
        }

        if let onAskAgent {
            HStack(spacing: 10) {
                Button {
                    let prompt = nocturnalSpO2Prompt(summary: summary)
                    onAskAgent(prompt, nocturnalSpO2ContextItem(summary: summary))
                } label: {
                    Label(appText("Ask Agent about this", appLanguageRaw), systemImage: "sparkles")
                }
                .buttonStyle(.bordered)

                if let onAddContext {
                    Button {
                        onAddContext(nocturnalSpO2ContextItem(summary: summary))
                    } label: {
                        Label(appText("Add to context", appLanguageRaw), systemImage: "tray.and.arrow.down")
                    }
                    .buttonStyle(.bordered)
                }

                Spacer()
            }
        }
    }

    private func spo2Stat(label: String, value: String, color: Color) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer(minLength: 8)
            Text(value)
                .font(.callout.weight(.semibold).monospacedDigit())
                .foregroundStyle(color)
        }
    }

    private func nocturnalSpO2Prompt(summary: NocturnalSpO2Summary) -> String {
        let minStr = summary.minValue.map { String(format: "%.0f%%", $0) } ?? "—"
        let avgStr = summary.avgValue.map { String(format: "%.1f%%", $0) } ?? "—"
        let belowStr = summary.percentBelow90.map { String(format: "%.1f%%", $0) } ?? "—"
        return "请基于昨夜 SpO2 数据评估呼吸/睡眠风险（最低 \(minStr)，平均 \(avgStr)，低于 90% 占比 \(belowStr)），并给出后续监测建议。"
    }

    private func nocturnalSpO2ContextItem(summary: NocturnalSpO2Summary) -> AgentContextItem {
        let minStr = summary.minValue.map { String(format: "%.0f%%", $0) } ?? "—"
        let avgStr = summary.avgValue.map { String(format: "%.1f%%", $0) } ?? "—"
        let belowStr = summary.percentBelow90.map { String(format: "%.1f%%", $0) } ?? "—"
        return AgentContextItem(
            sourceID: "nocturnal-spo2-\(summary.date)",
            sourceKind: "nocturnal_spo2",
            title: "Nighttime SpO2 · \(summary.date)",
            summary: "Min \(minStr) · Avg \(avgStr) · Below 90% \(belowStr) · \(summary.samples.count) samples",
            payload: [
                "date": summary.date,
                "min": summary.minValue.map { String(format: "%.1f", $0) } ?? "",
                "avg": summary.avgValue.map { String(format: "%.2f", $0) } ?? "",
                "below_90_pct": summary.percentBelow90.map { String(format: "%.2f", $0) } ?? "",
                "sample_count": "\(summary.samples.count)"
            ]
        )
    }

    @ViewBuilder
    private func nocturnalMultiMetricOverlay(snapshot: NocturnalNightSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Divider().opacity(0.4)
            Text(appText("Aligned overnight metrics", appLanguageRaw))
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)

            VStack(spacing: 6) {
                metricMiniRow(
                    label: appText("Heart rate", appLanguageRaw),
                    summary: snapshot.heartRate,
                    color: .pink,
                    unit: "bpm",
                    yMin: 35, yMax: 110
                )
                metricMiniRow(
                    label: appText("Respiration", appLanguageRaw),
                    summary: snapshot.respiration,
                    color: .blue,
                    unit: "rpm",
                    yMin: 8, yMax: 22
                )
                metricMiniRow(
                    label: appText("HRV", appLanguageRaw),
                    summary: snapshot.hrv,
                    color: .green,
                    unit: "ms",
                    yMin: 15, yMax: 90
                )
                metricMiniRow(
                    label: appText("Stress", appLanguageRaw),
                    summary: snapshot.stress,
                    color: .orange,
                    unit: "",
                    yMin: 0, yMax: 100
                )
            }

            if !snapshot.sleepStages.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text(appText("Sleep stages", appLanguageRaw))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    SleepStageBand(stages: snapshot.sleepStages)
                        .frame(height: 18)
                    SleepStageLegend(language: appLanguageRaw)
                }
                .padding(.top, 4)
            }
        }
    }

    private func metricMiniRow(
        label: String,
        summary: NocturnalMetricSummary,
        color: Color,
        unit: String,
        yMin: Double,
        yMax: Double
    ) -> some View {
        HStack(spacing: 10) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 90, alignment: .leading)

            MetricMiniSparkline(
                values: summary.samples.compactMap { $0.value },
                color: color,
                yMin: yMin,
                yMax: yMax
            )
            .frame(maxWidth: .infinity, minHeight: 28)

            HStack(spacing: 4) {
                if let avg = summary.avgValue {
                    Text(String(format: "%.0f", avg))
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(color)
                } else {
                    Text("—")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                if !unit.isEmpty {
                    Text(unit)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            .frame(width: 60, alignment: .trailing)
        }
    }

    private var nocturnalWeekStripPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(appText("Last 7 nights SpO2", appLanguageRaw), systemImage: "calendar")
                    .font(.headline)
                    .foregroundStyle(.cyan)
                Spacer()
                if nocturnalWeekLoading {
                    ProgressView().controlSize(.small)
                }
            }

            if nocturnalWeek.isEmpty && !nocturnalWeekLoading {
                Text(appText("No SpO2 history available.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                HStack(alignment: .center, spacing: 8) {
                    ForEach(nocturnalWeek) { night in
                        VStack(spacing: 6) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(weekNightColor(night).opacity(0.85))
                                if let summary = night.summary, let minValue = summary.minValue {
                                    Text(String(format: "%.0f", minValue))
                                        .font(.system(size: 11, weight: .semibold).monospacedDigit())
                                        .foregroundStyle(.white)
                                } else {
                                    Image(systemName: "minus")
                                        .font(.caption2)
                                        .foregroundStyle(.white.opacity(0.7))
                                }
                            }
                            .frame(height: 56)
                            Text(weekNightLabel(night.date))
                                .font(.system(size: 9).monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                    }
                }

                HStack(spacing: 10) {
                    weekStripLegendItem(color: .green, text: ">= 94%")
                    weekStripLegendItem(color: .yellow, text: "90–93%")
                    weekStripLegendItem(color: .orange, text: "85–89%")
                    weekStripLegendItem(color: .red, text: "< 85%")
                    Spacer()
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private func weekStripLegendItem(color: Color, text: String) -> some View {
        HStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(color)
                .frame(width: 10, height: 10)
            Text(text)
        }
    }

    private func weekNightColor(_ night: NocturnalWeekNight) -> Color {
        guard let minValue = night.summary?.minValue else { return Color.gray.opacity(0.4) }
        switch minValue {
        case ..<85: return .red
        case ..<90: return .orange
        case ..<94: return .yellow
        default: return .green
        }
    }

    private func weekNightLabel(_ date: String) -> String {
        // "yyyy-MM-dd" → "MM-dd"
        let parts = date.split(separator: "-")
        if parts.count == 3 {
            return "\(parts[1])-\(parts[2])"
        }
        return date
    }

    // MARK: - Lab indicator trends (A2)

    @MainActor
    private func loadLabTrendsIfNeeded() async {
        guard kind == .data, let client = labClient, !labLoaded, !labLoading else { return }
        labLoading = true
        labError = nil
        defer { labLoading = false }
        do {
            let series = try await client.fetchIndicatorTrends()
            let nonEmpty = series.filter { !$0.data.isEmpty }
            labSeries = nonEmpty
            if selectedLabCode == nil {
                selectedLabCode = nonEmpty.first?.code
            }
            labLoaded = true
        } catch {
            labError = error.localizedDescription
            labLoaded = true
        }
    }

    @MainActor
    private func loadInterventionsIfNeeded() async {
        guard kind == .data, let client = interventionsClient, !interventionsLoaded else { return }
        interventionEvents = await client.fetchEvents()
        interventionsLoaded = true
    }

    private var labTrendsPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(appText("Lab indicator trends", appLanguageRaw), systemImage: "chart.xyaxis.line")
                    .font(.headline)
                    .foregroundStyle(.purple)
                Spacer()
                if labLoading {
                    ProgressView().controlSize(.small)
                }
                Button {
                    Task {
                        labLoaded = false
                        await loadLabTrendsIfNeeded()
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.borderless)
                .help(appText("Refresh", appLanguageRaw))
            }

            if let labError {
                Text(labError)
                    .font(.caption)
                    .foregroundStyle(.red.opacity(0.8))
            } else if labSeries.isEmpty && !labLoading {
                VStack(alignment: .leading, spacing: 4) {
                    Text(appText("No lab indicator data yet.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                    Text(appText("Import a medical exam PDF or photo to start tracking.", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 60, alignment: .leading)
            } else if let selected = selectedLabSeries {
                labTrendsBody(selected: selected)
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private var selectedLabSeries: LabIndicatorSeries? {
        guard let code = selectedLabCode else { return labSeries.first }
        return labSeries.first { $0.code == code } ?? labSeries.first
    }

    @ViewBuilder
    private func labTrendsBody(selected: LabIndicatorSeries) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(labSeries) { series in
                    let isSelected = series.code == (selectedLabCode ?? labSeries.first?.code)
                    Button {
                        selectedLabCode = series.code
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(series.displayName)
                                .font(.caption.weight(.semibold))
                            HStack(spacing: 4) {
                                if let latest = series.latest, let value = latest.value {
                                    Text(formatLabValue(value))
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(latest.isAbnormal == true ? Color.red : Color.primary)
                                }
                                if series.abnormalCount > 0 {
                                    Image(systemName: "exclamationmark.triangle.fill")
                                        .font(.system(size: 8))
                                        .foregroundStyle(.orange)
                                }
                            }
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .fill(isSelected ? Color.purple.opacity(0.18) : Color.secondary.opacity(0.08))
                        )
                        .overlay {
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .stroke(isSelected ? Color.purple.opacity(0.6) : Color.clear, lineWidth: 1)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
        }

        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(selected.displayName)
                    .font(.title3.weight(.semibold))
                if let unit = selected.unit, !unit.isEmpty {
                    Text("(\(unit))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if let low = selected.referenceLow, let high = selected.referenceHigh {
                    Text("\(appText("Reference", appLanguageRaw)) \(formatLabValue(low))–\(formatLabValue(high))")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }

            LabSeriesChart(series: selected, interventions: interventionEvents)
                .frame(height: 160)

            if !visibleInterventions(for: selected).isEmpty {
                interventionLegend(for: selected)
            }

            HStack(spacing: 18) {
                if let latest = selected.latest, let value = latest.value {
                    labStat(label: appText("Latest", appLanguageRaw), value: formatLabValue(value), date: latest.date, abnormal: latest.isAbnormal == true)
                }
                if let earliest = selected.earliest, let value = earliest.value {
                    labStat(label: appText("First", appLanguageRaw), value: formatLabValue(value), date: earliest.date, abnormal: false)
                }
                labStat(label: appText("Visits", appLanguageRaw), value: "\(selected.data.count)", date: nil, abnormal: false)
                if selected.abnormalCount > 0 {
                    labStat(label: appText("Abnormal", appLanguageRaw), value: "\(selected.abnormalCount)", date: nil, abnormal: true)
                }
                Spacer()
            }

            if let onAskAgent {
                HStack(spacing: 10) {
                    Button {
                        onAskAgent(labPromptText(series: selected), labContextItem(series: selected))
                    } label: {
                        Label(appText("Ask Agent about this", appLanguageRaw), systemImage: "sparkles")
                    }
                    .buttonStyle(.bordered)

                    if let onAddContext {
                        Button {
                            onAddContext(labContextItem(series: selected))
                        } label: {
                            Label(appText("Add to context", appLanguageRaw), systemImage: "tray.and.arrow.down")
                        }
                        .buttonStyle(.bordered)
                    }
                    Spacer()
                }
            }
        }
    }

    private func labStat(label: String, value: String, date: String?, abnormal: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.callout.monospacedDigit().weight(.semibold))
                .foregroundStyle(abnormal ? Color.red : Color.primary)
            if let date {
                Text(date)
                    .font(.system(size: 9).monospacedDigit())
                    .foregroundStyle(.tertiary)
            }
        }
    }

    private func visibleInterventions(for series: LabIndicatorSeries) -> [InterventionEvent] {
        guard let first = series.sortedData.first?.date, let last = series.sortedData.last?.date else {
            return []
        }
        return interventionEvents.filter { $0.date >= first && $0.date <= last }
    }

    private func interventionLegend(for series: LabIndicatorSeries) -> some View {
        let events = visibleInterventions(for: series)
        let preview = events.suffix(4)
        return HStack(alignment: .top, spacing: 12) {
            HStack(spacing: 6) {
                Circle().fill(Color.orange).frame(width: 6, height: 6)
                Text(appText("Medication started", appLanguageRaw))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Circle().fill(Color.teal).frame(width: 6, height: 6)
                Text(appText("Supplement started", appLanguageRaw))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            if !preview.isEmpty {
                VStack(alignment: .trailing, spacing: 1) {
                    ForEach(Array(preview), id: \.id) { event in
                        Text("\(event.date) · \(event.label)")
                            .font(.system(size: 9).monospacedDigit())
                            .foregroundStyle(event.kind == .medication ? Color.orange : Color.teal)
                    }
                }
            }
        }
    }

    private func formatLabValue(_ value: Double) -> String {
        if abs(value) >= 100 {
            return String(format: "%.0f", value)
        }
        if abs(value) >= 10 {
            return String(format: "%.1f", value)
        }
        return String(format: "%.2f", value)
    }

    private func labPromptText(series: LabIndicatorSeries) -> String {
        let latest = series.latest.flatMap { $0.value }.map { formatLabValue($0) } ?? "—"
        let earliest = series.earliest.flatMap { $0.value }.map { formatLabValue($0) } ?? "—"
        let unit = series.unit ?? ""
        var ref = ""
        if let low = series.referenceLow, let high = series.referenceHigh {
            ref = "（参考 \(formatLabValue(low))–\(formatLabValue(high))\(unit)）"
        }
        return "请分析我的 \(series.displayName)\(ref) 长期趋势：最早 \(earliest)\(unit)、最近 \(latest)\(unit)，共 \(series.data.count) 次。异常 \(series.abnormalCount) 次。结合我的基因和生活方式给出解读和建议。"
    }

    private func labContextItem(series: LabIndicatorSeries) -> AgentContextItem {
        let sortedPoints = series.sortedData
        let dataDescription = sortedPoints.compactMap { point -> String? in
            guard let value = point.value else { return nil }
            return "\(point.date)=\(formatLabValue(value))"
        }.joined(separator: ", ")

        var payload: [String: String] = [
            "code": series.code,
            "name": series.displayName,
            "visits": "\(series.data.count)",
            "abnormal_count": "\(series.abnormalCount)",
        ]
        if let unit = series.unit { payload["unit"] = unit }
        if let low = series.referenceLow { payload["reference_low"] = formatLabValue(low) }
        if let high = series.referenceHigh { payload["reference_high"] = formatLabValue(high) }
        if let latest = series.latest, let value = latest.value {
            payload["latest_date"] = latest.date
            payload["latest_value"] = formatLabValue(value)
        }
        if !dataDescription.isEmpty {
            payload["timeline"] = dataDescription
        }
        let summary = "\(series.data.count) visits · \(series.abnormalCount) abnormal"

        return AgentContextItem(
            sourceID: "lab-trend-\(series.code)",
            sourceKind: "lab_trend",
            title: "\(series.displayName) trend",
            summary: summary,
            payload: payload
        )
    }

    private var dataRangeDays: Int {
        dataRange == "30d" ? 30 : 7
    }

    private func primaryHealthTrendContexts() -> [DesktopHealthTrendContext] {
        [.diet, .water, .supplements].compactMap { dataTrendContext(for: $0) }
    }

    private func dataTrendContext(for metric: DesktopWorkspaceMetric) -> DesktopHealthTrendContext? {
        switch metric.id {
        case "diet_calories":
            return dataTrendContext(for: .diet)
        case "water_ml":
            return dataTrendContext(for: .water)
        case "supplements":
            return dataTrendContext(for: .supplements)
        case "latest_weight":
            return dataTrendContext(for: .weight)
        case "latest_bp":
            return dataTrendContext(for: .bloodPressure)
        case "steps":
            return dataTrendContext(for: .steps)
        default:
            return nil
        }
    }

    private func dataTrendContext(for kind: DesktopHealthTrendKind) -> DesktopHealthTrendContext? {
        guard let recordsSummary = viewModel.bootstrap?.recentRecordsSummary else {
            return nil
        }
        let days = dataRangeDays
        switch kind {
        case .diet:
            guard let diet = recordsSummary.diet else { return nil }
            let points = (days == 30 ? diet.daily30 : diet.daily7) ?? []
            return DesktopHealthTrendContext(
                kind: .diet,
                rangeDays: days,
                unit: "kcal",
                total: days == 30 ? diet.last30Calories : diet.last7Calories,
                average: days == 30 ? diet.last30AvgCalories : diet.last7AvgCalories,
                recordCount: days == 30 ? diet.last30Count : diet.last7Count,
                points: points.map { DesktopHealthTrendPoint(date: $0.date, value: $0.calories, count: $0.count) },
                latestRecord: latestRecord(matching: ["diet", "meal", "food"])
            )
        case .water:
            guard let water = recordsSummary.water else { return nil }
            let points = (days == 30 ? water.daily30 : water.daily7) ?? []
            return DesktopHealthTrendContext(
                kind: .water,
                rangeDays: days,
                unit: "ml",
                total: Double(days == 30 ? (water.last30TotalMl ?? 0) : (water.last7TotalMl ?? 0)),
                average: days == 30 ? water.last30AvgMl : water.last7AvgMl,
                recordCount: days == 30 ? water.last30Count : water.last7Count,
                points: points.map { DesktopHealthTrendPoint(date: $0.date, value: Double($0.totalMl), count: $0.count) },
                latestRecord: latestRecord(matching: ["water", "drink"])
            )
        case .supplements:
            guard let supplements = recordsSummary.supplements else { return nil }
            let points = (days == 30 ? supplements.daily30 : supplements.daily7) ?? []
            let count = days == 30 ? supplements.last30Count : supplements.last7Count
            return DesktopHealthTrendContext(
                kind: .supplements,
                rangeDays: days,
                unit: "次",
                total: count.map(Double.init),
                average: days == 30 ? supplements.last30AvgPerDay : supplements.last7AvgPerDay,
                recordCount: count,
                points: points.map { DesktopHealthTrendPoint(date: $0.date, value: Double($0.count), count: $0.count) },
                latestRecord: latestRecord(matching: ["supplement", "supplements"])
            )
        case .weight:
            guard let latestWeight = recordsSummary.latestWeight else { return nil }
            return DesktopHealthTrendContext(
                kind: .weight,
                rangeDays: days,
                unit: latestWeight.unit ?? "kg",
                points: [],
                latestRecord: latestWeight
            )
        case .bloodPressure:
            guard let latestBloodPressure = recordsSummary.latestBloodPressure else { return nil }
            return DesktopHealthTrendContext(
                kind: .bloodPressure,
                rangeDays: days,
                unit: latestBloodPressure.unit ?? "mmHg",
                points: [],
                latestRecord: latestBloodPressure
            )
        case .steps:
            guard let garmin = recordsSummary.latestGarmin, let steps = garmin.steps else { return nil }
            return DesktopHealthTrendContext(
                kind: .steps,
                rangeDays: days,
                unit: "步",
                total: Double(steps),
                points: [
                    DesktopHealthTrendPoint(date: garmin.recordDate ?? recordsSummary.date ?? "latest", value: Double(steps), count: nil)
                ]
            )
        }
    }

    private func latestRecord(matching keywords: [String]) -> DesktopRecordMetric? {
        viewModel.bootstrap?.recentRecordsSummary.recentRecords?.first { record in
            let type = record.type.lowercased()
            let title = record.title.lowercased()
            return keywords.contains { type.contains($0) || title.contains($0) }
        }
    }

    private func formatCompactNumber(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.numberStyle = .decimal
        formatter.usesGroupingSeparator = true
        formatter.minimumFractionDigits = 0
        formatter.maximumFractionDigits = value.rounded() == value ? 0 : 1
        return formatter.string(from: NSNumber(value: value)) ?? "\(value)"
    }

    private func dataGuidancePanel(_ summary: DesktopWorkspaceSummary) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Label(appText("Workspace Actions", appLanguageRaw), systemImage: "wand.and.stars")
                .font(.headline)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 10)], spacing: 10) {
                ForEach(summary.guidanceRows) { row in
                    guidanceActionButton(row, summary: summary)
                }
            }
            guidanceStatusView
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private func dataActionPanel(_ summary: DesktopWorkspaceSummary) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label(appText("Priority Actions", appLanguageRaw), systemImage: "checklist")
                    .font(.headline)
                Spacer()
                Text("\(summary.actionCards.count)")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
            }
            if summary.actionCards.isEmpty {
                Text(appText("No actions loaded yet.", appLanguageRaw))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 90, alignment: .center)
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: 10)], spacing: 10) {
                    ForEach(summary.actionCards.prefix(8)) { card in
                        WorkspaceActionCard(card: card, color: .teal, systemImage: "checkmark.seal.fill")
                    }
                }
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private func dataRecordsPanel(_ summary: DesktopWorkspaceSummary) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label(appText("Recent Health Records", appLanguageRaw), systemImage: "waveform.path.ecg")
                    .font(.headline)
                Spacer()
                Text("\(summary.recentRecords.count)")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
            }
            if summary.recentRecords.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "tray")
                        .font(.system(size: 26))
                        .foregroundStyle(.secondary)
                    Text(appText("No recent health records loaded.", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 180)
            } else {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(summary.recentRecords.prefix(8)) { record in
                        dataRecordRow(record)
                    }
                }
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private func dataRecordRow(_ record: DesktopRecordMetric) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: workspaceRecordIcon(record.type))
                    .foregroundStyle(workspaceRecordColor(record.type))
                    .frame(width: 30, height: 30)
                    .background(workspaceRecordColor(record.type).opacity(0.13), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                VStack(alignment: .leading, spacing: 3) {
                    Text(record.title)
                        .font(.callout.weight(.semibold))
                        .lineLimit(1)
                    Text(record.recordDate ?? appText("No record", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text(record.displayValue)
                    .font(.callout.weight(.bold).monospacedDigit())
                    .lineLimit(1)
            }

            contextActionBar(
                item: DesktopWorkspaceContextFactory.contextItem(for: record),
                prompt: DesktopWorkspaceContextFactory.prompt(for: record)
            )
        }
        .padding(11)
        .background(Color.secondary.opacity(0.065), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    @ViewBuilder
    private func geneticsWorkspaceDetails(_ summary: DesktopWorkspaceSummary) -> some View {
            SectionPanel(title: appText("Genetic Risk Summary", appLanguageRaw), systemImage: "dna") {
                if let genomic = summary.genomicSummary, genomic.recordCount > 0 {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 10) {
                            if let provider = genomic.provider {
                                Text(provider)
                            }
                            if let testDate = genomic.testDate {
                                Text(testDate)
                            }
                            if let latestImport = genomic.latestImport?.rawRecordCount {
                                Text("\(latestImport) raw")
                            }
                        }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)

                        if let latestImport = genomic.latestImport {
                            VStack(alignment: .leading, spacing: 10) {
                                HStack(spacing: 8) {
                                    Text(appText("Genetic Import Coverage", appLanguageRaw))
                                        .font(.callout.weight(.semibold))
                                    Spacer(minLength: 0)
                                    Text(appText(GenomicImportPresentation.statusLabel(for: latestImport), appLanguageRaw))
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(genomicImportStatusColor(GenomicImportPresentation.phase(for: latestImport)))
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(
                                            genomicImportStatusColor(GenomicImportPresentation.phase(for: latestImport)).opacity(0.12),
                                            in: Capsule()
                                        )
                                }
                                if let detail = GenomicImportPresentation.detailText(for: latestImport) {
                                    Text(detail)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 8)], spacing: 8) {
                                    coverageMetric(title: "Raw", value: latestImport.rawRecordCount.map { "\($0)" } ?? "—", color: .indigo)
                                    coverageMetric(title: "Coverage", value: latestImport.coveragePct.map { "\($0)%" } ?? "—", color: .blue)
                                    coverageMetric(title: "Matched", value: latestImport.matchedCount.map { "\($0)" } ?? "—", color: .teal)
                                    coverageMetric(title: "Unmapped", value: latestImport.unmappedCount.map { "\($0)" } ?? "—", color: .orange)
                                    coverageMetric(title: "Missing", value: latestImport.missingCount.map { "\($0)" } ?? "—", color: .red)
                                }
                            }
                            .padding(12)
                            .background(Color.indigo.opacity(0.07), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        }

                        if !genomic.profileSummaries.isEmpty {
                            VStack(alignment: .leading, spacing: 10) {
                                Text(appText("Genetic Profiles", appLanguageRaw))
                                    .font(.callout.weight(.semibold))
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 8)], spacing: 8) {
                                    ForEach(genomic.profileSummaries.prefix(6)) { profile in
                                        HStack(alignment: .top, spacing: 10) {
                                            Image(systemName: profile.isActive ? "checkmark.seal.fill" : "doc.text.fill")
                                                .foregroundStyle(profile.isActive ? .teal : .secondary)
                                            VStack(alignment: .leading, spacing: 4) {
                                                Text(profile.provider ?? "Profile #\(profile.profileID)")
                                                    .font(.callout.weight(.semibold))
                                                    .lineLimit(1)
                                                Text([profile.testDate, profile.reportID].compactMap { $0 }.joined(separator: " · "))
                                                    .font(.caption2)
                                                    .foregroundStyle(.secondary)
                                                    .lineLimit(1)
                                            }
                                            Spacer(minLength: 0)
                                            Text("\(profile.recordCount)")
                                                .font(.callout.weight(.bold).monospacedDigit())
                                        }
                                        .padding(10)
                                        .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                                    }
                                }
                            }
                        }

                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 10)], spacing: 10) {
                            ForEach(genomic.topCategories) { category in
                                VStack(alignment: .leading, spacing: 10) {
                                    HStack {
                                        Text(localizedGenomicCategory(category.category))
                                            .font(.callout.weight(.semibold))
                                            .lineLimit(1)
                                        Spacer()
                                    }
                                    Text("\(category.count) \(appText("variants", appLanguageRaw))")
                                        .font(.title3.weight(.bold).monospacedDigit())
                                    Text("\(appText("High", appLanguageRaw)) \(category.highRiskCount) · \(appText("Medium", appLanguageRaw)) \(category.mediumRiskCount)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    HStack(spacing: 8) {
                                        Button {
                                            selectedGenomicDetail = .category(category)
                                        } label: {
                                            Label(appText("Detail", appLanguageRaw), systemImage: "doc.text.magnifyingglass")
                                        }
                                        .buttonStyle(.bordered)
                                        .controlSize(.small)
                                        if let onAskAgent {
                                            Button {
                                                onAskAgent(genomicCategoryPrompt(category), genomicCategoryContext(category))
                                            } label: {
                                                Label(appText("Ask", appLanguageRaw), systemImage: "sparkles")
                                            }
                                            .buttonStyle(.borderedProminent)
                                            .controlSize(.small)
                                        }
                                        if let onAddContext {
                                            Button {
                                                onAddContext(genomicCategoryContext(category))
                                            } label: {
                                                Label(appText("Add", appLanguageRaw), systemImage: "tray.and.arrow.down")
                                            }
                                            .buttonStyle(.bordered)
                                            .controlSize(.small)
                                        }
                                    }
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(12)
                                .background(Color.purple.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                            }
                        }
                    }
                } else {
                    Text(appText("No genetic variants loaded yet.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                }
            }

            SectionPanel(title: appText("Top Genetic Findings", appLanguageRaw), systemImage: "exclamationmark.triangle.fill") {
                if let findings = summary.genomicSummary?.topFindings, !findings.isEmpty {
                    let findingGroups = GenomicFindingPresentation.groups(from: findings)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: 10)], spacing: 10) {
                        ForEach(findingGroups.prefix(8)) { group in
                            let finding = group.primary
                            VStack(alignment: .leading, spacing: 10) {
                                HStack(alignment: .top) {
                                    Text(group.title)
                                        .font(.callout.weight(.semibold))
                                        .lineLimit(2)
                                    Spacer(minLength: 8)
                                    Text(GenomicFindingPresentation.badgeLabel(for: finding))
                                        .font(.caption2.weight(.bold))
                                        .padding(.horizontal, 7)
                                        .padding(.vertical, 4)
                                        .background(geneticRiskColor(finding.riskLevel).opacity(0.16), in: Capsule())
                                        .foregroundStyle(geneticRiskColor(finding.riskLevel))
                                }
                                HStack(spacing: 8) {
                                    if group.variantCount > 1 {
                                        Text("\(group.variantCount) \(appText("variants", appLanguageRaw))")
                                            .foregroundStyle(.primary)
                                    }
                                    if !group.rsidSummary.isEmpty {
                                        Text(group.rsidSummary)
                                    }
                                    if group.variantCount == 1, let genotype = finding.genotype {
                                        Text(genotype)
                                    }
                                    if let evidence = finding.evidenceLevel {
                                        Text(evidence)
                                    }
                                }
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                if let description = finding.description, !description.isEmpty {
                                    Text(description)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(2)
                                }
                                if let boundary = GenomicFindingPresentation.boundaryText(for: finding) {
                                    Text(appText(boundary, appLanguageRaw))
                                        .font(.caption2)
                                        .foregroundStyle(.orange)
                                        .lineLimit(2)
                                }
                                HStack(spacing: 8) {
                                    Button {
                                        selectedGenomicDetail = .finding(finding)
                                    } label: {
                                        Label(appText("View Detail", appLanguageRaw), systemImage: "doc.text.magnifyingglass")
                                    }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                                    if let onAskAgent {
                                        Button {
                                            onAskAgent(genomicFindingPrompt(finding), genomicFindingContext(finding))
                                        } label: {
                                            Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                                        }
                                        .buttonStyle(.borderedProminent)
                                        .controlSize(.small)
                                    }
                                    if let onAddContext {
                                        Button {
                                            onAddContext(genomicFindingContext(finding))
                                        } label: {
                                            Label(appText("Add Context", appLanguageRaw), systemImage: "tray.and.arrow.down")
                                        }
                                        .buttonStyle(.bordered)
                                        .controlSize(.small)
                                    }
                                    Spacer(minLength: 0)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                            .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        }
                    }
                } else {
                    Text(appText("No high-signal genetic findings loaded.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                }
            }
    }

    @ViewBuilder
    private func knowledgeWorkspaceDetails(_ summary: DesktopWorkspaceSummary) -> some View {
            SectionPanel(title: appText("Knowledge Coverage", appLanguageRaw), systemImage: "books.vertical.fill") {
                if let knowledge = summary.knowledgeSummary, knowledge.documentCount > 0 {
                    VStack(alignment: .leading, spacing: 14) {
                        if let localSource = resolvedLocalKnowledgeSource(knowledge.localSourceSummary) {
                            localKnowledgeSourcePanel(localSource)
                        }

                        HStack(alignment: .top, spacing: 12) {
                            if !knowledge.docTypeCounts.isEmpty {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(appText("Document Types", appLanguageRaw))
                                        .font(.callout.weight(.semibold))
                                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 8)], spacing: 8) {
                                        ForEach(knowledge.docTypeCounts) { item in
                                            coverageMetric(title: item.level, value: "\(item.count)", color: .blue)
                                        }
                                    }
                                }
                            }
                            if !knowledge.entityTypeCounts.isEmpty {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(appText("Entity Coverage", appLanguageRaw))
                                        .font(.callout.weight(.semibold))
                                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 8)], spacing: 8) {
                                        ForEach(knowledge.entityTypeCounts) { item in
                                            coverageMetric(title: item.level, value: "\(item.count)", color: .teal)
                                        }
                                    }
                                }
                            }
                        }

                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 10)], spacing: 10) {
                            ForEach(knowledge.sourceCounts.prefix(8)) { source in
                                HStack {
                                    Text(source.source)
                                        .font(.callout.weight(.semibold))
                                        .lineLimit(1)
                                    Spacer()
                                    Text("\(source.count)")
                                        .font(.callout.weight(.bold).monospacedDigit())
                                }
                                .padding(12)
                                .background(Color.teal.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                            }
                        }
                        if !knowledge.evidenceLevelCounts.isEmpty {
                            HStack(spacing: 8) {
                                ForEach(knowledge.evidenceLevelCounts) { item in
                                    Text("\(item.level): \(item.count)")
                                        .font(.caption.weight(.semibold))
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 6)
                                        .background(Color.indigo.opacity(0.12), in: Capsule())
                                }
                            }
                        }
                    }
                } else {
                    Text(appText("No knowledge documents loaded yet.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                }
            }

            SectionPanel(title: appText("Recent Knowledge Documents", appLanguageRaw), systemImage: "doc.text.magnifyingglass") {
                if let documents = summary.knowledgeSummary?.recentDocuments, !documents.isEmpty {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(documents.prefix(8)) { document in
                            VStack(alignment: .leading, spacing: 10) {
                                HStack(alignment: .top, spacing: 10) {
                                    Image(systemName: document.docType == "claim" ? "checkmark.seal.fill" : "doc.text.fill")
                                        .foregroundStyle(document.docType == "claim" ? .teal : .blue)
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(document.title ?? document.docID)
                                            .font(.callout.weight(.semibold))
                                            .lineLimit(1)
                                        Text(document.summary ?? document.docID)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                            .lineLimit(2)
                                        HStack(spacing: 8) {
                                            Text(document.docType)
                                            if let level = document.evidenceLevel {
                                                Text("Level \(level)")
                                            }
                                            if let firstSource = document.sources.first {
                                                Text(firstSource)
                                            }
                                        }
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                    }
                                    Spacer(minLength: 0)
                                }

                                HStack(spacing: 8) {
                                    Button {
                                        selectedKnowledgeDocument = document
                                    } label: {
                                        Label(appText("View Detail", appLanguageRaw), systemImage: "doc.text.magnifyingglass")
                                    }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)

                                    Spacer(minLength: 0)
                                }

                                contextActionBar(
                                    item: DesktopWorkspaceContextFactory.contextItem(for: document),
                                    prompt: DesktopWorkspaceContextFactory.prompt(for: document)
                                )
                            }
                            .padding(.vertical, 6)
                            if document.id != documents.prefix(8).last?.id {
                                Divider()
                            }
                        }
                    }
                } else {
                    Text(appText("No knowledge documents loaded yet.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                }
            }
    }

    @ViewBuilder
    private func knowledgeWorkspaceSummary(_ summary: DesktopWorkspaceSummary) -> some View {
        if let knowledge = summary.knowledgeSummary, knowledge.documentCount > 0 {
            let documents = KnowledgeWorkspacePresentation.filteredDocuments(
                knowledge.recentDocuments,
                query: knowledgeSearchText,
                filter: knowledgeDocumentFilter
            )

            VStack(alignment: .leading, spacing: 18) {
                SectionPanel(title: appText("Knowledge Workbench", appLanguageRaw), systemImage: "books.vertical.fill") {
                    VStack(alignment: .leading, spacing: 16) {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 12)], spacing: 12) {
                            ForEach(summary.metrics) { metric in
                                WorkspaceMetricCard(metric: metric)
                            }
                        }

                        if let localSource = resolvedLocalKnowledgeSource(knowledge.localSourceSummary) {
                            localKnowledgeSourcePanel(localSource)
                        }

                        HStack(spacing: 10) {
                            Label(appText("Search", appLanguageRaw), systemImage: "magnifyingglass")
                                .font(.callout.weight(.semibold))
                                .foregroundStyle(.secondary)
                            TextField(appText("Search knowledge documents", appLanguageRaw), text: $knowledgeSearchText)
                                .textFieldStyle(.roundedBorder)
                            Picker(appText("Type", appLanguageRaw), selection: $knowledgeDocumentFilter) {
                                ForEach(KnowledgeDocumentFilter.allCases) { filter in
                                    Text(knowledgeFilterTitle(filter)).tag(filter)
                                }
                            }
                            .pickerStyle(.segmented)
                            .frame(width: 330)
                        }
                    }
                }

                SectionPanel(title: appText("Knowledge Documents", appLanguageRaw), systemImage: "doc.text.magnifyingglass") {
                    if documents.isEmpty {
                        ContentUnavailableView(
                            appText("No matching knowledge documents", appLanguageRaw),
                            systemImage: "doc.text.magnifyingglass",
                            description: Text(appText("Try another keyword or document type.", appLanguageRaw))
                        )
                        .frame(maxWidth: .infinity, minHeight: 180)
                    } else {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 360), spacing: 12)], spacing: 12) {
                            ForEach(documents.prefix(12)) { document in
                                knowledgeDocumentCard(document)
                            }
                        }
                    }
                }

                HStack(alignment: .top, spacing: 16) {
                    knowledgeCoveragePanel(
                        title: appText("Document Types", appLanguageRaw),
                        systemImage: "doc.on.doc.fill",
                        color: .blue,
                        counts: knowledge.docTypeCounts
                    )
                    knowledgeCoveragePanel(
                        title: appText("Entity Coverage", appLanguageRaw),
                        systemImage: "point.3.connected.trianglepath.dotted",
                        color: .teal,
                        counts: knowledge.entityTypeCounts
                    )
                }

                if !knowledge.sourceCounts.isEmpty || !knowledge.evidenceLevelCounts.isEmpty {
                    SectionPanel(title: appText("Source Coverage", appLanguageRaw), systemImage: "link.circle.fill") {
                        VStack(alignment: .leading, spacing: 14) {
                            if !knowledge.sourceCounts.isEmpty {
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 10)], spacing: 10) {
                                    ForEach(knowledge.sourceCounts.prefix(10)) { source in
                                        HStack {
                                            Text(source.source)
                                                .font(.callout.weight(.semibold))
                                                .lineLimit(1)
                                                .truncationMode(.middle)
                                            Spacer()
                                            Text("\(source.count)")
                                                .font(.callout.weight(.bold).monospacedDigit())
                                        }
                                        .padding(12)
                                        .background(Color.teal.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                                    }
                                }
                            }
                            if !knowledge.evidenceLevelCounts.isEmpty {
                                HStack(spacing: 8) {
                                    ForEach(knowledge.evidenceLevelCounts) { item in
                                        knowledgePill("\(appText("Level", appLanguageRaw)) \(item.level): \(item.count)", color: .indigo)
                                    }
                                }
                            }
                        }
                    }
                }

                SectionPanel(title: appText("Workspace Actions", appLanguageRaw), systemImage: "wand.and.stars") {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 10)], spacing: 10) {
                        ForEach(summary.guidanceRows) { row in
                            guidanceActionButton(row, summary: summary)
                        }
                    }
                    guidanceStatusView
                }

                SectionPanel(title: appText("Priority Actions", appLanguageRaw), systemImage: "checklist") {
                    if summary.actionCards.isEmpty {
                        Text(appText("No actions loaded yet.", appLanguageRaw))
                            .foregroundStyle(.secondary)
                    } else {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 10)], spacing: 10) {
                            ForEach(summary.actionCards.prefix(6)) { card in
                                WorkspaceActionCard(
                                    card: card,
                                    color: .teal,
                                    systemImage: "books.vertical.fill"
                                )
                            }
                        }
                    }
                }
            }
        } else {
            SectionPanel(title: appText("Knowledge Workbench", appLanguageRaw), systemImage: "books.vertical.fill") {
                ContentUnavailableView(
                    appText("No knowledge documents loaded yet.", appLanguageRaw),
                    systemImage: "books.vertical"
                )
                .frame(maxWidth: .infinity, minHeight: 220)
            }
        }
    }

    private func knowledgeDocumentCard(_ document: KnowledgeDocumentSummary) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: document.docType == "claim" ? "checkmark.seal.fill" : "doc.text.fill")
                    .foregroundStyle(document.docType == "claim" ? .teal : .blue)
                    .frame(width: 22)
                VStack(alignment: .leading, spacing: 5) {
                    Text(document.title ?? document.docID)
                        .font(.headline)
                        .lineLimit(2)
                    Text(document.summary ?? document.docID)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                }
                Spacer(minLength: 0)
                knowledgePill(appText(document.docType, appLanguageRaw), color: .blue)
            }

            HStack(spacing: 8) {
                if let level = document.evidenceLevel {
                    knowledgePill("\(appText("Level", appLanguageRaw)) \(level)", color: .indigo)
                }
                if let confidence = document.confidence {
                    knowledgePill("\(appText("Confidence", appLanguageRaw)) \(Int(confidence * 100))%", color: .teal)
                }
                if let firstSource = document.sources.first {
                    knowledgePill(firstSource, color: .secondary)
                }
            }

            HStack(spacing: 8) {
                Button {
                    selectedKnowledgeDocument = document
                } label: {
                    Label(appText("View Detail", appLanguageRaw), systemImage: "doc.text.magnifyingglass")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)

                Spacer(minLength: 0)

                if let onAddContext {
                    Button {
                        onAddContext(DesktopWorkspaceContextFactory.contextItem(for: document))
                    } label: {
                        Label(appText("Add Context", appLanguageRaw), systemImage: "tray.and.arrow.down")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
                if let onAskAgent {
                    Button {
                        onAskAgent(
                            DesktopWorkspaceContextFactory.prompt(for: document),
                            DesktopWorkspaceContextFactory.contextItem(for: document)
                        )
                    } label: {
                        Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 170, alignment: .topLeading)
        .background(Color(nsColor: .controlBackgroundColor).opacity(0.72), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func knowledgeCoveragePanel(
        title: String,
        systemImage: String,
        color: Color,
        counts: [KnowledgeCount]
    ) -> some View {
        SectionPanel(title: title, systemImage: systemImage) {
            if counts.isEmpty {
                Text(appText("No data loaded yet.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 130), spacing: 8)], spacing: 8) {
                    ForEach(counts) { item in
                        coverageMetric(title: item.level, value: "\(item.count)", color: color)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .top)
    }

    private func knowledgePill(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .lineLimit(1)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(color.opacity(0.12), in: Capsule())
    }

    private func knowledgeFilterTitle(_ filter: KnowledgeDocumentFilter) -> String {
        switch filter {
        case .all:
            appText("All", appLanguageRaw)
        case .claims:
            appText("Claims", appLanguageRaw)
        case .articles:
            appText("Articles", appLanguageRaw)
        case .entities:
            appText("Entities", appLanguageRaw)
        }
    }

    @ViewBuilder
    private func workspaceSideSections(_ summary: DesktopWorkspaceSummary) -> some View {
        SectionPanel(title: appText("Focus Domains", appLanguageRaw), systemImage: "scope") {
            if summary.focusDomains.isEmpty {
                Text(appText("No focus domains loaded.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            } else {
                HStack(spacing: 8) {
                    ForEach(summary.focusDomains, id: \.self) { domain in
                        Text(domain)
                            .font(.caption.bold())
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(Color.accentColor.opacity(0.12), in: Capsule())
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }

        SectionPanel(title: appText("Relevant Jobs", appLanguageRaw), systemImage: "clock.arrow.circlepath") {
            if summary.jobs.isEmpty {
                Text(appText("No active jobs for this workspace.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            } else {
                ForEach(summary.jobs) { job in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            VStack(alignment: .leading) {
                                Text(job.sourceName ?? job.jobType)
                                    .font(.headline)
                                Text("#\(job.id) \(job.jobType)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(job.status)
                            ProgressView(value: Double(job.progress), total: 100)
                                .frame(width: 140)
                        }
                        contextActionBar(
                            item: DesktopWorkspaceContextFactory.contextItem(for: job),
                            prompt: DesktopWorkspaceContextFactory.prompt(for: job)
                        )
                    }
                    Divider()
                }
            }
        }

        SectionPanel(title: appText("Recent Memory", appLanguageRaw), systemImage: "brain.head.profile") {
            if summary.recentMemory.isEmpty {
                Text(appText("No recent memory loaded.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            } else {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(summary.recentMemory.prefix(6)) { memory in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "brain.head.profile")
                                .foregroundStyle(.indigo)
                            Text(memory.objectValue)
                                .lineLimit(2)
                            Spacer(minLength: 0)
                        }
                        .padding(.vertical, 6)
                        if memory.id != summary.recentMemory.prefix(6).last?.id {
                            Divider()
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func contextActionBar(item: AgentContextItem, prompt: String) -> some View {
        if onAskAgent != nil || onAddContext != nil {
            HStack(spacing: 8) {
                if let onAddContext {
                    Button {
                        onAddContext(item)
                    } label: {
                        Label(appText("Add Context", appLanguageRaw), systemImage: "tray.and.arrow.down")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
                if let onAskAgent {
                    Button {
                        onAskAgent(prompt, item)
                    } label: {
                        Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                }
            }
        }
    }

    private func genomicFindingPrompt(_ finding: GenomicFindingSummary) -> String {
        """
        请基于我的真实基因上下文，分析这个基因发现，并给出可执行建议。注意：不要把基因风险当成诊断，不要直接给用药决定；请列出不确定性边界、需要结合的化验/症状/生活方式数据，以及未来 30 天可执行动作。

        基因发现：
        - 标题：\(finding.displayTitle)
        - 分类：\(finding.category ?? "unknown")
        - rsid：\(finding.rsid ?? "unknown")
        - 基因型：\(finding.genotype ?? "unknown")
        - 结果：\(finding.resultLabel ?? "unknown")
        - 风险等级：\(finding.riskLevel ?? "unknown")
        - 证据等级：\(finding.evidenceLevel ?? "unknown")
        - 临床边界：\(finding.clinicalStatus ?? "unknown")
        - 位点性质：\(finding.variantNature ?? "unknown")
        - 描述：\(finding.description ?? "无")
        """
    }

    private func localizedGenomicCategory(_ category: String) -> String {
        appText(category, appLanguageRaw)
    }

    private func genomicCategoryPrompt(_ category: GenomicCategorySummary) -> String {
        let localizedCategory = localizedGenomicCategory(category.category)
        return """
        请基于我的真实基因报告，围绕 \(localizedCategory) 这个分类做一次风险分层和行动建议。不要把基因结果当成诊断；请按优先级列出需要结合的数据、可执行生活方式动作、复查指标和不确定性边界。

        分类摘要：
        - 分类：\(localizedCategory)
        - 原始分类键：\(category.category)
        - 位点数：\(category.count)
        - 高风险：\(category.highRiskCount)
        - 中风险：\(category.mediumRiskCount)
        """
    }

    private func genomicFindingContext(_ finding: GenomicFindingSummary) -> AgentContextItem {
        AgentContextItem(
            sourceID: "genomic_finding:\(finding.id)",
            sourceKind: "genomic_finding",
            title: finding.displayTitle,
            summary: [
                finding.rsid,
                finding.genotype,
                finding.riskLevel,
                finding.evidenceLevel,
                finding.clinicalStatus,
                finding.description
            ].compactMap { $0 }.joined(separator: " · "),
            payload: [
                "id": "\(finding.id)",
                "gene_name": finding.geneName,
                "variant_name": finding.variantName ?? "",
                "rsid": finding.rsid ?? "",
                "genotype": finding.genotype ?? "",
                "result_label": finding.resultLabel ?? "",
                "risk_level": finding.riskLevel ?? "",
                "evidence_level": finding.evidenceLevel ?? "",
                "clinical_status": finding.clinicalStatus ?? "",
                "category": finding.category ?? "",
                "variant_nature": finding.variantNature ?? ""
            ]
        )
    }

    private func genomicCategoryContext(_ category: GenomicCategorySummary) -> AgentContextItem {
        AgentContextItem(
            sourceID: "genomic_category:\(category.category)",
            sourceKind: "genomic_category",
            title: localizedGenomicCategory(category.category),
            summary: "\(category.count) \(appText("variants", appLanguageRaw)) · \(appText("High", appLanguageRaw)) \(category.highRiskCount) · \(appText("Medium", appLanguageRaw)) \(category.mediumRiskCount)",
            payload: [
                "category": category.category,
                "display_category": localizedGenomicCategory(category.category),
                "count": "\(category.count)",
                "high_risk_count": "\(category.highRiskCount)",
                "medium_risk_count": "\(category.mediumRiskCount)"
            ]
        )
    }

    private func workspaceRecordIcon(_ type: String) -> String {
        switch type {
        case "diet": "fork.knife"
        case "water": "drop.fill"
        case "weight": "scalemass.fill"
        case "blood_pressure": "heart.text.square.fill"
        default: "doc.text.fill"
        }
    }

    private func workspaceRecordColor(_ type: String) -> Color {
        switch type {
        case "diet": .orange
        case "water": .cyan
        case "weight": .green
        case "blood_pressure": .pink
        default: .secondary
        }
    }

    private func coverageMetric(title: String, value: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(appText(title, appLanguageRaw))
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Text(value)
                .font(.callout.weight(.bold).monospacedDigit())
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
    }

    private func genomicImportStatusColor(_ phase: GenomicImportPhase) -> Color {
        switch phase {
        case .pending, .running:
            return .orange
        case .complete:
            return .teal
        case .failed:
            return .red
        case .unknown:
            return .secondary
        }
    }

    private func localKnowledgeSourcePanel(_ source: KnowledgeLocalSourceSummary) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: source.exists ? "externaldrive.connected.to.line.below.fill" : "externaldrive.badge.questionmark")
                    .foregroundStyle(source.exists ? .teal : .orange)
                VStack(alignment: .leading, spacing: 4) {
                    Text(appText("Local LLM Wiki Source", appLanguageRaw))
                        .font(.callout.weight(.semibold))
                    Text(source.sourceRoot)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .textSelection(.enabled)
                }
                Spacer(minLength: 0)
                Text(appText(source.exists ? "Connected" : "Not Found", appLanguageRaw))
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background((source.exists ? Color.teal : Color.orange).opacity(0.12), in: Capsule())
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), spacing: 8)], spacing: 8) {
                coverageMetric(title: "Wiki Markdown", value: "\(source.wikiMarkdownCount)", color: .teal)
                coverageMetric(title: "Artifacts JSON", value: "\(source.artifactJSONCount)", color: .cyan)
                coverageMetric(title: "Raw Sources", value: "\(source.rawSourceCount)", color: .blue)
                coverageMetric(title: "Linked KB Docs", value: "\(source.linkedDocumentCount)", color: .purple)
            }

            HStack(spacing: 8) {
                if let pipeline = source.bridgeManifest?.pipeline {
                    Text(pipeline)
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color.secondary.opacity(0.10), in: Capsule())
                }
                if let compiledAt = source.bridgeManifest?.compiledAt {
                    Text("\(appText("Compiled", appLanguageRaw)): \(compiledAt)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            if !source.originCounts.isEmpty {
                HStack(spacing: 8) {
                    ForEach(source.originCounts) { origin in
                        Text("\(origin.origin): \(origin.count)")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(Color.indigo.opacity(0.12), in: Capsule())
                    }
                }
            }
        }
        .padding(12)
        .background(Color.teal.opacity(0.06), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func resolvedLocalKnowledgeSource(_ apiSource: KnowledgeLocalSourceSummary?) -> KnowledgeLocalSourceSummary? {
        let root = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("work/personal/down-dedao", isDirectory: true)
        guard FileManager.default.fileExists(atPath: root.path) else {
            return apiSource
        }
        let wikiRoot = root.appendingPathComponent("wiki", isDirectory: true)
        let artifactRoot = root.appendingPathComponent("artifacts", isDirectory: true)
        let rawRoot = root.appendingPathComponent("raw", isDirectory: true)
        return KnowledgeLocalSourceSummary(
            sourceRoot: root.path,
            exists: true,
            wikiExists: FileManager.default.fileExists(atPath: wikiRoot.path),
            artifactsExists: FileManager.default.fileExists(atPath: artifactRoot.path),
            wikiMarkdownCount: countLocalFiles(in: wikiRoot, pathExtension: "md"),
            artifactJSONCount: countLocalFiles(in: artifactRoot, pathExtension: "json"),
            rawSourceCount: countTopLevelItems(in: rawRoot),
            linkedDocumentCount: apiSource?.linkedDocumentCount ?? 0,
            originCounts: apiSource?.originCounts ?? [],
            bridgeManifest: apiSource?.bridgeManifest ?? localBridgeManifest(in: artifactRoot)
        )
    }

    private func localBridgeManifest(in artifactRoot: URL) -> KnowledgeBridgeManifest? {
        let manifestURL = artifactRoot.appendingPathComponent("manifest.json")
        guard
            let data = try? Data(contentsOf: manifestURL),
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return nil
        }
        let bridge = json["down_dedao_wiki"] as? [String: Any]
        return KnowledgeBridgeManifest(
            pipeline: bridge?["pipeline"] as? String ?? json["pipeline"] as? String,
            sourceRoot: bridge?["source_root"] as? String ?? json["source_root"] as? String,
            compiledAt: bridge?["compiled_at"] as? String ?? json["compiled_at"] as? String
        )
    }

    private func countLocalFiles(in root: URL, pathExtension: String) -> Int {
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else {
            return 0
        }
        return enumerator.compactMap { $0 as? URL }.filter { url in
            guard
                url.pathExtension.lowercased() == pathExtension,
                let values = try? url.resourceValues(forKeys: [.isRegularFileKey])
            else {
                return false
            }
            return values.isRegularFile == true
        }.count
    }

    private func countTopLevelItems(in root: URL) -> Int {
        guard let items = try? FileManager.default.contentsOfDirectory(
            at: root,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) else {
            return 0
        }
        return items.count
    }

    private func geneticRiskColor(_ riskLevel: String?) -> Color {
        switch riskLevel?.lowercased() {
        case "high": .red
        case "medium": .orange
        case "low": .blue
        default: .secondary
        }
    }
}

private struct WorkspaceMetricCard: View {
    let metric: DesktopWorkspaceMetric
    var showsDisclosure = false
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: icon)
                    .font(.headline)
                    .foregroundStyle(color)
                    .frame(width: 30, height: 30)
                    .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                Spacer()
                if showsDisclosure {
                    Image(systemName: "chevron.right.circle.fill")
                        .font(.callout)
                        .foregroundStyle(color.opacity(0.9))
                }
            }
            Text(appText(metric.title, appLanguageRaw))
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(metric.value)
                .font(.title2.weight(.bold).monospacedDigit())
                .lineLimit(1)
                .minimumScaleFactor(0.72)
        }
        .frame(maxWidth: .infinity, minHeight: 118, alignment: .topLeading)
        .padding(14)
        .background(color.opacity(0.07), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(color.opacity(0.12), lineWidth: 1)
        )
    }

    private var icon: String {
        switch metric.id {
        case "diet_calories": "fork.knife"
        case "water_ml": "drop.fill"
        case "supplements": "pills.fill"
        case "latest_weight": "scalemass.fill"
        case "latest_bp": "heart.text.square.fill"
        case "steps": "figure.walk"
        case "gene_jobs": "dna"
        case "variants": "dna"
        case "all_variants": "number.square.fill"
        case "profiles": "rectangle.stack.fill"
        case "high_risk": "exclamationmark.triangle.fill"
        case "medium_risk": "exclamationmark.circle.fill"
        case "categories": "square.grid.2x2.fill"
        case "kb_jobs": "books.vertical.fill"
        case "documents": "doc.text.fill"
        case "claims": "checkmark.seal.fill"
        case "sources": "link"
        case "edges": "point.3.connected.trianglepath.dotted"
        case "entity_types": "tag.fill"
        case "running": "clock.arrow.circlepath"
        case "action_cards": "checkmark.seal.fill"
        case "focus_domains": "scope"
        case "memory": "brain.head.profile"
        default: "chart.bar.fill"
        }
    }

    private var color: Color {
        switch metric.id {
        case "diet_calories": .orange
        case "water_ml": .cyan
        case "supplements": .teal
        case "latest_weight": .green
        case "latest_bp": .pink
        case "steps": .blue
        case "gene_jobs": .purple
        case "variants": .purple
        case "all_variants": .indigo
        case "profiles": .blue
        case "high_risk": .red
        case "medium_risk": .orange
        case "categories": .indigo
        case "kb_jobs": .teal
        case "documents": .teal
        case "claims": .green
        case "sources": .blue
        case "edges": .indigo
        case "entity_types": .purple
        case "running": .blue
        case "action_cards": .orange
        case "focus_domains": .cyan
        case "memory": .indigo
        default: .accentColor
        }
    }
}

private struct GenomicFindingDetailSheet: View {
    let finding: GenomicFindingSummary
    let onAddContext: (() -> Void)?
    let onAskAgent: (() -> Void)?
    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(appText("Genetic Finding Detail", appLanguageRaw))
                        .font(.title2.bold())
                    Text(finding.displayTitle)
                        .font(.headline)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text(GenomicFindingPresentation.badgeLabel(for: finding))
                    .font(.caption.bold())
                    .padding(.horizontal, 9)
                    .padding(.vertical, 5)
                    .background(riskColor.opacity(0.16), in: Capsule())
                    .foregroundStyle(riskColor)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 10)], spacing: 10) {
                detailMetric("Gene", finding.geneName)
                detailMetric("rsid", finding.rsid ?? "—")
                detailMetric("Genotype", finding.genotype ?? "—")
                detailMetric("Category", finding.category ?? "—")
                detailMetric("Evidence", finding.evidenceLevel ?? "—")
                detailMetric("Nature", finding.variantNature ?? "—")
            }

            VStack(alignment: .leading, spacing: 8) {
                Text(appText("Interpretation", appLanguageRaw))
                    .font(.headline)
                Text(finding.description?.isEmpty == false ? finding.description! : appText("No description loaded.", appLanguageRaw))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text(appText("Clinical Boundary", appLanguageRaw))
                    .font(.headline)
                if let boundary = GenomicFindingPresentation.boundaryText(for: finding) {
                    Label(appText(boundary, appLanguageRaw), systemImage: "exclamationmark.triangle.fill")
                }
                Label(appText("Use genotype as a risk flag, not a diagnosis.", appLanguageRaw), systemImage: "exclamationmark.shield.fill")
                Label(appText("Confirm high-impact findings with clinical testing before medication or disease decisions.", appLanguageRaw), systemImage: "checkmark.seal")
                Label(appText("Ask Agent with recent labs, symptoms, supplements, and exercise before changing plans.", appLanguageRaw), systemImage: "sparkles")
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            .padding(12)
            .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))

            HStack {
                Text(appText("Genetic results are for risk stratification, not diagnosis or medication decisions.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Button(appText("Close", appLanguageRaw)) {
                    dismiss()
                }
                if let onAddContext {
                    Button {
                        onAddContext()
                    } label: {
                        Label(appText("Add Context", appLanguageRaw), systemImage: "tray.and.arrow.down")
                    }
                    .buttonStyle(.bordered)
                }
                if let onAskAgent {
                    Button {
                        onAskAgent()
                        dismiss()
                    } label: {
                        Label(appText("Ask Agent with Context", appLanguageRaw), systemImage: "sparkles")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        }
        .padding(24)
        .frame(width: 620)
    }

    private var riskColor: Color {
        switch finding.riskLevel?.lowercased() {
        case "high": .red
        case "medium": .orange
        case "low": .blue
        default: .secondary
        }
    }

    private func detailMetric(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(appText(title, appLanguageRaw))
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.callout.weight(.semibold))
                .lineLimit(2)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

private struct GenomicCategoryDetailSheet: View {
    let category: GenomicCategorySummary
    let findings: [GenomicFindingSummary]
    let onAddContext: (() -> Void)?
    let onAskAgent: (() -> Void)?
    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(appText("Genetic Category Detail", appLanguageRaw))
                        .font(.title2.bold())
                    Text(appText(category.category, appLanguageRaw))
                        .font(.headline)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button(appText("Close", appLanguageRaw)) {
                    dismiss()
                }
            }

            HStack(spacing: 10) {
                categoryMetric(appText("Variants", appLanguageRaw), "\(category.count)", .purple)
                categoryMetric(appText("High Risk", appLanguageRaw), "\(category.highRiskCount)", .red)
                categoryMetric(appText("Medium Risk", appLanguageRaw), "\(category.mediumRiskCount)", .orange)
            }

            VStack(alignment: .leading, spacing: 10) {
                Text(appText("Representative Findings", appLanguageRaw))
                    .font(.headline)
                if findings.isEmpty {
                    Text(appText("No representative findings loaded for this category.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(findings.prefix(6)) { finding in
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: "atom")
                                .foregroundStyle(.purple)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(finding.displayTitle)
                                    .font(.callout.weight(.semibold))
                                Text([finding.rsid, finding.genotype, finding.riskLevel].compactMap { $0 }.joined(separator: " · "))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                        }
                        .padding(10)
                        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    }
                }
            }

            HStack {
                Text(appText("Ask the Agent to combine this category with labs, symptoms, supplements, and exercise data.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                if let onAddContext {
                    Button {
                        onAddContext()
                    } label: {
                        Label(appText("Add Context", appLanguageRaw), systemImage: "tray.and.arrow.down")
                    }
                    .buttonStyle(.bordered)
                }
                if let onAskAgent {
                    Button {
                        onAskAgent()
                        dismiss()
                    } label: {
                        Label(appText("Ask Agent with Context", appLanguageRaw), systemImage: "sparkles")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        }
        .padding(24)
        .frame(width: 620)
    }

    private func categoryMetric(_ title: String, _ value: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(appText(title, appLanguageRaw))
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.weight(.bold).monospacedDigit())
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(color.opacity(0.10), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct KnowledgeDocumentDetailSheet: View {
    let document: KnowledgeDocumentSummary
    let onAddContext: (() -> Void)?
    let onAskAgent: (() -> Void)?
    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(appText("Knowledge Document Detail", appLanguageRaw))
                        .font(.title2.bold())
                    Text(document.title ?? document.docID)
                        .font(.headline)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                Spacer()
                Button(appText("Close", appLanguageRaw)) {
                    dismiss()
                }
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 10)], spacing: 10) {
                detailMetric("Document ID", document.docID)
                detailMetric("Type", document.docType)
                detailMetric("Evidence", document.evidenceLevel ?? "—")
                detailMetric("Confidence", document.confidence.map { "\($0)" } ?? "—")
            }

            VStack(alignment: .leading, spacing: 8) {
                Text(appText("Summary", appLanguageRaw))
                    .font(.headline)
                Text(document.summary?.isEmpty == false ? document.summary! : appText("No description loaded.", appLanguageRaw))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text(appText("Sources", appLanguageRaw))
                    .font(.headline)
                if document.sources.isEmpty {
                    Text(appText("No source refs loaded.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(document.sources, id: \.self) { source in
                            Label(source, systemImage: "link")
                                .font(.caption.weight(.semibold))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(Color.blue.opacity(0.11), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                        }
                    }
                }
            }

            HStack {
                Text(appText("Use this source with your own data before turning it into an action.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                if let onAddContext {
                    Button {
                        onAddContext()
                    } label: {
                        Label(appText("Add Context", appLanguageRaw), systemImage: "tray.and.arrow.down")
                    }
                    .buttonStyle(.bordered)
                }
                if let onAskAgent {
                    Button {
                        onAskAgent()
                        dismiss()
                    } label: {
                        Label(appText("Ask Agent with Context", appLanguageRaw), systemImage: "sparkles")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        }
        .padding(24)
        .frame(width: 620)
    }

    private func detailMetric(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(appText(title, appLanguageRaw))
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.callout.weight(.semibold))
                .lineLimit(2)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

private struct DataTrendCard: View {
    let title: String
    let value: String
    let color: Color
    let points: [Double]
    var showsDisclosure = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.callout.weight(.semibold))
                    Text(value)
                        .font(.caption.weight(.semibold).monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chart.bar.fill")
                    .foregroundStyle(color)
                if showsDisclosure {
                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                }
            }
            HStack(alignment: .bottom, spacing: 4) {
                ForEach(Array(normalizedPoints.enumerated()), id: \.offset) { _, point in
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(color.opacity(0.75))
                        .frame(height: 10 + CGFloat(point) * 38)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 52, maxHeight: 52, alignment: .bottom)
        }
        .padding(14)
        .background(color.opacity(0.075), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(color.opacity(0.13), lineWidth: 1)
        }
    }

    private var normalizedPoints: [Double] {
        let values = points.suffix(12)
        guard let maxValue = values.max(), maxValue > 0 else {
            return Array(repeating: 0.12, count: max(points.count, 7))
        }
        return values.map { max(0.08, $0 / maxValue) }
    }
}

private struct VitalSnapshotCard: View {
    let icon: String
    let color: Color
    let title: String
    let value: String
    let unit: String
    var showsDisclosure = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: icon)
                    .font(.headline)
                    .foregroundStyle(color)
                    .frame(width: 30, height: 30)
                    .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                Spacer()
                if showsDisclosure {
                    Image(systemName: "chevron.right.circle.fill")
                        .font(.callout)
                        .foregroundStyle(color.opacity(0.9))
                }
            }
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(value)
                    .font(.title2.weight(.bold).monospacedDigit())
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                if !unit.isEmpty {
                    Text(unit)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }
        }
        .frame(maxWidth: .infinity, minHeight: 104, alignment: .topLeading)
        .padding(14)
        .background(color.opacity(0.07), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(color.opacity(0.12), lineWidth: 1)
        )
    }
}

/// 最新一晚睡眠分期的横向堆叠条 (深睡/浅睡/REM/清醒) + 图例。
private struct SleepStagesBar: View {
    let stages: VitalsTrendPresentation.SleepStages
    let deepLabel: String
    let lightLabel: String
    let remLabel: String
    let awakeLabel: String

    private var segments: [(label: String, minutes: Int, color: Color)] {
        [
            (deepLabel, stages.deepMinutes, .indigo),
            (lightLabel, stages.lightMinutes, .blue),
            (remLabel, stages.remMinutes, .teal),
            (awakeLabel, stages.awakeMinutes, .orange)
        ].filter { $0.minutes > 0 }
    }

    private func durationLabel(_ minutes: Int) -> String {
        let h = minutes / 60
        let m = minutes % 60
        if h > 0 { return m > 0 ? "\(h)h \(m)m" : "\(h)h" }
        return "\(m)m"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            GeometryReader { geo in
                HStack(spacing: 2) {
                    ForEach(Array(segments.enumerated()), id: \.offset) { _, seg in
                        seg.color.opacity(0.85)
                            .frame(width: max(2, geo.size.width * CGFloat(seg.minutes) / CGFloat(max(stages.totalMinutes, 1))))
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
            }
            .frame(height: 16)

            HStack(spacing: 14) {
                ForEach(Array(segments.enumerated()), id: \.offset) { _, seg in
                    HStack(spacing: 5) {
                        Circle().fill(seg.color).frame(width: 8, height: 8)
                        Text(seg.label)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text(durationLabel(seg.minutes))
                            .font(.caption2.weight(.semibold).monospacedDigit())
                    }
                }
            }
        }
    }
}

/// 逐日睡眠分期堆叠柱状图 (深睡/浅睡/REM/清醒)，柱高按当天总睡眠时长归一化。
private struct SleepStageTrendChart: View {
    let days: [VitalsTrendPresentation.SleepStageDay]
    let deepLabel: String
    let lightLabel: String
    let remLabel: String
    let awakeLabel: String

    private let deepColor = Color.indigo
    private let lightColor = Color.blue
    private let remColor = Color.teal
    private let awakeColor = Color.orange

    private var maxTotal: Int { max(days.map(\.totalMinutes).max() ?? 1, 1) }

    private func avgHoursLabel() -> String {
        guard !days.isEmpty else { return "—" }
        let avgMin = Double(days.map(\.totalMinutes).reduce(0, +)) / Double(days.count)
        return String(format: "%.1fh", avgMin / 60.0)
    }

    private func monthDay(_ date: String) -> String {
        // "2026-05-30" → "05-30"
        let parts = date.split(separator: "-")
        return parts.count >= 3 ? "\(parts[1])-\(parts[2])" : date
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("\(deepLabel)/\(lightLabel)/\(remLabel)/\(awakeLabel) · \(avgHoursLabel())")
                .font(.caption.weight(.semibold).monospacedDigit())
                .foregroundStyle(.secondary)

            GeometryReader { geo in
                let spacing: CGFloat = days.count > 14 ? 2 : 4
                HStack(alignment: .bottom, spacing: spacing) {
                    ForEach(days) { day in
                        stackedBar(day, fullHeight: geo.size.height)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(height: 96)

            HStack {
                Text(days.first.map { monthDay($0.date) } ?? "")
                Spacer()
                Text(days.last.map { monthDay($0.date) } ?? "")
            }
            .font(.caption2.monospacedDigit())
            .foregroundStyle(.tertiary)

            HStack(spacing: 14) {
                legendDot(deepColor, deepLabel)
                legendDot(lightColor, lightLabel)
                legendDot(remColor, remLabel)
                legendDot(awakeColor, awakeLabel)
            }
        }
    }

    private func stackedBar(_ day: VitalsTrendPresentation.SleepStageDay, fullHeight: CGFloat) -> some View {
        let barHeight = fullHeight * CGFloat(day.totalMinutes) / CGFloat(maxTotal)
        func seg(_ minutes: Int) -> CGFloat {
            guard day.totalMinutes > 0 else { return 0 }
            return barHeight * CGFloat(minutes) / CGFloat(day.totalMinutes)
        }
        return VStack(spacing: 0) {
            // 顺序自上而下：清醒 → REM → 浅睡 → 深睡 (深睡贴底)
            Rectangle().fill(awakeColor.opacity(0.85)).frame(height: seg(day.awakeMinutes))
            Rectangle().fill(remColor.opacity(0.85)).frame(height: seg(day.remMinutes))
            Rectangle().fill(lightColor.opacity(0.85)).frame(height: seg(day.lightMinutes))
            Rectangle().fill(deepColor.opacity(0.9)).frame(height: seg(day.deepMinutes))
        }
        .frame(maxWidth: .infinity)
        .frame(height: barHeight, alignment: .bottom)
        .clipShape(RoundedRectangle(cornerRadius: 2, style: .continuous))
        .help("\(monthDay(day.date)) · \(String(format: "%.1fh", Double(day.totalMinutes) / 60.0))")
    }

    private func legendDot(_ color: Color, _ label: String) -> some View {
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
    }
}

private struct SpO2Sparkline: View {
    let values: [Double]

    private let yMin: Double = 80
    private let yMax: Double = 100

    var body: some View {
        GeometryReader { geo in
            ZStack {
                // Risk band: below 90% in light red
                let normalizedLow = 1 - normalize(90)
                Rectangle()
                    .fill(Color.red.opacity(0.06))
                    .frame(height: geo.size.height * (1 - normalizedLow))
                    .frame(maxHeight: .infinity, alignment: .bottom)

                // Reference line at 90%
                Path { p in
                    let y = geo.size.height * normalizedLow
                    p.move(to: CGPoint(x: 0, y: y))
                    p.addLine(to: CGPoint(x: geo.size.width, y: y))
                }
                .stroke(Color.red.opacity(0.35), style: StrokeStyle(lineWidth: 0.8, dash: [3, 3]))

                // SpO2 line
                Path { p in
                    guard !values.isEmpty else { return }
                    for (idx, value) in values.enumerated() {
                        let x = geo.size.width * CGFloat(idx) / CGFloat(max(values.count - 1, 1))
                        let y = geo.size.height * (1 - normalize(value))
                        if idx == 0 {
                            p.move(to: CGPoint(x: x, y: y))
                        } else {
                            p.addLine(to: CGPoint(x: x, y: y))
                        }
                    }
                }
                .stroke(Color.cyan, lineWidth: 1.4)

                // Y-axis labels
                VStack {
                    Text("100%")
                        .font(.system(size: 9).monospacedDigit())
                        .foregroundStyle(.tertiary)
                    Spacer()
                    Text("80%")
                        .font(.system(size: 9).monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                .frame(maxWidth: .infinity, alignment: .trailing)
                .padding(.trailing, 2)
            }
        }
    }

    private func normalize(_ value: Double) -> Double {
        let clamped = min(max(value, yMin), yMax)
        return (clamped - yMin) / (yMax - yMin)
    }
}

private struct MetricMiniSparkline: View {
    let values: [Double]
    let color: Color
    let yMin: Double
    let yMax: Double

    var body: some View {
        GeometryReader { geo in
            ZStack {
                if values.isEmpty {
                    Text("—")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    Path { p in
                        for (idx, value) in values.enumerated() {
                            let x = geo.size.width * CGFloat(idx) / CGFloat(max(values.count - 1, 1))
                            let y = geo.size.height * (1 - normalize(value))
                            if idx == 0 {
                                p.move(to: CGPoint(x: x, y: y))
                            } else {
                                p.addLine(to: CGPoint(x: x, y: y))
                            }
                        }
                    }
                    .stroke(color.opacity(0.85), lineWidth: 1.1)
                }
            }
        }
    }

    private func normalize(_ value: Double) -> Double {
        let clamped = min(max(value, yMin), yMax)
        let range = yMax - yMin
        if range <= 0 { return 0.5 }
        return (clamped - yMin) / range
    }
}

private struct SleepStageBand: View {
    let stages: [NocturnalSleepStage]

    var body: some View {
        GeometryReader { geo in
            let totalStart = stages.compactMap { $0.startMs }.min() ?? 0
            let totalEnd = stages.compactMap { $0.endMs }.max() ?? 0
            let span = max(Int64(1), totalEnd - totalStart)

            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(Color.secondary.opacity(0.08))

                ForEach(Array(stages.enumerated()), id: \.offset) { _, stage in
                    if let start = stage.startMs, let end = stage.endMs, end > start {
                        let x = CGFloat(start - totalStart) / CGFloat(span) * geo.size.width
                        let w = CGFloat(end - start) / CGFloat(span) * geo.size.width
                        RoundedRectangle(cornerRadius: 2, style: .continuous)
                            .fill(SleepStageBand.color(for: stage.level))
                            .frame(width: max(1, w), height: geo.size.height)
                            .offset(x: x)
                    }
                }
            }
        }
    }

    static func color(for level: String?) -> Color {
        switch (level ?? "").lowercased() {
        case "deep": return .indigo
        case "light": return .blue.opacity(0.7)
        case "rem": return .purple
        case "awake", "wake": return .orange
        default: return .gray.opacity(0.6)
        }
    }
}

private struct SleepStageLegend: View {
    let language: String

    var body: some View {
        HStack(spacing: 10) {
            legendItem(color: SleepStageBand.color(for: "deep"), label: appText("Deep", language))
            legendItem(color: SleepStageBand.color(for: "light"), label: appText("Light", language))
            legendItem(color: SleepStageBand.color(for: "rem"), label: appText("REM", language))
            legendItem(color: SleepStageBand.color(for: "awake"), label: appText("Awake", language))
            Spacer()
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
    }

    private func legendItem(color: Color, label: String) -> some View {
        HStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(color)
                .frame(width: 8, height: 8)
            Text(label)
        }
    }
}

private struct LabSeriesChart: View {
    let series: LabIndicatorSeries
    var interventions: [InterventionEvent] = []

    private struct PointEntry {
        let index: Int
        let date: String
        let value: Double
        let abnormal: Bool
    }

    private struct InterventionMark {
        let event: InterventionEvent
        let x: CGFloat
    }

    private struct Scale {
        let yMin: Double
        let yMax: Double
        let range: Double
        let leftAxisWidth: CGFloat
        let bottomAxisHeight: CGFloat
        let plotWidth: CGFloat
        let plotHeight: CGFloat
        let pointCount: Int

        func xPos(_ idx: Int) -> CGFloat {
            if pointCount <= 1 { return plotWidth / 2 + leftAxisWidth }
            return leftAxisWidth + plotWidth * CGFloat(idx) / CGFloat(pointCount - 1)
        }

        func yPos(_ value: Double) -> CGFloat {
            let safeRange = range == 0 ? 1 : range
            let normalized = (value - yMin) / safeRange
            return plotHeight * (1 - CGFloat(normalized))
        }
    }

    var body: some View {
        GeometryReader { geo in
            let entries: [PointEntry] = series.sortedData.enumerated().compactMap { idx, point in
                guard let v = point.value else { return nil }
                return PointEntry(index: idx, date: point.date, value: v, abnormal: point.isAbnormal == true)
            }
            let scale = makeScale(entries: entries, size: geo.size)
            let marks = mapInterventions(entries: entries, scale: scale)
            ZStack(alignment: .topLeading) {
                if entries.isEmpty {
                    Text("—")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    chartContent(entries: entries, scale: scale, marks: marks)
                }
            }
        }
    }

    private func makeScale(entries: [PointEntry], size: CGSize) -> Scale {
        let leftAxisWidth: CGFloat = 36
        let bottomAxisHeight: CGFloat = 18
        let plotWidth = max(size.width - leftAxisWidth - 8, 10)
        let plotHeight = max(size.height - bottomAxisHeight - 4, 10)

        if entries.isEmpty {
            return Scale(yMin: 0, yMax: 1, range: 1,
                         leftAxisWidth: leftAxisWidth, bottomAxisHeight: bottomAxisHeight,
                         plotWidth: plotWidth, plotHeight: plotHeight, pointCount: 0)
        }
        let values = entries.map { $0.value }
        let refLow = series.referenceLow
        let refHigh = series.referenceHigh
        let minRaw = ([values.min(), refLow].compactMap { $0 }).min() ?? 0
        let maxRaw = ([values.max(), refHigh].compactMap { $0 }).max() ?? 1
        let padding = max((maxRaw - minRaw) * 0.12, 0.5)
        let yMin = minRaw - padding
        let yMax = maxRaw + padding
        let range = max(yMax - yMin, 0.0001)
        return Scale(yMin: yMin, yMax: yMax, range: range,
                     leftAxisWidth: leftAxisWidth, bottomAxisHeight: bottomAxisHeight,
                     plotWidth: plotWidth, plotHeight: plotHeight, pointCount: entries.count)
    }

    @ViewBuilder
    private func chartContent(entries: [PointEntry], scale: Scale, marks: [InterventionMark]) -> some View {
        // Reference range band
        if let low = series.referenceLow, let high = series.referenceHigh, high > low {
            let yHigh = scale.yPos(high)
            let yLow = scale.yPos(low)
            Rectangle()
                .fill(Color.green.opacity(0.08))
                .frame(width: scale.plotWidth, height: max(yLow - yHigh, 1))
                .offset(x: scale.leftAxisWidth, y: yHigh)
        }

        // Intervention markers (dashed vertical lines) — render before reference axis lines so they sit underneath.
        ForEach(Array(marks.enumerated()), id: \.offset) { _, mark in
            let color: Color = mark.event.kind == .medication ? .orange : .teal
            Path { p in
                p.move(to: CGPoint(x: mark.x, y: 0))
                p.addLine(to: CGPoint(x: mark.x, y: scale.plotHeight))
            }
            .stroke(color.opacity(0.55), style: StrokeStyle(lineWidth: 1.0, dash: [2, 3]))
            Circle()
                .fill(color)
                .frame(width: 4, height: 4)
                .offset(x: mark.x - 2, y: -2)
                .help("\(mark.event.label) · \(mark.event.date)")
        }

        if let high = series.referenceHigh {
            Path { p in
                p.move(to: CGPoint(x: scale.leftAxisWidth, y: scale.yPos(high)))
                p.addLine(to: CGPoint(x: scale.leftAxisWidth + scale.plotWidth, y: scale.yPos(high)))
            }
            .stroke(Color.green.opacity(0.4), style: StrokeStyle(lineWidth: 0.6, dash: [3, 3]))
        }
        if let low = series.referenceLow {
            Path { p in
                p.move(to: CGPoint(x: scale.leftAxisWidth, y: scale.yPos(low)))
                p.addLine(to: CGPoint(x: scale.leftAxisWidth + scale.plotWidth, y: scale.yPos(low)))
            }
            .stroke(Color.green.opacity(0.4), style: StrokeStyle(lineWidth: 0.6, dash: [3, 3]))
        }

        Path { p in
            for entry in entries {
                let position = CGPoint(x: scale.xPos(entry.index), y: scale.yPos(entry.value))
                if entry.index == 0 {
                    p.move(to: position)
                } else {
                    p.addLine(to: position)
                }
            }
        }
        .stroke(Color.purple, lineWidth: 1.6)

        ForEach(entries, id: \.index) { entry in
            Circle()
                .fill(entry.abnormal ? Color.red : Color.purple)
                .frame(width: 6, height: 6)
                .offset(x: scale.xPos(entry.index) - 3, y: scale.yPos(entry.value) - 3)
        }

        VStack(alignment: .trailing, spacing: 0) {
            Text(LabSeriesChart.formatAxis(scale.yMax))
                .font(.system(size: 9).monospacedDigit())
                .foregroundStyle(.tertiary)
            Spacer()
            Text(LabSeriesChart.formatAxis(scale.yMin))
                .font(.system(size: 9).monospacedDigit())
                .foregroundStyle(.tertiary)
        }
        .frame(width: scale.leftAxisWidth - 4, height: scale.plotHeight, alignment: .trailing)

        if let first = entries.first, let last = entries.last {
            Text(LabSeriesChart.shortDate(first.date))
                .font(.system(size: 9).monospacedDigit())
                .foregroundStyle(.tertiary)
                .offset(x: scale.leftAxisWidth, y: scale.plotHeight + 2)
            Text(LabSeriesChart.shortDate(last.date))
                .font(.system(size: 9).monospacedDigit())
                .foregroundStyle(.tertiary)
                .frame(width: 60, alignment: .trailing)
                .offset(x: scale.leftAxisWidth + scale.plotWidth - 60, y: scale.plotHeight + 2)
        }
    }

    static func formatAxis(_ value: Double) -> String {
        if abs(value) >= 100 { return String(format: "%.0f", value) }
        if abs(value) >= 10 { return String(format: "%.1f", value) }
        return String(format: "%.2f", value)
    }

    static func shortDate(_ date: String) -> String {
        // "yyyy-MM-dd" → "yy/MM"
        let parts = date.split(separator: "-")
        if parts.count == 3 {
            let yearPart = String(parts[0])
            let yy = yearPart.count >= 2 ? String(yearPart.suffix(2)) : yearPart
            return "\(yy)/\(parts[1])"
        }
        return date
    }

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.calendar = Calendar(identifier: .gregorian)
        f.timeZone = TimeZone.current
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    /// Map intervention dates to absolute x-positions on the chart. Out-of-range events are dropped.
    private func mapInterventions(entries: [PointEntry], scale: Scale) -> [InterventionMark] {
        guard entries.count >= 2, !interventions.isEmpty else { return [] }
        let firstDate = entries.first!.date
        let lastDate = entries.last!.date
        let formatter = LabSeriesChart.dateFormatter
        guard let firstParsed = formatter.date(from: firstDate),
              let lastParsed = formatter.date(from: lastDate),
              lastParsed > firstParsed else { return [] }

        // Precompute each entry's day offset from the first visit for interpolation.
        let entryDays: [Double] = entries.map { entry in
            guard let parsed = formatter.date(from: entry.date) else { return 0 }
            return parsed.timeIntervalSince(firstParsed) / 86400.0
        }
        let totalDays = lastParsed.timeIntervalSince(firstParsed) / 86400.0
        guard totalDays > 0 else { return [] }

        return interventions.compactMap { event in
            guard let parsed = formatter.date(from: event.date) else { return nil }
            if parsed < firstParsed || parsed > lastParsed { return nil }
            let dayOffset = parsed.timeIntervalSince(firstParsed) / 86400.0
            // Find segment [i, i+1] where dayOffset falls; interpolate xPos linearly within it.
            var segIdx = 0
            for i in 0..<(entryDays.count - 1) {
                if dayOffset >= entryDays[i] && dayOffset <= entryDays[i + 1] {
                    segIdx = i
                    break
                }
                if i == entryDays.count - 2 { segIdx = i }
            }
            let lo = entryDays[segIdx]
            let hi = entryDays[segIdx + 1]
            let frac: CGFloat = hi > lo ? CGFloat((dayOffset - lo) / (hi - lo)) : 0
            let xLo = scale.xPos(segIdx)
            let xHi = scale.xPos(segIdx + 1)
            let x = xLo + frac * (xHi - xLo)
            return InterventionMark(event: event, x: x)
        }
    }
}

private struct HealthTrendDetailSheet: View {
    let context: DesktopHealthTrendContext
    let color: Color
    var onAddContext: (() -> Void)?
    var onAskAgent: (() -> Void)?
    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(appText("Trend Detail", appLanguageRaw))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(appText(context.title, appLanguageRaw))
                        .font(.title2.bold())
                    Text("\(context.rangeDays) \(appText("days", appLanguageRaw)) · \(context.unit)")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 132), spacing: 10)], spacing: 10) {
                trendSummaryTile(title: "Total", value: summaryValue(context.total))
                trendSummaryTile(title: "Average", value: summaryValue(context.average))
                trendSummaryTile(title: "Record Count", value: context.recordCount.map(String.init) ?? "—")
                trendSummaryTile(title: "Latest Record", value: context.latestRecordText ?? "—")
            }

            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Label(appText("Detailed Trend Chart", appLanguageRaw), systemImage: "chart.bar.xaxis")
                        .font(.headline)
                    Spacer()
                    Text(appText(context.rangeDays == 30 ? "30 days" : "7 days", appLanguageRaw))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
                HealthTrendBarChart(points: context.points, unit: context.unit, color: color)
            }
            .padding(14)
            .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 14, style: .continuous))

            VStack(alignment: .leading, spacing: 10) {
                Label(appText("Daily Points", appLanguageRaw), systemImage: "list.bullet.rectangle")
                    .font(.headline)
                if context.points.isEmpty {
                    Text(appText("No trend points loaded.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            ForEach(context.points.suffix(30)) { point in
                                HStack {
                                    Text(point.date)
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Text("\(formatTrendNumber(point.value)) \(context.unit)")
                                        .font(.callout.weight(.semibold).monospacedDigit())
                                    if let count = point.count {
                                        Text("(\(count))")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                .padding(.vertical, 7)
                                Divider()
                            }
                        }
                    }
                    .frame(maxHeight: 180)
                }
            }

            Spacer(minLength: 0)

            HStack {
                if let onAddContext {
                    Button(appText("Add Trend Context", appLanguageRaw)) {
                        onAddContext()
                    }
                }
                Spacer()
                if let onAskAgent {
                    Button {
                        onAskAgent()
                        dismiss()
                    } label: {
                        Label(appText("Ask Agent about Trend", appLanguageRaw), systemImage: "sparkles")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        }
        .padding(24)
        .frame(width: 720)
        .frame(minHeight: 620)
    }

    private func trendSummaryTile(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(appText(title, appLanguageRaw))
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.callout.weight(.semibold))
                .lineLimit(2)
                .minimumScaleFactor(0.78)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(11)
        .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func summaryValue(_ value: Double?) -> String {
        guard let value else { return "—" }
        return "\(formatTrendNumber(value)) \(context.unit)"
    }
}

private struct VitalTrendDetailSheet: View {
    let kind: VitalMetricKind
    let title: String
    let color: Color
    let initialRecords: [GarminDailyRecord]
    let initialRange: Int
    var client: GarminTrendClient?
    var onAddContext: ((VitalTrendDetail) -> Void)?
    var onAskAgent: ((VitalTrendDetail) -> Void)?

    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var rangeDays: Int
    @State private var records: [GarminDailyRecord]
    @State private var fetchedLimit: Int
    @State private var loading = false

    private static let rangeOptions = [7, 30, 90, 180]

    init(
        kind: VitalMetricKind,
        title: String,
        color: Color,
        initialRecords: [GarminDailyRecord],
        initialRange: Int,
        client: GarminTrendClient?,
        onAddContext: ((VitalTrendDetail) -> Void)? = nil,
        onAskAgent: ((VitalTrendDetail) -> Void)? = nil
    ) {
        self.kind = kind
        self.title = title
        self.color = color
        self.initialRecords = initialRecords
        self.initialRange = initialRange
        self.client = client
        self.onAddContext = onAddContext
        self.onAskAgent = onAskAgent
        _rangeDays = State(initialValue: initialRange)
        _records = State(initialValue: initialRecords)
        // 数据页按 30 天拉取，详情默认已有 30 天可用。
        _fetchedLimit = State(initialValue: max(initialRange, 30))
    }

    private var detail: VitalTrendDetail {
        VitalTrendDetail(kind: kind, rangeDays: rangeDays, records: records)
    }

    var body: some View {
        let detail = self.detail
        return VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(appText("Trend Detail", appLanguageRaw))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(title)
                        .font(.title2.bold())
                    Text("\(rangeDays) \(appText("days", appLanguageRaw))\(detail.unit.isEmpty ? "" : " · \(detail.unit)")")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button { dismiss() } label: {
                    Image(systemName: "xmark.circle.fill")
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
            }

            HStack(spacing: 10) {
                Picker(appText("Range", appLanguageRaw), selection: $rangeDays) {
                    ForEach(Self.rangeOptions, id: \.self) { days in
                        Text("\(days)\(appText("d", appLanguageRaw))").tag(days)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 280)
                if loading {
                    ProgressView().controlSize(.small)
                }
                Spacer()
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 132), spacing: 10)], spacing: 10) {
                trendSummaryTile(title: "Average", value: summaryValue(detail.average))
                trendSummaryTile(title: "Min", value: summaryValue(detail.minValue))
                trendSummaryTile(title: "Max", value: summaryValue(detail.maxValue))
                trendSummaryTile(title: "Record Count", value: "\(detail.points.count)")
            }

            VStack(alignment: .leading, spacing: 10) {
                Label(appText("Detailed Trend Chart", appLanguageRaw), systemImage: "chart.bar.xaxis")
                    .font(.headline)
                if detail.points.isEmpty {
                    Text(appText("No trend points loaded.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, minHeight: 120)
                } else {
                    HealthTrendBarChart(points: detail.points, unit: detail.unit, color: color)
                }
            }
            .padding(14)
            .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 14, style: .continuous))

            VStack(alignment: .leading, spacing: 10) {
                Label(appText("Daily Points", appLanguageRaw), systemImage: "list.bullet.rectangle")
                    .font(.headline)
                if detail.points.isEmpty {
                    Text(appText("No trend points loaded.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            ForEach(detail.points.reversed()) { point in
                                HStack {
                                    Text(point.date)
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Text("\(formatTrendNumber(point.value))\(detail.unit.isEmpty ? "" : " \(detail.unit)")")
                                        .font(.callout.weight(.semibold).monospacedDigit())
                                }
                                .padding(.vertical, 7)
                                Divider()
                            }
                        }
                    }
                    .frame(maxHeight: 180)
                }
            }

            Spacer(minLength: 0)

            HStack {
                if let onAddContext {
                    Button(appText("Add Trend Context", appLanguageRaw)) {
                        onAddContext(detail)
                    }
                }
                Spacer()
                if let onAskAgent {
                    Button {
                        onAskAgent(detail)
                        dismiss()
                    } label: {
                        Label(appText("Ask Agent about Trend", appLanguageRaw), systemImage: "sparkles")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        }
        .padding(24)
        .frame(width: 720)
        .frame(minHeight: 620)
        .onChange(of: rangeDays) { _, newValue in
            Task { await loadIfNeeded(for: newValue) }
        }
    }

    @MainActor
    private func loadIfNeeded(for range: Int) async {
        guard let client, range > fetchedLimit, !loading else { return }
        loading = true
        defer { loading = false }
        let fetched = await client.fetchDaily(limit: range)
        if !fetched.isEmpty {
            records = fetched
            fetchedLimit = range
        }
    }

    private func trendSummaryTile(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(appText(title, appLanguageRaw))
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.callout.weight(.semibold))
                .lineLimit(2)
                .minimumScaleFactor(0.78)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(11)
        .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func summaryValue(_ value: Double?) -> String {
        guard let value else { return "—" }
        return "\(formatTrendNumber(value))\(detail.unit.isEmpty ? "" : " \(detail.unit)")"
    }
}

private struct HealthTrendBarChart: View {
    let points: [DesktopHealthTrendPoint]
    let unit: String
    let color: Color

    var body: some View {
        if points.isEmpty {
            ContentUnavailableView("No trend points loaded.", systemImage: "chart.bar.xaxis")
                .frame(height: 180)
        } else {
            let visiblePoints = Array(points.suffix(30))
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .bottom, spacing: 5) {
                    ForEach(visiblePoints) { point in
                        VStack(spacing: 6) {
                            Spacer(minLength: 0)
                            RoundedRectangle(cornerRadius: 3, style: .continuous)
                                .fill(color.gradient)
                                .frame(height: 12 + CGFloat(normalized(point.value, in: visiblePoints)) * 132)
                            Text(shortDate(point.date))
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(.secondary)
                                .rotationEffect(.degrees(-35))
                                .frame(height: 24)
                        }
                        .frame(maxWidth: .infinity, minHeight: 174, alignment: .bottom)
                        .help("\(point.date): \(formatTrendNumber(point.value)) \(unit)")
                    }
                }
            }
            .frame(minHeight: 190)
        }
    }

    private func normalized(_ value: Double, in points: [DesktopHealthTrendPoint]) -> Double {
        guard let maxValue = points.map(\.value).max(), maxValue > 0 else { return 0.08 }
        return max(0.06, value / maxValue)
    }

    private func shortDate(_ date: String) -> String {
        let components = date.split(separator: "-").map(String.init)
        if components.count >= 2 {
            return components.suffix(2).joined(separator: "/")
        }
        return date
    }
}

private func healthTrendColor(_ kind: DesktopHealthTrendKind) -> Color {
    switch kind {
    case .diet: .orange
    case .water: .cyan
    case .supplements: .teal
    case .weight: .green
    case .bloodPressure: .pink
    case .steps: .blue
    }
}

private func formatTrendNumber(_ value: Double) -> String {
    let formatter = NumberFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.numberStyle = .decimal
    formatter.usesGroupingSeparator = true
    formatter.minimumFractionDigits = 0
    formatter.maximumFractionDigits = value.rounded() == value ? 0 : 1
    return formatter.string(from: NSNumber(value: value)) ?? "\(value)"
}

private struct WorkspaceGuidanceCard: View {
    let row: DesktopWorkspaceGuidanceRow
    let isWorking: Bool
    let ctaTitle: String
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            ZStack {
                if isWorking {
                    ProgressView()
                        .controlSize(.small)
                } else {
                    Image(systemName: row.systemImage)
                        .font(.headline)
                        .foregroundStyle(color)
                }
            }
            .frame(width: 32, height: 32)
            .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            VStack(alignment: .leading, spacing: 5) {
                Text(appText(row.title, appLanguageRaw))
                    .font(.callout.weight(.semibold))
                    .lineLimit(1)
                Text(appText(row.detail, appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }
            Spacer(minLength: 0)
            Label(ctaTitle, systemImage: isWorking ? "hourglass" : "chevron.right")
                .font(.caption.weight(.semibold))
                .labelStyle(.titleAndIcon)
                .foregroundStyle(color)
                .padding(.horizontal, 9)
                .padding(.vertical, 6)
                .background(color.opacity(0.10), in: Capsule())
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 96, alignment: .topLeading)
        .background(color.opacity(0.07), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(color.opacity(0.18), lineWidth: 1)
        }
    }

    private var color: Color {
        switch row.tone {
        case "purple": .purple
        case "teal": .teal
        case "orange": .orange
        case "indigo": .indigo
        case "blue": .blue
        default: .accentColor
        }
    }
}

private struct WorkspaceActionCard: View {
    let card: ActionCardSummary
    let color: Color
    let systemImage: String
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: systemImage)
                .font(.headline)
                .foregroundStyle(.white)
                .frame(width: 32, height: 32)
                .background(color.opacity(0.86), in: RoundedRectangle(cornerRadius: 9, style: .continuous))

            VStack(alignment: .leading, spacing: 7) {
                Text(MarkdownRenderSupport.compactPreview(from: card.title, maxLines: 1))
                    .font(.callout.weight(.semibold))
                    .lineLimit(2)

                if let content = card.content?.trimmingCharacters(in: .whitespacesAndNewlines), !content.isEmpty {
                    Text(MarkdownRenderSupport.compactPreview(from: content, maxLines: 3))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                }

                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 6) {
                        metaChips
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        metaChips
                    }
                }
            }

            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 96, alignment: .topLeading)
        .background(color.opacity(0.075), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(color.opacity(0.14), lineWidth: 1)
        }
    }

    private func actionMetaChip(_ text: String) -> some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(color)
            .lineLimit(1)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(color.opacity(0.11), in: Capsule())
    }

    @ViewBuilder
    private var metaChips: some View {
        if let status = card.status, !status.isEmpty {
            actionMetaChip(status)
        }
        if let priority = card.priority {
            actionMetaChip("P\(priority)")
        }
        if let metricKey = card.metricKey, !metricKey.isEmpty {
            actionMetaChip("\(appText("Metric", appLanguageRaw)): \(metricKey)")
        }
        if let sourceType = card.sourceType, !sourceType.isEmpty {
            actionMetaChip("\(appText("Source", appLanguageRaw)): \(sourceType)")
        }
    }
}

struct ImportWorkspaceView: View {
    @Bindable var viewModel: TodayViewModel
    let jobClient: DesktopJobClient
    let kind: DesktopWorkspaceKind
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    var onAddContext: ((AgentContextItem) -> Void)?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                WorkspaceOverviewView(
                    viewModel: viewModel,
                    jobClient: jobClient,
                    kind: kind,
                    onAskAgent: onAskAgent,
                    onAddContext: onAddContext
                )
                    .frame(minHeight: 420)
                Divider()
                ImportCenterView(jobClient: jobClient, onAskAgent: onAskAgent)
                    .frame(minHeight: 460)
            }
        }
    }
}

struct MenuBarRootView: View {
    @Bindable var viewModel: TodayViewModel
    @Bindable var navigation: AppNavigationState
    let recordClient: RecordClient
    @Environment(\.openWindow) private var openWindow
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var isSavingQuickRecord = false
    @State private var quickRecordMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(appText("Health Agent", appLanguageRaw), systemImage: "heart.text.square")
                .font(.headline)
            Divider()
            Label(appText("Status Center", appLanguageRaw), systemImage: "dot.radiowaves.left.and.right")
                .font(.caption.bold())
                .foregroundStyle(.secondary)
            HStack(spacing: 8) {
                menuStatusChip(
                    title: "Jobs",
                    value: "\(activeJobCount)",
                    color: activeJobCount > 0 ? .teal : .secondary
                )
                menuStatusChip(
                    title: "Failed",
                    value: "\(failedJobCount)",
                    color: failedJobCount > 0 ? .orange : .secondary
                )
                menuStatusChip(
                    title: "Cards",
                    value: "\(viewModel.bootstrap?.actionCards.count ?? 0)",
                    color: .blue
                )
            }
            Button(appText("Open Jobs", appLanguageRaw)) {
                navigation.selection = .jobs
                openWindow(id: "main")
            }
            Divider()
            Label(appText("Needs Review", appLanguageRaw), systemImage: "tray.full")
                .font(.caption.bold())
                .foregroundStyle(.secondary)
            if attentionJobs.isEmpty {
                Text(appText("No pending job results.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(attentionJobs) { job in
                    let outcome = DesktopJobOutcomePresentation(job: job)
                    Button {
                        navigation.selection = .jobs
                        openWindow(id: "main")
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(appText(outcome.title, appLanguageRaw))
                                .font(.caption.weight(.semibold))
                            Text(job.sourceName ?? job.jobType)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            Divider()
            if viewModel.topActions.isEmpty {
                Text(appText("No actions loaded", appLanguageRaw))
                    .foregroundStyle(.secondary)
            } else {
                ForEach(viewModel.topActions.prefix(3)) { action in
                    Text(action.title)
                        .lineLimit(1)
                }
            }
            Divider()
            Label(appText("Quick Capture", appLanguageRaw), systemImage: "bolt.fill")
                .font(.caption.bold())
                .foregroundStyle(.secondary)
            Button {
                saveQuickRecord("喝水 200ml")
            } label: {
                Label(appText("Record Water 200ml", appLanguageRaw), systemImage: "drop.fill")
            }
            .disabled(isSavingQuickRecord)
            Button {
                saveQuickRecord("补剂已吃")
            } label: {
                Label(appText("Record Supplements Taken", appLanguageRaw), systemImage: "pills.fill")
            }
            .disabled(isSavingQuickRecord)
            if isSavingQuickRecord {
                ProgressView()
                    .controlSize(.small)
            }
            if let quickRecordMessage {
                Text(quickRecordMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(nil)
            }
            Divider()
            Button {
                reopenMainApp()
            } label: {
                Label(appText("Reopen App", appLanguageRaw), systemImage: "macwindow")
            }
            Button(appText("Open Today", appLanguageRaw)) {
                navigation.selection = .today
                reopenMainApp()
            }
            Button(appText("Open Record", appLanguageRaw)) {
                navigation.selection = .record
                reopenMainApp()
            }
            Button(appText("Ask Agent", appLanguageRaw)) {
                navigation.selection = .agent
                reopenMainApp()
            }
            Button(appText("Import File", appLanguageRaw)) {
                navigation.selection = .genetics
                reopenMainApp()
            }
            Divider()
            Button(appText("Quit", appLanguageRaw), role: .destructive) {
                NSApplication.shared.terminate(nil)
            }
        }
        .task {
            if viewModel.bootstrap == nil {
                await viewModel.refresh()
            }
        }
        .padding(8)
        .frame(width: 250)
    }

    private func reopenMainApp() {
        openWindow(id: "main")
        NSApplication.shared.activate(ignoringOtherApps: true)
    }

    private var activeJobCount: Int {
        (viewModel.bootstrap?.activeJobs ?? []).filter { $0.status == "queued" || $0.status == "running" }.count
    }

    private var failedJobCount: Int {
        (viewModel.bootstrap?.activeJobs ?? []).filter { $0.status == "failed" }.count
    }

    private var attentionJobs: [DesktopJobSummary] {
        Array((viewModel.bootstrap?.activeJobs ?? [])
            .filter { $0.status == "failed" || $0.status == "completed" }
            .prefix(3))
    }

    private func menuStatusChip(title: String, value: String, color: Color) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.caption.weight(.bold).monospacedDigit())
            Text(appText(title, appLanguageRaw))
                .font(.caption2)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
        .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .foregroundStyle(color)
    }

    private func saveQuickRecord(_ text: String) {
        guard !isSavingQuickRecord else { return }
        isSavingQuickRecord = true
        quickRecordMessage = nil
        Task {
            do {
                let result = try await recordClient.quickRecord(text: text)
                quickRecordMessage = result.displayMessage
                sendMenuBarNotification(title: appText("Saved", appLanguageRaw), body: result.displayMessage)
                await viewModel.refresh()
            } catch {
                quickRecordMessage = error.localizedDescription
                sendMenuBarNotification(title: appText("Save failed", appLanguageRaw), body: error.localizedDescription)
            }
            isSavingQuickRecord = false
        }
    }

    private func sendMenuBarNotification(title: String, body: String) {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            content.sound = .default
            let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
            UNUserNotificationCenter.current().add(request)
        }
    }
}
