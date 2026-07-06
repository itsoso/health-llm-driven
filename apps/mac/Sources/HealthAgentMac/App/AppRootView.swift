import SwiftUI
import HealthAgentMacCore

struct AppRootView: View {
    let services: AppServices
    @Bindable private var navigation: AppNavigationState
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var hasCheckedAuth = false
    @State private var isAuthenticated = false
    @State private var currentUser: AuthUser?
    @State private var safetyMonitor: SafetyMonitor?

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
                    Task { await loadCurrentUser() }
                    startSafetyMonitor()
                }
            } else {
                NavigationSplitView {
                    if let currentUser {
                        SidebarAccountHeader(user: currentUser)
                    }
                    List(selection: $navigation.selection) {
                        ForEach(SidebarDestination.sidebarSections) { section in
                            Section {
                                ForEach(section.items) { destination in
                                    sidebarRow(destination)
                                        .tag(destination)
                                        .listRowBackground(sidebarRowBackground(destination))
                                }
                            } header: {
                                if !section.titleKey.isEmpty {
                                    Text(section.title(language: AppLanguage(storedValue: appLanguageRaw)))
                                }
                            }
                        }
                        // Settings pinned at the bottom, set off by a headerless section.
                        Section {
                            sidebarRow(.settings)
                                .tag(SidebarDestination.settings)
                                .listRowBackground(sidebarRowBackground(.settings))
                        }
                    }
                    .listStyle(.sidebar)
                    // 侧栏选中行高亮从系统蓝改为暖陶土(WarmPalette.clay,#C96442 light /
                    // #D9784F warm-dark)。macOS 的 .sidebar List 默认用系统强调色画选中背景,
                    // 焦点态会露出系统蓝;这里用显式 .listRowBackground 给选中行铺一层 clay,
                    // 无论窗口是否 key、明暗模式,选中态都稳定呈现 redesign 的暖陶土。
                    // .tint 让选中行文字/图标在 clay 底上仍走 accent 语义。未选中行透明,不变。
                    .tint(WarmPalette.clay)
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
            if isAuthenticated {
                startSafetyMonitor()
                await loadCurrentUser()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .authSessionExpired)) { _ in
            // A request hit 401 and cleared the token; drop back to login so the
            // user isn't stranded in a logged-in shell where everything fails.
            isAuthenticated = false
            currentUser = nil
            navigation.selection = .agent
        }
        .onChange(of: navigation.refreshTick) { _, _ in
            // ⌘R: refresh the shared dashboard data backing most pages.
            Task { await services.todayViewModel.refresh() }
        }
        .sheet(isPresented: $navigation.isCommandPalettePresented) {
            CommandPaletteView(
                commands: DesktopCommandPalette.defaultCommands(language: AppLanguage(storedValue: appLanguageRaw)),
                onSelect: handleCommand
            )
        }
    }

    private func loadCurrentUser() async {
        currentUser = try? await services.authClient.currentUser()
    }

    private func startSafetyMonitor() {
        if safetyMonitor == nil {
            safetyMonitor = SafetyMonitor(
                safetyClient: services.safetyClient,
                navigation: services.navigation
            )
        }
        safetyMonitor?.start()
        services.quickCaptureManager.install()
    }

    /// One sidebar row: localized label + icon, plus the agent context-basket badge.
    /// Selected rows sit on a clay `.listRowBackground`, so their label + icon flip
    /// to white for contrast; unselected rows keep the default warm-ink foreground.
    @ViewBuilder
    private func sidebarRow(_ destination: SidebarDestination) -> some View {
        let isSelected = navigation.selection == destination
        HStack(spacing: 6) {
            Label(destination.title(language: AppLanguage(storedValue: appLanguageRaw)), systemImage: destination.systemImage)
                .foregroundStyle(isSelected ? Color.white : Color.primary)
            if destination == .agent {
                let basketCount = services.agentViewModel.contextItems.count
                if basketCount > 0 {
                    Text("\(basketCount)")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(isSelected ? WarmPalette.clay : Color.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 1)
                        .background(isSelected ? Color.white : WarmPalette.clay, in: Capsule())
                        .help(appText("Items waiting in the context basket.", appLanguageRaw))
                }
            }
        }
    }

    /// Selected sidebar row → clay fill (redesign accent). Unselected → clear, so the
    /// default `.sidebar` list chrome (headers, hover) is untouched. Clay carries its
    /// own light/warm-dark values, so this is correct in both appearances.
    private func sidebarRowBackground(_ destination: SidebarDestination) -> Color {
        navigation.selection == destination ? WarmPalette.clay : Color.clear
    }

    @ViewBuilder
    private var detailView: some View {
        switch navigation.selection ?? .agent {
        case .today:
            TodayView(
                viewModel: services.todayViewModel,
                briefingClient: services.briefingClient,
                nocturnalClient: services.nocturnalClient,
                onAskAgent: askAgentWithContext,
                onAddContext: addAgentContext
            )
        case .schedule:
            ScheduleView(services: services)
        case .agenda:
            AgendaView(client: services.agendaClient)
        case .review, .liver, .healthExtras:
            // 三者收进「健康洞察」hub;hub 用当前 selection 预选对应标签页。
            InsightsHubView(
                services: services,
                navigation: navigation,
                onAskAgent: askAgentWithContext
            )
        case .timeline:
            DayTimelineView(
                scheduleClient: services.scheduleClient,
                calendarClient: services.calendarClient
            )
        case .calendar:
            CalendarView(client: services.calendarClient)
        case .agent:
            AgentChatView(viewModel: services.agentViewModel, navigation: navigation)
        case .record:
            RecordHubView(
                client: services.recordClient,
                productClient: services.supplementProductClient,
                labUploadClient: services.labUploadClient,
                viewModel: services.todayViewModel,
                onAskAgent: askAgentWithContext
            )
        case .jobs:
            JobListView(client: services.desktopJobClient, viewModel: services.todayViewModel) { conversationID in
                navigation.openTrace(conversationID: conversationID)
            }
        case .trace:
            TraceLookupView(client: services.traceClient, navigation: navigation)
        case .dataSources:
            DataSourcesView(client: services.deviceSourcesClient, onAskAgent: askAgentWithContext)
        case .dataConnections:
            DataConnectionsView(client: services.dataConnectionsClient, onAskAgent: askAgentWithContext)
        case .prescriptions:
            OriginatorView(client: services.originatorClient, onAskAgent: askAgentWithContext)
        case .data:
            WorkspaceOverviewView(
                viewModel: services.todayViewModel,
                jobClient: services.desktopJobClient,
                kind: .data,
                nocturnalClient: services.nocturnalClient,
                garminTrendClient: services.garminTrendClient,
                labClient: services.labClient,
                interventionsClient: services.interventionsClient,
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
        case .workouts:
            WorkoutsView(client: services.workoutClient, onAskAgent: askAgentWithContext)
        case .goals:
            GoalsView(client: services.goalClient, onAskAgent: askAgentWithContext)
        case .settings:
            SettingsView(authClient: services.authClient, tokenStore: services.tokenProvider) {
                isAuthenticated = false
                currentUser = nil
                navigation.selection = .agent
            }
        }
    }

    /// A card "提问 / Ask Agent" action: open a FRESH conversation (Fix B — saves
    /// context/tokens, mirrors the web contract) and drop the clean question into
    /// the composer input, ready to send (Fix A). The card prompts are already
    /// self-contained (they inline the metric/finding data), so we deliberately do
    /// NOT push `item` into the 已选上下文 basket here — that regression turned a
    /// question into a silent context chip + a wall of "### 当前上下文" text. The
    /// context-package panel stays a first-class feature via the separate explicit
    /// "Add Context" button (`addAgentContext`), which is untouched.
    private func askAgentWithContext(_ prompt: String, _ item: AgentContextItem?) {
        _ = item // intentionally not injected as a context chip; see note above.
        services.agentViewModel.prepareDraftForNewConversation(prompt, contextItems: [])
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
            services.agentViewModel.prepareDraftForNewConversation(
                "请结合最近健康记录、基因、知识库证据和不确定性边界，给出可执行建议。",
                contextItems: services.agentViewModel.contextItems
            )
            navigation.selection = .agent
        case .refresh:
            Task { await services.todayViewModel.refresh() }
        case .newAgentConversation:
            services.agentViewModel.startNewConversation()
            navigation.selection = .agent
        case .askPrompt(let prompt):
            services.agentViewModel.prepareDraftForNewConversation(
                prompt,
                contextItems: services.agentViewModel.contextItems
            )
            navigation.selection = .agent
        case .startQuickRecord:
            navigation.selection = .record
        }
    }
}

/// Compact identity strip pinned above the sidebar list so the logged-in
/// account is always visible — important on a shared Mac where it's easy to
/// forget whose session is active.
private struct SidebarAccountHeader: View {
    let user: AuthUser
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    private var primaryLabel: String { user.name ?? user.username }
    private var secondaryLabel: String? {
        let secondary = user.email ?? (user.name != nil ? user.username : nil)
        return secondary == primaryLabel ? nil : secondary
    }

    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: "person.crop.circle.fill")
                .font(.title2)
                .foregroundStyle(WarmPalette.clay)
            VStack(alignment: .leading, spacing: 1) {
                Text(primaryLabel)
                    .font(.callout.weight(.semibold))
                    .lineLimit(1)
                if let secondaryLabel {
                    Text(secondaryLabel)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12)
        .padding(.top, 10)
        .padding(.bottom, 4)
        .help(appText("Open Settings to switch account.", appLanguageRaw))
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
