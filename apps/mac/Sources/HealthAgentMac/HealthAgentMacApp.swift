import HealthAgentMacCore
import SwiftUI

@main
struct HealthAgentMacApp: App {
    @State private var appServices = AppServices()
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @AppStorage(AppFontScale.defaultsKey) private var appFontScaleLevel = AppFontScale.defaultLevel

    var body: some Scene {
        WindowGroup(id: "main") {
            AppRootView(services: appServices)
                .appFontScale(AppFontScale(level: appFontScaleLevel))
        }
        MenuBarExtra(appText("Health Agent", appLanguageRaw), systemImage: "heart.text.square") {
            MenuBarRootView(
                viewModel: appServices.todayViewModel,
                navigation: appServices.navigation
            )
            .appFontScale(AppFontScale(level: appFontScaleLevel))
        }
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
                Divider()
                Button(appText("Increase Font Size", appLanguageRaw)) {
                    appFontScaleLevel = AppFontScale(level: appFontScaleLevel).increased().level
                }
                .keyboardShortcut("+", modifiers: [.command])
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

private extension View {
    func appFontScale(_ scale: AppFontScale) -> some View {
        modifier(AppFontScaleViewModifier(scale: scale))
    }
}

private struct AppFontScaleViewModifier: ViewModifier {
    let scale: AppFontScale

    func body(content: Content) -> some View {
        content
            .dynamicTypeSize(dynamicTypeSize)
    }

    private var dynamicTypeSize: DynamicTypeSize {
        switch scale.level {
        case AppFontScale.minLevel:
            .small
        case 1:
            .large
        case 2:
            .xLarge
        case 3:
            .xxLarge
        case AppFontScale.maxLevel:
            .xxxLarge
        default:
            .medium
        }
    }
}

@MainActor
@Observable
final class AppNavigationState {
    var selection: SidebarDestination? = .today
    var traceConversationID: Int?

    func openTrace(conversationID: Int) {
        traceConversationID = conversationID
        selection = .trace
    }
}

@MainActor
struct AppServices {
    let tokenProvider: UserDefaultsTokenStore
    let navigation = AppNavigationState()
    let apiClient: APIClient
    let todayViewModel: TodayViewModel
    let agentViewModel: AgentChatViewModel
    let recordClient: RecordClient
    let desktopJobClient: DesktopJobClient
    let traceClient: TraceClient
    let authClient: AuthClient

    init() {
        let tokenProvider = UserDefaultsTokenStore()
        self.tokenProvider = tokenProvider
        let baseURL = APIEndpoint.resolvedBaseURL()
        self.apiClient = APIClient(baseURL: baseURL, tokenProvider: tokenProvider)
        self.todayViewModel = TodayViewModel(
            service: DesktopBootstrapService(apiClient: apiClient)
        )
        self.agentViewModel = AgentChatViewModel(
            streamService: AgentStreamClient(baseURL: baseURL, tokenProvider: tokenProvider)
        )
        self.recordClient = RecordClient(apiClient: apiClient)
        self.desktopJobClient = DesktopJobClient(apiClient: apiClient)
        self.traceClient = TraceClient(apiClient: apiClient)
        self.authClient = AuthClient(apiClient: apiClient, tokenStore: tokenProvider)
    }
}

struct AppRootView: View {
    let services: AppServices
    @Bindable private var navigation: AppNavigationState
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var hasCheckedAuth = false
    @State private var isAuthenticated = false

    init(services: AppServices) {
        self.services = services
        self.navigation = services.navigation
    }

    var body: some View {
        Group {
            if !hasCheckedAuth {
                ProgressView(appText("Checking login...", appLanguageRaw))
                    .frame(minWidth: 520, minHeight: 360)
            } else if !isAuthenticated {
                LoginView(authClient: services.authClient) {
                    isAuthenticated = true
                    Task { await services.todayViewModel.refresh() }
                }
            } else {
                NavigationSplitView {
                    List(SidebarDestination.allCases, selection: $navigation.selection) { destination in
                        Label(destination.title(language: AppLanguage(storedValue: appLanguageRaw)), systemImage: destination.systemImage)
                            .tag(destination)
                    }
                    .navigationTitle(appText("Health Agent", appLanguageRaw))
                } detail: {
                    detailView
                }
            }
        }
        .frame(minWidth: 980, minHeight: 680)
        .task {
            guard !hasCheckedAuth else { return }
            isAuthenticated = await services.authClient.hasValidSession()
            hasCheckedAuth = true
        }
    }

    @ViewBuilder
    private var detailView: some View {
        switch navigation.selection ?? .today {
        case .today:
            TodayView(viewModel: services.todayViewModel)
        case .agent:
            AgentChatView(viewModel: services.agentViewModel)
        case .record:
            RecordHubView(client: services.recordClient)
        case .jobs:
            JobListView(client: services.desktopJobClient) { conversationID in
                navigation.openTrace(conversationID: conversationID)
            }
        case .trace:
            TraceLookupView(client: services.traceClient, navigation: navigation)
        case .data:
            WorkspaceOverviewView(viewModel: services.todayViewModel, kind: .data)
        case .genetics:
            ImportWorkspaceView(viewModel: services.todayViewModel, jobClient: services.desktopJobClient, kind: .genetics)
        case .knowledge:
            ImportWorkspaceView(viewModel: services.todayViewModel, jobClient: services.desktopJobClient, kind: .knowledge)
        case .settings:
            SettingsView(authClient: services.authClient, tokenStore: services.tokenProvider) {
                isAuthenticated = false
                navigation.selection = .today
            }
        }
    }
}

struct LoginView: View {
    let authClient: AuthClient
    let onLogin: () -> Void
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var username = ""
    @State private var password = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 20) {
            VStack(spacing: 8) {
                Image(systemName: "heart.text.square.fill")
                    .font(.system(size: 44))
                    .foregroundStyle(Color.accentColor)
                Text(appText("Health Agent", appLanguageRaw))
                    .font(.largeTitle.bold())
                Text(appText("Sign in with your executor.life account.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 12) {
                TextField(appText("Username or email", appLanguageRaw), text: $username)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { submitIfReady() }
                SecureField(appText("Password", appLanguageRaw), text: $password)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { submitIfReady() }

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                }

                Button {
                    submitIfReady()
                } label: {
                    Label(appText(isSubmitting ? "Signing in..." : "Sign In", appLanguageRaw), systemImage: "person.crop.circle.badge.checkmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(isSubmitting || username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || password.isEmpty)
                .keyboardShortcut(.return, modifiers: .command)
            }
            .frame(width: 360)
        }
        .padding(36)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func submitIfReady() {
        guard !isSubmitting else { return }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty, !password.isEmpty else { return }
        Task { await signIn(username: trimmedUsername, password: password) }
    }

    private func signIn(username: String, password: String) async {
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }
        do {
            _ = try await authClient.login(username: username, password: password)
            self.password = ""
            onLogin()
        } catch APIError.unauthorized {
            errorMessage = "用户名或密码错误。"
        } catch APIError.httpStatus(let status, let message) {
            errorMessage = message.map { "登录失败，HTTP \(status)：\($0)" } ?? "登录失败，HTTP \(status)。"
        } catch {
            errorMessage = "登录失败：\(error.localizedDescription)"
        }
    }
}

struct TodayView: View {
    @Bindable var viewModel: TodayViewModel
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var dashboardRange: DashboardRange = .sevenDays

    var body: some View {
        ZStack {
            Color(nsColor: .controlBackgroundColor)
                .ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let presentation {
                        HStack(alignment: .top, spacing: 16) {
                            VStack(alignment: .leading, spacing: 18) {
                                dashboardHero(presentation)
                                actionPanel(presentation.actionRows)
                                recentRecordsPanel(presentation.recentRecordRows)
                            }
                            .frame(minWidth: 620, maxWidth: .infinity, alignment: .topLeading)

                            VStack(alignment: .leading, spacing: 18) {
                                refreshPanel
                                wearablePanel(presentation.wearableMetrics)
                                memoryPanel(presentation.memoryRows)
                                jobsPanel(presentation.activeJobRows)
                            }
                            .frame(width: 360, alignment: .topLeading)
                        }
                    } else {
                        loadingPanel
                    }
                }
                .frame(maxWidth: 1220, alignment: .center)
                .padding(.horizontal, 26)
                .padding(.vertical, 22)
                .frame(maxWidth: .infinity, alignment: .top)
            }
        }
        .task {
            if viewModel.bootstrap == nil {
                await viewModel.refresh()
            }
        }
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

    private var refreshPanel: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(appText("Health Agent", appLanguageRaw))
                    .font(.headline.weight(.semibold))
                if viewModel.isLoading {
                    Text(appText("Loading desktop context...", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Text(appText("Ready", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            Button {
                Task { await viewModel.refresh() }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .frame(width: 24, height: 24)
            }
            .buttonStyle(.borderedProminent)
            .help(appText("Refresh", appLanguageRaw))
        }
        .padding(14)
        .background(.background, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(panelStroke(radius: 16))
    }

    private func dashboardHero(_ presentation: DesktopDashboardPresentation) -> some View {
        let rangeMetrics = dashboardRange == .sevenDays ? presentation.sevenDayMetrics : presentation.thirtyDayMetrics
        let rangeTrends = dashboardRange == .sevenDays ? presentation.sevenDayTrends : presentation.thirtyDayTrends

        return VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 6) {
                Text(appText("Health Dashboard", appLanguageRaw))
                    .font(.system(size: 34, weight: .bold, design: .rounded))
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
                                .background(Color.teal.opacity(0.10), in: Capsule())
                                .foregroundStyle(.teal)
                        }
                    }
                    .padding(.top, 6)
                }
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 145), spacing: 12)], spacing: 12) {
                ForEach(presentation.heroMetrics) { metric in
                    HeroMetricTile(
                        metric: metric,
                        title: localizedMetricTitle(metric.titleKey),
                        detail: localizedMetricDetail(metric.detail)
                    )
                }
            }

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
                    SummaryMetricStrip(
                        metric: metric,
                        title: localizedMetricTitle(metric.titleKey),
                        detail: localizedMetricDetail(metric.detail)
                    )
                }
            }

            TrendSparklineGrid(
                trends: rangeTrends,
                localizedTitle: localizedMetricTitle,
                localizedDetail: localizedMetricDetail
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
        .padding(24)
        .background {
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(.background)
                .overlay(alignment: .topTrailing) {
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .fill(
                            LinearGradient(
                                colors: [Color.teal.opacity(0.14), Color.blue.opacity(0.07), Color.clear],
                                startPoint: .topTrailing,
                                endPoint: .bottomLeading
                            )
                        )
                }
        }
        .overlay(panelStroke(radius: 22))
        .shadow(color: Color.black.opacity(0.045), radius: 18, y: 10)
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

    private func sectionHeader(title: String, systemImage: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: systemImage)
                .foregroundStyle(.secondary)
            Text(title)
                .font(.headline.weight(.semibold))
            Spacer()
        }
    }

    private func card<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            content()
        }
        .padding(16)
        .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(panelStroke(radius: 18))
    }

    private func panelStroke(radius: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: radius, style: .continuous)
            .stroke(Color.primary.opacity(0.07), lineWidth: 1)
    }

    private func actionPanel(_ actions: [DesktopDashboardRow]) -> some View {
        card {
            sectionHeader(title: appText("Priority Actions", appLanguageRaw), systemImage: "checklist")
            if actions.isEmpty {
                EmptyStateText(text: appText("No actions loaded yet.", appLanguageRaw))
            } else {
                VStack(spacing: 0) {
                    ForEach(actions) { row in
                        DashboardRowView(row: row)
                        if row.id != actions.last?.id { Divider().padding(.leading, 34) }
                    }
                }
            }
        }
    }

    private func recentRecordsPanel(_ records: [DesktopDashboardRow]) -> some View {
        card {
            sectionHeader(title: appText("Recent Health Records", appLanguageRaw), systemImage: "waveform.path.ecg")
            if records.isEmpty {
                EmptyStateText(text: appText("No recent health records loaded.", appLanguageRaw))
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 10)], spacing: 10) {
                    ForEach(records) { row in
                        CompactRecordCard(row: row)
                    }
                }
            }
        }
    }

    private func wearablePanel(_ metrics: [DesktopDashboardMetric]) -> some View {
        card {
            sectionHeader(title: appText("Wearable Today", appLanguageRaw), systemImage: "sensor.tag.radiowaves.forward.fill")
            VStack(spacing: 8) {
                ForEach(metrics) { metric in
                    VitalRow(
                        metric: metric,
                        title: localizedMetricTitle(metric.titleKey),
                        detail: localizedMetricDetail(metric.detail)
                    )
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

private struct HeroMetricTile: View {
    let metric: DesktopDashboardMetric
    let title: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: metric.systemImage)
                    .foregroundStyle(toneColor(metric.tone))
                Spacer()
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
        }
        .padding(12)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

private struct TrendSparklineGrid: View {
    let trends: [DesktopDashboardTrend]
    let localizedTitle: (String) -> String
    let localizedDetail: (String) -> String

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 210), spacing: 12)], spacing: 12) {
            ForEach(trends) { trend in
                TrendSparklineCard(
                    trend: trend,
                    title: localizedTitle(trend.titleKey),
                    detail: localizedDetail(trend.averageLabel)
                )
            }
        }
    }
}

private struct TrendSparklineCard: View {
    let trend: DesktopDashboardTrend
    let title: String
    let detail: String

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

private struct VitalRow: View {
    let metric: DesktopDashboardMetric
    let title: String
    let detail: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: metric.systemImage)
                .font(.callout.weight(.semibold))
                .foregroundStyle(toneColor(metric.tone))
                .frame(width: 30, height: 30)
                .background(toneColor(metric.tone).opacity(0.11), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.callout.weight(.semibold))
                    .lineLimit(1)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            Text(metric.value)
                .font(.title3.weight(.bold).monospacedDigit())
                .lineLimit(1)
        }
        .padding(10)
        .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct DashboardRowView: View {
    let row: DesktopDashboardRow

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: row.systemImage)
                .font(.callout)
                .foregroundStyle(toneColor(row.tone))
                .frame(width: 24, height: 24)
            VStack(alignment: .leading, spacing: 3) {
                Text(row.title)
                    .font(.callout.weight(.semibold))
                    .lineLimit(2)
                if let subtitle = row.subtitle, !subtitle.isEmpty {
                    Text(subtitle)
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
        }
        .padding(.vertical, 9)
    }
}

private struct CompactRecordCard: View {
    let row: DesktopDashboardRow

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

private func toneColor(_ tone: String) -> Color {
    switch tone {
    case "orange": .orange
    case "cyan": .cyan
    case "green": .green
    case "pink": .pink
    case "purple": .purple
    case "blue": .blue
    case "red": .red
    case "indigo": .indigo
    case "teal": .teal
    default: .secondary
    }
}

struct SectionPanel<Content: View>: View {
    let title: String
    let systemImage: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(title, systemImage: systemImage)
                .font(.title3.bold())
            content
        }
        .padding(18)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

struct ContentPlaceholder: View {
    let destination: SidebarDestination
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(destination.title(language: AppLanguage(storedValue: appLanguageRaw)), systemImage: destination.systemImage)
                .font(.title.bold())
            Text("Native macOS client surface backed by \(APIEndpoint.defaultBaseURL.absoluteString)")
                .foregroundStyle(.secondary)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

struct WorkspaceOverviewView: View {
    @Bindable var viewModel: TodayViewModel
    let kind: DesktopWorkspaceKind
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

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
        .task {
            if viewModel.bootstrap == nil {
                await viewModel.refresh()
            }
        }
    }

    private var summary: DesktopWorkspaceSummary? {
        viewModel.bootstrap?.workspaceSummary(for: kind)
    }

    @ViewBuilder
    private func workspaceSummary(_ summary: DesktopWorkspaceSummary) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 12)], spacing: 12) {
            ForEach(summary.metrics) { metric in
                WorkspaceMetricCard(metric: metric)
            }
        }

        SectionPanel(title: appText("Workspace Actions", appLanguageRaw), systemImage: "wand.and.stars") {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 10)], spacing: 10) {
                ForEach(summary.guidanceRows) { row in
                    WorkspaceGuidanceCard(row: row)
                }
            }
        }

        if kind == .data {
            SectionPanel(title: appText("Priority Actions", appLanguageRaw), systemImage: "checklist") {
                if summary.actionCards.isEmpty {
                    Text(appText("No actions loaded yet.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                } else {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 10)], spacing: 10) {
                        ForEach(summary.actionCards.prefix(6)) { card in
                            HStack(alignment: .top, spacing: 10) {
                                Image(systemName: "checkmark.seal.fill")
                                    .foregroundStyle(.teal)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(card.title)
                                        .font(.callout.weight(.semibold))
                                        .lineLimit(2)
                                    HStack(spacing: 6) {
                                        if let status = card.status {
                                            Text(status)
                                        }
                                        if let priority = card.priority {
                                            Text("P\(priority)")
                                        }
                                    }
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                }
                                Spacer(minLength: 0)
                            }
                            .padding(12)
                            .background(Color.teal.opacity(0.07), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        }
                    }
                }
            }

            SectionPanel(title: appText("Recent Health Records", appLanguageRaw), systemImage: "waveform.path.ecg") {
                if summary.recentRecords.isEmpty {
                    Text(appText("No recent health records loaded.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                } else {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 10)], spacing: 10) {
                        ForEach(summary.recentRecords) { record in
                            HStack(spacing: 10) {
                                Image(systemName: workspaceRecordIcon(record.type))
                                    .foregroundStyle(workspaceRecordColor(record.type))
                                    .frame(width: 28, height: 28)
                                    .background(workspaceRecordColor(record.type).opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
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
                                    .font(.callout.weight(.semibold).monospacedDigit())
                                    .lineLimit(1)
                            }
                            .padding(12)
                            .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        }
                    }
                }
            }
        } else {
            SectionPanel(title: appText("Priority Actions", appLanguageRaw), systemImage: "checklist") {
                if summary.actionCards.isEmpty {
                    Text(appText("No actions loaded yet.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                } else {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 10)], spacing: 10) {
                        ForEach(summary.actionCards.prefix(6)) { card in
                            HStack(alignment: .top, spacing: 10) {
                                Image(systemName: kind == .genetics ? "dna" : "books.vertical.fill")
                                    .foregroundStyle(kind == .genetics ? .purple : .teal)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(card.title)
                                        .font(.callout.weight(.semibold))
                                        .lineLimit(2)
                                    Text(card.status ?? appText("Ready", appLanguageRaw))
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer(minLength: 0)
                            }
                            .padding(12)
                            .background((kind == .genetics ? Color.purple : Color.teal).opacity(0.07), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        }
                    }
                }
            }
        }

        if kind == .genetics {
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

                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 10)], spacing: 10) {
                            ForEach(genomic.topCategories) { category in
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(category.category)
                                        .font(.callout.weight(.semibold))
                                        .lineLimit(1)
                                    Text("\(category.count) variants")
                                        .font(.title3.weight(.bold).monospacedDigit())
                                    Text("H \(category.highRiskCount) · M \(category.mediumRiskCount)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
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
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: 10)], spacing: 10) {
                        ForEach(findings.prefix(8)) { finding in
                            VStack(alignment: .leading, spacing: 8) {
                                HStack(alignment: .top) {
                                    Text(finding.displayTitle)
                                        .font(.callout.weight(.semibold))
                                        .lineLimit(2)
                                    Spacer(minLength: 8)
                                    Text((finding.riskLevel ?? "info").uppercased())
                                        .font(.caption2.weight(.bold))
                                        .padding(.horizontal, 7)
                                        .padding(.vertical, 4)
                                        .background(geneticRiskColor(finding.riskLevel).opacity(0.16), in: Capsule())
                                        .foregroundStyle(geneticRiskColor(finding.riskLevel))
                                }
                                HStack(spacing: 8) {
                                    if let rsid = finding.rsid {
                                        Text(rsid)
                                    }
                                    if let genotype = finding.genotype {
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

        if kind == .knowledge {
            SectionPanel(title: appText("Knowledge Coverage", appLanguageRaw), systemImage: "books.vertical.fill") {
                if let knowledge = summary.knowledgeSummary, knowledge.documentCount > 0 {
                    VStack(alignment: .leading, spacing: 14) {
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
        case "high_risk": "exclamationmark.triangle.fill"
        case "medium_risk": "exclamationmark.circle.fill"
        case "categories": "square.grid.2x2.fill"
        case "kb_jobs": "books.vertical.fill"
        case "documents": "doc.text.fill"
        case "claims": "checkmark.seal.fill"
        case "sources": "link"
        case "edges": "point.3.connected.trianglepath.dotted"
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
        case "high_risk": .red
        case "medium_risk": .orange
        case "categories": .indigo
        case "kb_jobs": .teal
        case "documents": .teal
        case "claims": .green
        case "sources": .blue
        case "edges": .indigo
        case "running": .blue
        case "action_cards": .orange
        case "focus_domains": .cyan
        case "memory": .indigo
        default: .accentColor
        }
    }
}

private struct WorkspaceGuidanceCard: View {
    let row: DesktopWorkspaceGuidanceRow
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: row.systemImage)
                .font(.headline)
                .foregroundStyle(color)
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
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 96, alignment: .topLeading)
        .background(color.opacity(0.07), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
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

struct ImportWorkspaceView: View {
    @Bindable var viewModel: TodayViewModel
    let jobClient: DesktopJobClient
    let kind: DesktopWorkspaceKind

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                WorkspaceOverviewView(viewModel: viewModel, kind: kind)
                    .frame(minHeight: 420)
                Divider()
                ImportCenterView(jobClient: jobClient)
                    .frame(minHeight: 460)
            }
        }
    }
}

struct MenuBarRootView: View {
    @Bindable var viewModel: TodayViewModel
    @Bindable var navigation: AppNavigationState
    @Environment(\.openWindow) private var openWindow
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(appText("Health Agent", appLanguageRaw), systemImage: "heart.text.square")
                .font(.headline)
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
            Button(appText("Open Today", appLanguageRaw)) {
                navigation.selection = .today
                openWindow(id: "main")
            }
            Button(appText("Ask Agent", appLanguageRaw)) {
                navigation.selection = .agent
                openWindow(id: "main")
            }
            Button(appText("Import File", appLanguageRaw)) {
                navigation.selection = .genetics
                openWindow(id: "main")
            }
        }
        .task {
            if viewModel.bootstrap == nil {
                await viewModel.refresh()
            }
        }
        .padding(8)
        .frame(width: 220)
    }
}
