import SwiftUI
import HealthAgentMacCore

/// 日程 —— 把「今日时间线 · 议程 · 日历」三个同属"日程/排期"域的视图合并进一个分段切换容器。
/// 三者各自的独有能力都完整保留,只是从三个侧栏入口收进一个入口的标签页:
///   - 时间线:唯一的 24h 逐时网格 + "现在"线(schedule + calendar 合并)
///   - 议程:唯一可勾选「完成」的结构化任务(protocol/follow-up/训练闸)
///   - 日历:唯一的日历源管理(ICS/CalDAV 增删同步)+ 月/周/年总览
/// 复用 SidebarDestination 作为标签标识,子视图与 AppRootView.detailView 里的构造完全一致。
struct ScheduleView: View {
    let services: AppServices
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var tab: SidebarDestination = .timeline

    private var language: AppLanguage { AppLanguage(storedValue: appLanguageRaw) }

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $tab) {
                Text(L10n.text("Timeline", language: language)).tag(SidebarDestination.timeline)
                Text(L10n.text("Agenda", language: language)).tag(SidebarDestination.agenda)
                Text(L10n.text("Calendar", language: language)).tag(SidebarDestination.calendar)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            Divider()

            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder
    private var content: some View {
        switch tab {
        case .agenda:
            AgendaView(client: services.agendaClient)
        case .calendar:
            CalendarView(client: services.calendarClient)
        default:  // .timeline
            DayTimelineView(
                scheduleClient: services.scheduleClient,
                calendarClient: services.calendarClient
            )
        }
    }
}
