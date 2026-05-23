import HealthAgentMacCore
import SwiftUI

@main
struct HealthAgentMacApp: App {
    @State private var appServices = AppServices()

    var body: some Scene {
        WindowGroup {
            AppRootView(services: appServices)
        }
        MenuBarExtra("Health Agent", systemImage: "heart.text.square") {
            MenuBarRootView(viewModel: appServices.todayViewModel)
        }
    }
}

@MainActor
struct AppServices {
    let tokenProvider = KeychainTokenStore()
    let apiClient: APIClient
    let todayViewModel: TodayViewModel
    let agentViewModel: AgentChatViewModel
    let recordClient: RecordClient
    let desktopJobClient: DesktopJobClient
    let traceClient: TraceClient

    init() {
        let tokenProvider = KeychainTokenStore()
        self.apiClient = APIClient(tokenProvider: tokenProvider)
        self.todayViewModel = TodayViewModel(
            service: DesktopBootstrapService(apiClient: apiClient)
        )
        self.agentViewModel = AgentChatViewModel(
            streamService: AgentStreamClient(tokenProvider: tokenProvider)
        )
        self.recordClient = RecordClient(apiClient: apiClient)
        self.desktopJobClient = DesktopJobClient(apiClient: apiClient)
        self.traceClient = TraceClient(apiClient: apiClient)
    }
}

struct AppRootView: View {
    let services: AppServices
    @State private var selection: SidebarDestination? = .today

    var body: some View {
        NavigationSplitView {
            List(SidebarDestination.allCases, selection: $selection) { destination in
                Label(destination.title, systemImage: destination.systemImage)
                    .tag(destination)
            }
            .navigationTitle("Health Agent")
        } detail: {
            switch selection ?? .today {
            case .today:
                TodayView(viewModel: services.todayViewModel)
            case .agent:
                AgentChatView(viewModel: services.agentViewModel)
            case .record:
                RecordHubView(client: services.recordClient)
            case .jobs:
                JobListView(client: services.desktopJobClient)
            case .trace:
                TraceLookupView(client: services.traceClient)
            case .genetics, .knowledge:
                ImportCenterView(jobClient: services.desktopJobClient)
            default:
                ContentPlaceholder(destination: selection ?? .today)
            }
        }
        .frame(minWidth: 980, minHeight: 680)
    }
}

struct TodayView: View {
    @Bindable var viewModel: TodayViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Today")
                            .font(.largeTitle.bold())
                        Text("Daily operating plan, feedback, and active desktop jobs.")
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Refresh") {
                        Task { await viewModel.refresh() }
                    }
                }

                if viewModel.isLoading {
                    ProgressView("Loading desktop context...")
                }

                if let error = viewModel.errorMessage {
                    Text(error)
                        .foregroundStyle(.red)
                }

                SectionPanel(title: "Top Actions", systemImage: "checklist") {
                    if viewModel.topActions.isEmpty {
                        Text("No actions loaded yet.")
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
                                Button("Done") {}
                                Button("Adjust") {}
                            }
                            Divider()
                        }
                    }
                }

                SectionPanel(title: "Active Jobs", systemImage: "clock.arrow.circlepath") {
                    if viewModel.activeJobs.isEmpty {
                        Text("No active desktop jobs.")
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

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(destination.title, systemImage: destination.systemImage)
                .font(.title.bold())
            Text("Native macOS client surface backed by \(APIEndpoint.defaultBaseURL.absoluteString)")
                .foregroundStyle(.secondary)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

struct MenuBarRootView: View {
    @Bindable var viewModel: TodayViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Health Agent", systemImage: "heart.text.square")
                .font(.headline)
            Divider()
            if viewModel.topActions.isEmpty {
                Text("No actions loaded")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(viewModel.topActions.prefix(3)) { action in
                    Text(action.title)
                        .lineLimit(1)
                }
            }
            Divider()
            Button("Open Today") {}
            Button("Ask Agent") {}
            Button("Import File") {}
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
