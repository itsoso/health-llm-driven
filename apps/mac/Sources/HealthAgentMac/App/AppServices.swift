import Foundation
import HealthAgentMacCore

@MainActor
@Observable
final class AppNavigationState {
    var selection: SidebarDestination? = .today
    var traceConversationID: Int?
    var isCommandPalettePresented = false
    /// Bumped by the ⌘R command; observed at the app root to refresh the
    /// shared dashboard data without coupling the menu to a specific view.
    var refreshTick = 0
    /// Bumped by ⌘N; observed by AgentChatView to start a fresh conversation
    /// (and clear its local composer draft, which the app layer can't reach).
    var newConversationTick = 0

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
    let supplementProductClient: SupplementProductLibraryClient
    let desktopJobClient: DesktopJobClient
    let traceClient: TraceClient
    let authClient: AuthClient
    let safetyClient: SafetyClient
    let briefingClient: BriefingClient
    let nocturnalClient: NocturnalTimeseriesClient
    let labClient: LabClient
    let interventionsClient: InterventionsClient
    let workoutClient: WorkoutClient
    let goalClient: GoalClient
    let quickCaptureManager: QuickCaptureManager

    @MainActor
    init() {
        AppPreferences.registerDefaults()
        let tokenProvider = UserDefaultsTokenStore()
        self.tokenProvider = tokenProvider
        let baseURL = APIEndpoint.resolvedBaseURL()
        self.apiClient = APIClient(baseURL: baseURL, tokenProvider: tokenProvider)
        self.todayViewModel = TodayViewModel(
            service: DesktopBootstrapService(apiClient: apiClient)
        )
        self.agentViewModel = AgentChatViewModel(
            streamService: AgentStreamClient(baseURL: baseURL, tokenProvider: tokenProvider),
            contextBundleStore: UserDefaultsAgentContextBundleStore(),
            conversationStore: UserDefaultsAgentConversationStore()
        )
        self.recordClient = RecordClient(apiClient: apiClient)
        self.supplementProductClient = SupplementProductLibraryClient(apiClient: apiClient)
        self.desktopJobClient = DesktopJobClient(apiClient: apiClient)
        self.traceClient = TraceClient(apiClient: apiClient)
        self.authClient = AuthClient(apiClient: apiClient, tokenStore: tokenProvider)
        self.safetyClient = SafetyClient(apiClient: apiClient)
        self.briefingClient = BriefingClient(apiClient: apiClient)
        self.nocturnalClient = NocturnalTimeseriesClient(apiClient: apiClient)
        self.labClient = LabClient(apiClient: apiClient)
        self.interventionsClient = InterventionsClient(apiClient: apiClient)
        self.workoutClient = WorkoutClient(apiClient: apiClient)
        self.goalClient = GoalClient(apiClient: apiClient)
        self.quickCaptureManager = QuickCaptureManager(recordClient: recordClient)
    }
}
