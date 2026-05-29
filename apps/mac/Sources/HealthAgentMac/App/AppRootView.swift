import SwiftUI
import HealthAgentMacCore

struct AppRootView: View {
    let services: AppServices
    @Bindable private var navigation: AppNavigationState
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var hasCheckedAuth = false
    @State private var isAuthenticated = false
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
                    startSafetyMonitor()
                }
            } else {
                NavigationSplitView {
                    List(SidebarDestination.sidebarVisible, selection: $navigation.selection) { destination in
                        HStack(spacing: 6) {
                            Label(destination.title(language: AppLanguage(storedValue: appLanguageRaw)), systemImage: destination.systemImage)
                            if destination == .agent {
                                let basketCount = services.agentViewModel.contextItems.count
                                if basketCount > 0 {
                                    Text("\(basketCount)")
                                        .font(.caption2.weight(.bold))
                                        .foregroundStyle(.white)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 1)
                                        .background(Color.accentColor, in: Capsule())
                                        .help(appText("Items waiting in the context basket.", appLanguageRaw))
                                }
                            }
                        }
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
            if isAuthenticated { startSafetyMonitor() }
        }
        .sheet(isPresented: $navigation.isCommandPalettePresented) {
            CommandPaletteView(
                commands: DesktopCommandPalette.defaultCommands(language: AppLanguage(storedValue: appLanguageRaw)),
                onSelect: handleCommand
            )
        }
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

    @ViewBuilder
    private var detailView: some View {
        switch navigation.selection ?? .today {
        case .today:
            TodayView(
                viewModel: services.todayViewModel,
                briefingClient: services.briefingClient,
                nocturnalClient: services.nocturnalClient,
                onAskAgent: askAgentWithContext,
                onAddContext: addAgentContext
            )
        case .agent:
            AgentChatView(viewModel: services.agentViewModel)
        case .record:
            RecordHubView(
                client: services.recordClient,
                productClient: services.supplementProductClient,
                viewModel: services.todayViewModel,
                onAskAgent: askAgentWithContext
            )
        case .jobs:
            JobListView(client: services.desktopJobClient, viewModel: services.todayViewModel) { conversationID in
                navigation.openTrace(conversationID: conversationID)
            }
        case .trace:
            TraceLookupView(client: services.traceClient, navigation: navigation)
        case .data:
            WorkspaceOverviewView(
                viewModel: services.todayViewModel,
                jobClient: services.desktopJobClient,
                kind: .data,
                nocturnalClient: services.nocturnalClient,
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
        case .settings:
            SettingsView(authClient: services.authClient, tokenStore: services.tokenProvider) {
                isAuthenticated = false
                navigation.selection = .today
            }
        }
    }

    private func askAgentWithContext(_ prompt: String, _ item: AgentContextItem?) {
        let currentContext = services.agentViewModel.contextItems
        let handoffContext = currentContext + (item.map { [$0] } ?? [])
        services.agentViewModel.prepareDraftForNewConversation(prompt, contextItems: handoffContext)
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
