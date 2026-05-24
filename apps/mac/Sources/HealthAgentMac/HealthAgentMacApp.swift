import HealthAgentMacCore
import AppKit
import SwiftUI
import UserNotifications

@main
struct HealthAgentMacApp: App {
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
            Label {
                Text(appText("Health Agent", appLanguageRaw))
            } icon: {
                Image(nsImage: AppBrandIcon.statusBarImage)
            }
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
                Button(appText("Command Palette", appLanguageRaw)) {
                    appServices.navigation.isCommandPalettePresented = true
                }
                .keyboardShortcut("k", modifiers: [.command])
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

private enum AppBrandIcon {
    static var statusBarImage: NSImage {
        let image: NSImage
        if let bundledImage = NSImage(named: "StatusBarIconTemplate") {
            image = bundledImage
        } else if let resourceURL = Bundle.module.url(forResource: "StatusBarIconTemplate", withExtension: "png"),
                  let moduleImage = NSImage(contentsOf: resourceURL) {
            image = moduleImage
        } else {
            image = NSImage(systemSymbolName: "heart.text.square", accessibilityDescription: "Health Agent") ?? NSImage()
        }
        image.isTemplate = true
        return image
    }
}

private extension View {
    func appFontScale(_ scale: AppFontScale) -> some View {
        modifier(AppFontScaleViewModifier(scale: scale))
    }

    func fontScaleKeyboardShortcuts(level: Binding<Int>) -> some View {
        background(FontScaleKeyboardShortcutBridge(level: level).frame(width: 0, height: 0))
    }
}

private struct FontScaleKeyboardShortcutBridge: NSViewRepresentable {
    @Binding var level: Int

    func makeCoordinator() -> Coordinator {
        Coordinator(level: $level)
    }

    func makeNSView(context: Context) -> NSView {
        context.coordinator.install()
        return NSView(frame: .zero)
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        context.coordinator.level = $level
    }

    static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
        coordinator.uninstall()
    }

    final class Coordinator {
        var level: Binding<Int>
        private var monitor: Any?

        init(level: Binding<Int>) {
            self.level = level
        }

        func install() {
            guard monitor == nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
                guard let self,
                      let key = event.charactersIgnoringModifiers?.lowercased(),
                      let action = AppFontScaleKeyboardShortcut.action(
                        forKeyEquivalent: key,
                        command: event.modifierFlags.contains(.command),
                        shift: event.modifierFlags.contains(.shift),
                        option: event.modifierFlags.contains(.option),
                        control: event.modifierFlags.contains(.control)
                      ) else {
                    return event
                }

                level.wrappedValue = action.apply(to: AppFontScale(level: level.wrappedValue)).level
                return nil
            }
        }

        func uninstall() {
            if let monitor {
                NSEvent.removeMonitor(monitor)
            }
            monitor = nil
        }
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
    var isCommandPalettePresented = false

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
            streamService: AgentStreamClient(baseURL: baseURL, tokenProvider: tokenProvider),
            contextBundleStore: UserDefaultsAgentContextBundleStore()
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
        .sheet(isPresented: $navigation.isCommandPalettePresented) {
            CommandPaletteView(
                commands: DesktopCommandPalette.defaultCommands(language: AppLanguage(storedValue: appLanguageRaw)),
                onSelect: handleCommand
            )
        }
    }

    @ViewBuilder
    private var detailView: some View {
        switch navigation.selection ?? .today {
        case .today:
            TodayView(
                viewModel: services.todayViewModel,
                onAskAgent: askAgentWithContext,
                onAddContext: addAgentContext
            )
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
            WorkspaceOverviewView(
                viewModel: services.todayViewModel,
                kind: .data,
                onAskAgent: askAgentWithContext,
                onAddContext: addAgentContext
            )
        case .genetics:
            ImportWorkspaceView(
                viewModel: services.todayViewModel,
                jobClient: services.desktopJobClient,
                kind: .genetics,
                onAskAgent: askAgentWithContext,
                onAddContext: addAgentContext
            )
        case .knowledge:
            ImportWorkspaceView(
                viewModel: services.todayViewModel,
                jobClient: services.desktopJobClient,
                kind: .knowledge,
                onAskAgent: askAgentWithContext,
                onAddContext: addAgentContext
            )
        case .settings:
            SettingsView(authClient: services.authClient, tokenStore: services.tokenProvider) {
                isAuthenticated = false
                navigation.selection = .today
            }
        }
    }

    private func askAgentWithContext(_ prompt: String, _ item: AgentContextItem?) {
        if let item {
            services.agentViewModel.addContextItem(item)
        }
        services.agentViewModel.prepareDraft(prompt)
        navigation.selection = .agent
    }

    private func addAgentContext(_ item: AgentContextItem) {
        services.agentViewModel.addContextItem(item)
    }

    private func handleCommand(_ command: DesktopCommandPaletteCommand) {
        switch command.intent {
        case .navigate(let destination):
            navigation.selection = destination
        case .quickPrompt:
            services.agentViewModel.prepareDraft(
                "请基于我当前已选上下文，结合最近健康记录、基因、知识库证据和不确定性边界，给出可执行建议。"
            )
            navigation.selection = .agent
        case .refresh:
            Task { await services.todayViewModel.refresh() }
        }
    }
}

private struct CommandPaletteView: View {
    let commands: [DesktopCommandPaletteCommand]
    let onSelect: (DesktopCommandPaletteCommand) -> Void
    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @FocusState private var isSearchFocused: Bool
    @State private var query = ""

    private var filteredCommands: [DesktopCommandPaletteCommand] {
        DesktopCommandPalette.filter(commands, query: query)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: "command")
                    .foregroundStyle(.secondary)
                TextField(appText("Search command or action", appLanguageRaw), text: $query)
                    .textFieldStyle(.plain)
                    .font(.title3.weight(.semibold))
                    .focused($isSearchFocused)
                    .onSubmit { runFirstCommand() }
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(Color.secondary.opacity(0.09), in: RoundedRectangle(cornerRadius: 14, style: .continuous))

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(filteredCommands) { command in
                        Button {
                            select(command)
                        } label: {
                            CommandPaletteRow(command: command)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .frame(maxHeight: 420)

            HStack {
                Text("↩")
                    .font(.caption.monospaced().weight(.semibold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.secondary.opacity(0.10), in: Capsule())
                Text(appText("Run first result", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Text("⌘K")
                    .font(.caption.monospaced().weight(.semibold))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(18)
        .frame(width: 620)
        .onAppear {
            isSearchFocused = true
        }
    }

    private func runFirstCommand() {
        guard let command = filteredCommands.first else { return }
        select(command)
    }

    private func select(_ command: DesktopCommandPaletteCommand) {
        onSelect(command)
        dismiss()
    }
}

private struct CommandPaletteRow: View {
    let command: DesktopCommandPaletteCommand

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: command.systemImage)
                .font(.headline)
                .foregroundStyle(.white)
                .frame(width: 34, height: 34)
                .background(Color.accentColor.opacity(0.86), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                Text(command.title)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(.primary)
                Text(command.subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
        }
        .padding(11)
        .background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.secondary.opacity(0.08), lineWidth: 1)
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
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    var onAddContext: ((AgentContextItem) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var dashboardRange: DashboardRange = .sevenDays
    @State private var inputInboxFilter: InputInboxFilter = .all

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
                                inputInboxPanel(
                                    events: presentation.inputInboxEvents,
                                    summary: presentation.inputInboxSummary
                                )
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
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    var onAddContext: ((AgentContextItem) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var dataRange = "7d"
    @State private var selectedGenomicDetail: GenomicDetailRoute?
    @State private var selectedKnowledgeDocument: KnowledgeDocumentSummary?

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

    @ViewBuilder
    private func workspaceSummary(_ summary: DesktopWorkspaceSummary) -> some View {
        if kind == .data {
            dataWorkspaceSummary(summary)
        } else {
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

            SectionPanel(title: appText("Priority Actions", appLanguageRaw), systemImage: "checklist") {
                if summary.actionCards.isEmpty {
                    Text(appText("No actions loaded yet.", appLanguageRaw))
                        .foregroundStyle(.secondary)
                } else {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 10)], spacing: 10) {
                        ForEach(summary.actionCards.prefix(6)) { card in
                            HStack(alignment: .top, spacing: 10) {
                                Image(systemName: kind == .genetics ? "atom" : "books.vertical.fill")
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

        if kind != .data {
            if kind == .genetics {
                geneticsWorkspaceDetails(summary)
            }
            if kind == .knowledge {
                knowledgeWorkspaceDetails(summary)
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
                    WorkspaceMetricCard(metric: metric)
                }
            }

            dataTrendPanel

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
        let dietCalories = days == 30
            ? (recordsSummary.diet?.last30Calories ?? recordsSummary.diet?.last7Calories ?? recordsSummary.diet?.todayCalories ?? 0)
            : (recordsSummary.diet?.last7Calories ?? recordsSummary.diet?.last30Calories ?? recordsSummary.diet?.todayCalories ?? 0)
        let waterMl = days == 30
            ? (recordsSummary.water?.last30TotalMl ?? recordsSummary.water?.last7TotalMl ?? recordsSummary.water?.todayTotalMl ?? 0)
            : (recordsSummary.water?.last7TotalMl ?? recordsSummary.water?.last30TotalMl ?? recordsSummary.water?.todayTotalMl ?? 0)
        let supplements = days == 30
            ? (recordsSummary.supplements?.last30Count ?? recordsSummary.supplements?.last7Count ?? recordsSummary.supplements?.todayCount ?? 0)
            : (recordsSummary.supplements?.last7Count ?? recordsSummary.supplements?.last30Count ?? recordsSummary.supplements?.todayCount ?? 0)
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
        let summary = viewModel.bootstrap?.recentRecordsSummary
        let is30Days = dataRange == "30d"
        let dietPoints = (is30Days ? summary?.diet?.daily30 : summary?.diet?.daily7) ?? []
        let waterPoints = (is30Days ? summary?.water?.daily30 : summary?.water?.daily7) ?? []
        let supplementPoints = (is30Days ? summary?.supplements?.daily30 : summary?.supplements?.daily7) ?? []
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
                DataTrendCard(
                    title: appText("Diet Trend", appLanguageRaw),
                    value: trendAverageLabel(
                        value: is30Days ? summary?.diet?.last30AvgCalories : summary?.diet?.last7AvgCalories,
                        unit: "kcal"
                    ),
                    color: .orange,
                    points: dietPoints.map(\.calories)
                )
                DataTrendCard(
                    title: appText("Water Trend", appLanguageRaw),
                    value: trendAverageLabel(
                        value: is30Days ? summary?.water?.last30AvgMl : summary?.water?.last7AvgMl,
                        unit: "ml"
                    ),
                    color: .cyan,
                    points: waterPoints.map { Double($0.totalMl) }
                )
                DataTrendCard(
                    title: appText("Supplement Trend", appLanguageRaw),
                    value: trendAverageLabel(
                        value: is30Days ? summary?.supplements?.last30AvgPerDay : summary?.supplements?.last7AvgPerDay,
                        unit: "/day"
                    ),
                    color: .teal,
                    points: supplementPoints.map { Double($0.count) }
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

    private func trendAverageLabel(value: Double?, unit: String) -> String {
        "\(appText("Avg", appLanguageRaw)) \(formatCompactNumber(value ?? 0))\(appText(unit, appLanguageRaw))"
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
                    WorkspaceGuidanceCard(row: row)
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
                        dataActionCard(card)
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

    private func dataActionCard(_ card: ActionCardSummary) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "checkmark.seal.fill")
                .font(.callout)
                .foregroundStyle(.white)
                .frame(width: 28, height: 28)
                .background(Color.teal.opacity(0.85), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 6) {
                Text(card.title)
                    .font(.callout.weight(.semibold))
                    .lineLimit(2)
                HStack(spacing: 8) {
                    if let status = card.status {
                        Text(status)
                    }
                    if let priority = card.priority {
                        Text("P\(priority)")
                    }
                }
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.teal.opacity(0.075), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
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
                                Text(appText("Genetic Import Coverage", appLanguageRaw))
                                    .font(.callout.weight(.semibold))
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
                                        Text(category.category)
                                            .font(.callout.weight(.semibold))
                                            .lineLimit(1)
                                        Spacer()
                                    }
                                    Text("\(category.count) variants")
                                        .font(.title3.weight(.bold).monospacedDigit())
                                    Text("H \(category.highRiskCount) · M \(category.mediumRiskCount)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    HStack(spacing: 8) {
                                        Button {
                                            selectedGenomicDetail = .category(category)
                                        } label: {
                                            Label(appText("View Detail", appLanguageRaw), systemImage: "doc.text.magnifyingglass")
                                        }
                                        .buttonStyle(.bordered)
                                        .controlSize(.small)
                                        if let onAskAgent {
                                            Button {
                                                onAskAgent(genomicCategoryPrompt(category), genomicCategoryContext(category))
                                            } label: {
                                                Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                                            }
                                            .buttonStyle(.borderedProminent)
                                            .controlSize(.small)
                                        }
                                        if let onAddContext {
                                            Button {
                                                onAddContext(genomicCategoryContext(category))
                                            } label: {
                                                Label(appText("Add Context", appLanguageRaw), systemImage: "tray.and.arrow.down")
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
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: 10)], spacing: 10) {
                        ForEach(findings.prefix(8)) { finding in
                            VStack(alignment: .leading, spacing: 10) {
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
        - 位点性质：\(finding.variantNature ?? "unknown")
        - 描述：\(finding.description ?? "无")
        """
    }

    private func genomicCategoryPrompt(_ category: GenomicCategorySummary) -> String {
        """
        请基于我的真实基因报告，围绕 \(category.category) 这个分类做一次风险分层和行动建议。不要把基因结果当成诊断；请按优先级列出需要结合的数据、可执行生活方式动作、复查指标和不确定性边界。

        分类摘要：
        - 分类：\(category.category)
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
                "category": finding.category ?? "",
                "variant_nature": finding.variantNature ?? ""
            ]
        )
    }

    private func genomicCategoryContext(_ category: GenomicCategorySummary) -> AgentContextItem {
        AgentContextItem(
            sourceID: "genomic_category:\(category.category)",
            sourceKind: "genomic_category",
            title: category.category,
            summary: "\(category.count) variants · H \(category.highRiskCount) · M \(category.mediumRiskCount)",
            payload: [
                "category": category.category,
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
                Text((finding.riskLevel ?? "info").uppercased())
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
                    Text(category.category)
                        .font(.headline)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button(appText("Close", appLanguageRaw)) {
                    dismiss()
                }
            }

            HStack(spacing: 10) {
                categoryMetric("Variants", "\(category.count)", .purple)
                categoryMetric("High Risk", "\(category.highRiskCount)", .red)
                categoryMetric("Medium Risk", "\(category.mediumRiskCount)", .orange)
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
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    var onAddContext: ((AgentContextItem) -> Void)?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                WorkspaceOverviewView(
                    viewModel: viewModel,
                    kind: kind,
                    onAskAgent: onAskAgent,
                    onAddContext: onAddContext
                )
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
                    .lineLimit(2)
            }
            Divider()
            Button(appText("Open Today", appLanguageRaw)) {
                navigation.selection = .today
                openWindow(id: "main")
            }
            Button(appText("Open Record", appLanguageRaw)) {
                navigation.selection = .record
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
                quickRecordMessage = result.message
                sendMenuBarNotification(title: appText("Saved", appLanguageRaw), body: result.message)
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
