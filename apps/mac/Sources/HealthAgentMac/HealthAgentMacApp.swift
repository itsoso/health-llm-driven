import HealthAgentMacCore
import SwiftUI

@main
struct HealthAgentMacApp: App {
    @State private var appServices = AppServices()
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some Scene {
        WindowGroup(id: "main") {
            AppRootView(services: appServices)
        }
        MenuBarExtra(appText("Health Agent", appLanguageRaw), systemImage: "heart.text.square") {
            MenuBarRootView(
                viewModel: appServices.todayViewModel,
                navigation: appServices.navigation
            )
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
            }
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
    let tokenProvider: KeychainTokenStore
    let navigation = AppNavigationState()
    let apiClient: APIClient
    let todayViewModel: TodayViewModel
    let agentViewModel: AgentChatViewModel
    let recordClient: RecordClient
    let desktopJobClient: DesktopJobClient
    let traceClient: TraceClient
    let authClient: AuthClient

    init() {
        let tokenProvider = KeychainTokenStore()
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

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(appText("Today", appLanguageRaw))
                            .font(.largeTitle.bold())
                        Text(appText("Daily operating plan, feedback, and active desktop jobs.", appLanguageRaw))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(appText("Refresh", appLanguageRaw)) {
                        Task { await viewModel.refresh() }
                    }
                }

                if viewModel.isLoading {
                    ProgressView(appText("Loading desktop context...", appLanguageRaw))
                }

                if let error = viewModel.errorMessage {
                    Text(error)
                        .foregroundStyle(.red)
                }

                SectionPanel(title: appText("Top Actions", appLanguageRaw), systemImage: "checklist") {
                    if viewModel.topActions.isEmpty {
                        Text(appText("No actions loaded yet.", appLanguageRaw))
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(viewModel.topActions) { action in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(action.title).font(.headline)
                                    if let domain = action.domain {
                                        Text(domain).font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                                Spacer()
                                Button(appText("Done", appLanguageRaw)) {}
                                Button(appText("Adjust", appLanguageRaw)) {}
                            }
                            Divider()
                        }
                    }
                }

                SectionPanel(title: appText("Active Jobs", appLanguageRaw), systemImage: "clock.arrow.circlepath") {
                    if viewModel.activeJobs.isEmpty {
                        Text(appText("No active desktop jobs.", appLanguageRaw))
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(viewModel.activeJobs) { job in
                            HStack {
                                Text(job.jobType)
                                Spacer()
                                Text(job.status)
                                ProgressView(value: Double(job.progress), total: 100)
                                    .frame(width: 120)
                            }
                        }
                    }
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
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 12)], spacing: 12) {
            ForEach(summary.metrics) { metric in
                VStack(alignment: .leading, spacing: 6) {
                    Text(metric.title)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(metric.value)
                        .font(.title2.bold())
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(14)
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
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
                ForEach(summary.recentMemory.prefix(5)) { memory in
                    Text(memory.objectValue)
                        .lineLimit(2)
                    Divider()
                }
            }
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
