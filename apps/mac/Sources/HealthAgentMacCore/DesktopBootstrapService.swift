import Foundation
import Observation

public protocol DesktopBootstrapServicing: Sendable {
    func fetchBootstrap() async throws -> DesktopBootstrap
}

public struct DesktopBootstrapService: DesktopBootstrapServicing {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchBootstrap() async throws -> DesktopBootstrap {
        try await apiClient.get("desktop/bootstrap")
    }
}

@Observable
@MainActor
public final class TodayViewModel {
    private let service: DesktopBootstrapServicing

    public private(set) var bootstrap: DesktopBootstrap?
    public private(set) var topActions: [DailyPlanAction] = []
    public private(set) var activeJobs: [DesktopJobSummary] = []
    public private(set) var errorMessage: String?
    public private(set) var isLoading = false

    public init(service: DesktopBootstrapServicing) {
        self.service = service
    }

    public func refresh() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let payload = try await service.fetchBootstrap()
            bootstrap = payload
            topActions = Array(payload.dailyPlan.actions.prefix(3))
            activeJobs = payload.activeJobs
        } catch {
            errorMessage = String(describing: error)
        }
    }
}
