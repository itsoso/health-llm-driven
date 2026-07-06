import SwiftUI
import HealthAgentMacCore

/// 健康洞察 hub —— 把三个同属「洞察/分析」域的视图收进一个分段切换容器,
/// 复用 ScheduleView 已验证的 Picker(.segmented) 模式:
///   - 复盘(.review):干预→指标→结论的预测回测(HealthOperatingReviewView)
///   - 进阶能力(.healthExtras):减药 / 社会连接 / 因果 / 数据自检 四合一(HealthExtrasView)
///   - 器官趋势(.liver):单器官化验趋势,结构上预留更多器官(LiverTrendView)
///
/// 三个子视图完整复用,不重写。`.review` / `.liver` / `.healthExtras` 三个
/// SidebarDestination 都渲染本 hub —— 只是把当前 selection 投影成初始标签页,
/// 这样命令面板 / 证据深链 / 动态卡片路由跳到 `.review` 或 `.liver` 时,hub 会
/// 直接打开对应标签,不会留下悬空 destination。
struct InsightsHubView: View {
    let services: AppServices
    let navigation: AppNavigationState
    let onAskAgent: (String, AgentContextItem?) -> Void

    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var tab: SidebarDestination

    private var language: AppLanguage { AppLanguage(storedValue: appLanguageRaw) }

    init(
        services: AppServices,
        navigation: AppNavigationState,
        onAskAgent: @escaping (String, AgentContextItem?) -> Void
    ) {
        self.services = services
        self.navigation = navigation
        self.onAskAgent = onAskAgent
        _tab = State(initialValue: Self.tab(for: navigation.selection))
    }

    /// 把当前 selection 收敛到三个合法标签之一;非洞察 selection 兜底到复盘。
    private static func tab(for selection: SidebarDestination?) -> SidebarDestination {
        switch selection {
        case .healthExtras: return .healthExtras
        case .liver: return .liver
        default: return .review
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $tab) {
                Text(L10n.text("Review", language: language)).tag(SidebarDestination.review)
                Text(L10n.text("Advanced Abilities", language: language)).tag(SidebarDestination.healthExtras)
                Text(L10n.text("Organ Trends", language: language)).tag(SidebarDestination.liver)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            Divider()

            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        // 深链:selection 在 hub 显示时被改到另一个洞察 destination(如证据链跳
        // .liver)→ 同步切到对应标签,而不是重建视图。
        .onChange(of: navigation.selection) { _, newValue in
            let mapped = Self.tab(for: newValue)
            if [.review, .healthExtras, .liver].contains(newValue), tab != mapped {
                tab = mapped
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch tab {
        case .liver:
            LiverTrendView(client: services.liverHealthClient, onAskAgent: onAskAgent)
        case .healthExtras:
            HealthExtrasView(client: services.healthExtrasClient, onAskAgent: onAskAgent)
        default:  // .review
            HealthOperatingReviewView(
                client: services.healthOperatingReviewClient,
                onAskAgent: onAskAgent
            )
        }
    }
}
