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
    private let dynamicViewService: TodayDynamicViewServicing?

    public private(set) var bootstrap: DesktopBootstrap?
    public private(set) var topActions: [DailyPlanAction] = []
    public private(set) var activeJobs: [DesktopJobSummary] = []
    public private(set) var errorMessage: String?
    public private(set) var isLoading = false

    public init(service: DesktopBootstrapServicing, dynamicViewService: TodayDynamicViewServicing? = nil) {
        self.service = service
        self.dynamicViewService = dynamicViewService
    }

    public func refresh() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let payload = try await service.fetchBootstrap()
            bootstrap = payload
            topActions = await preferredMenuBarActions(fallback: payload.menuBarActions)
            activeJobs = payload.activeJobs
        } catch is CancellationError {
            // 视图生命周期取消(打开时 .task 被更新的刷新替换)不是错误——
            // 静默保留旧数据,不给用户亮红横幅(2026-07-13 founder 实锤:-999 已取消 上屏)。
            return
        } catch let urlError as URLError where urlError.code == .cancelled {
            // URLSession 的 -999 (NSURLErrorCancelled) — 同一类良性取消(镜像 chat VM 处理)。
            return
        } catch {
            AppLogger.dashboard.error("desktop bootstrap fetch failed: \(error.localizedDescription, privacy: .public)")
            // 用户可见文案用人话 localizedDescription;NSError 全文只进日志。
            errorMessage = error.localizedDescription
        }
    }

    private func preferredMenuBarActions(fallback: [DailyPlanAction]) async -> [DailyPlanAction] {
        guard let dynamicViewService else {
            return fallback
        }
        do {
            let view = try await dynamicViewService.fetchTodayDynamicView(trigger: "open")
            let dynamicActions = view.menuBarActions
            return dynamicActions.isEmpty ? fallback : dynamicActions
        } catch {
            AppLogger.dashboard.warning("today dynamic view fetch failed, falling back to desktop bootstrap: \(error.localizedDescription, privacy: .public)")
            return fallback
        }
    }
}

private extension DesktopBootstrap {
    var menuBarActions: [DailyPlanAction] {
        let planActions = Array(dailyPlan.actions.prefix(3))
        if !planActions.isEmpty {
            return planActions
        }
        return actionCards
            .sorted { ($0.priority ?? 0) > ($1.priority ?? 0) }
            .prefix(3)
            .map {
                DailyPlanAction(
                    actionKey: "action-card-\($0.id)",
                    title: $0.title,
                    domain: "action_card"
                )
            }
    }
}
