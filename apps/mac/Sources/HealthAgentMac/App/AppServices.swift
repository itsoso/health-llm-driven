import Foundation
import HealthAgentMacCore

@MainActor
@Observable
final class AppNavigationState {
    var selection: SidebarDestination? = .agent  // 小巴(助手)= 默认第一入口
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
    let garminTrendClient: GarminTrendClient
    let labClient: LabClient
    let labUploadClient: LabUploadClient
    let interventionsClient: InterventionsClient
    let workoutClient: WorkoutClient
    let goalClient: GoalClient
    let deviceSourcesClient: DeviceSourcesClient
    let dataConnectionsClient: DataConnectionsClient
    let agendaClient: AgendaClient
    let scheduleClient: ScheduleClient
    let calendarClient: CalendarClient
    let healthOperatingReviewClient: HealthOperatingReviewClient
    let originatorClient: OriginatorClient
    let liverHealthClient: LiverHealthClient
    let healthExtrasClient: HealthExtrasClient
    let quickCaptureManager: QuickCaptureManager

    @MainActor
    init() {
        AppPreferences.registerDefaults()
        let tokenProvider = UserDefaultsTokenStore()
        self.tokenProvider = tokenProvider
        let baseURL = APIEndpoint.resolvedBaseURL()
        let apiClient = APIClient(baseURL: baseURL, tokenProvider: tokenProvider)
        self.apiClient = apiClient
        let labUploadClient = LabUploadClient(apiClient: apiClient)
        self.labUploadClient = labUploadClient
        self.todayViewModel = TodayViewModel(
            service: DesktopBootstrapService(apiClient: apiClient),
            dynamicViewService: TodayDynamicViewClient(apiClient: apiClient)
        )
        self.agentViewModel = AgentChatViewModel(
            streamService: AgentStreamClient(baseURL: baseURL, tokenProvider: tokenProvider),
            contextBundleStore: UserDefaultsAgentContextBundleStore(),
            conversationStore: UserDefaultsAgentConversationStore(),
            // Backend conversation list/detail so Mac matches web/mobile; the local
            // store above is now only the offline fallback.
            remoteSource: AgentConversationClient(apiClient: apiClient),
            labUploadService: labUploadClient,
            aigcMediaClient: AIGCMediaJobClient(apiClient: apiClient)
        )
        self.recordClient = RecordClient(apiClient: apiClient)
        self.supplementProductClient = SupplementProductLibraryClient(apiClient: apiClient)
        self.desktopJobClient = DesktopJobClient(apiClient: apiClient)
        self.traceClient = TraceClient(apiClient: apiClient)
        self.authClient = AuthClient(apiClient: apiClient, tokenStore: tokenProvider)
        self.safetyClient = SafetyClient(apiClient: apiClient)
        self.briefingClient = BriefingClient(apiClient: apiClient)
        self.nocturnalClient = NocturnalTimeseriesClient(apiClient: apiClient)
        self.garminTrendClient = GarminTrendClient(apiClient: apiClient)
        self.labClient = LabClient(apiClient: apiClient)
        self.interventionsClient = InterventionsClient(apiClient: apiClient)
        self.workoutClient = WorkoutClient(apiClient: apiClient)
        self.goalClient = GoalClient(apiClient: apiClient)
        self.deviceSourcesClient = DeviceSourcesClient(apiClient: apiClient)
        self.dataConnectionsClient = DataConnectionsClient(apiClient: apiClient)
        self.agendaClient = AgendaClient(apiClient: apiClient)
        self.scheduleClient = ScheduleClient(apiClient: apiClient)
        self.calendarClient = CalendarClient(apiClient: apiClient)
        self.healthOperatingReviewClient = HealthOperatingReviewClient(apiClient: apiClient)
        self.originatorClient = OriginatorClient(apiClient: apiClient)
        self.liverHealthClient = LiverHealthClient(apiClient: apiClient)
        self.healthExtrasClient = HealthExtrasClient(apiClient: apiClient)
        self.quickCaptureManager = QuickCaptureManager(recordClient: recordClient)
    }
}
