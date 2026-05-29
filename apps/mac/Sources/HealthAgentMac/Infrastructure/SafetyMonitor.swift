import Foundation
@preconcurrency import UserNotifications
import HealthAgentMacCore

@MainActor
final class SafetyMonitor: NSObject, UNUserNotificationCenterDelegate {
    private let safetyClient: SafetyClient
    private let navigation: AppNavigationState
    private var task: Task<Void, Never>?
    private var seenAlertIDs = Set<String>()
    private var notificationsAuthorized = false
    private var authorizationRequested = false

    init(safetyClient: SafetyClient, navigation: AppNavigationState) {
        self.safetyClient = safetyClient
        self.navigation = navigation
        super.init()
        UNUserNotificationCenter.current().delegate = self
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .list])
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo
        if userInfo["rule_id"] is String {
            Task { @MainActor [weak self] in
                self?.navigation.selection = .today
            }
        }
        completionHandler()
    }

    func start() {
        guard task == nil else { return }
        ensureAuthorization()
        task = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                await self?.pollOnce()
                try? await Task.sleep(nanoseconds: 5 * 60 * 1_000_000_000)
            }
        }
    }

    func stop() {
        task?.cancel()
        task = nil
        seenAlertIDs.removeAll()
    }

    private func ensureAuthorization() {
        guard !authorizationRequested else { return }
        authorizationRequested = true
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { [weak self] granted, _ in
            Task { @MainActor in
                self?.notificationsAuthorized = granted
            }
        }
    }

    private func pollOnce() async {
        do {
            let report = try await safetyClient.fetchReport()
            await processReport(report)
        } catch {
            // Silent retry on next tick — UI deliberately stays clean (no banner for a failed poll).
            // Logged so failures surface in Console.app instead of vanishing.
            AppLogger.safety.error("safety poll failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func processReport(_ report: SafetyReport) async {
        let alerts = report.alerts.filter { $0.severity >= 2 }
        let newAlerts = alerts.filter { !seenAlertIDs.contains($0.rule_id) }
        for alert in newAlerts { seenAlertIDs.insert(alert.rule_id) }

        // Only send notifications for High (3) and Critical (4) tier — Medium stays passive.
        let urgent = newAlerts.filter { $0.severity >= 3 }
        guard !urgent.isEmpty, notificationsAuthorized else { return }

        for alert in urgent {
            postNotification(alert)
        }
    }

    private func postNotification(_ alert: SafetyAlert) {
        let content = UNMutableNotificationContent()
        content.title = "[\(alert.severityLabel)] \(alert.title)"
        content.body = alert.message ?? alert.action ?? ""
        content.sound = .default
        content.userInfo = ["rule_id": alert.rule_id]

        let trigger = quietHoursTrigger(now: Date())
        let identifier: String
        if trigger != nil {
            // Stable id during quiet hours so re-polls within the same night don't pile up duplicates.
            let dateKey = SafetyMonitor.quietHoursDateKey(for: Date())
            identifier = "safety.\(alert.rule_id).quiet.\(dateKey)"
        } else {
            identifier = "safety.\(alert.rule_id).\(Int(Date().timeIntervalSince1970))"
        }

        let request = UNNotificationRequest(
            identifier: identifier,
            content: content,
            trigger: trigger
        )
        UNUserNotificationCenter.current().add(request)
    }

    // 22:00 – 08:30 local time: defer notifications to 08:30 so they don't wake the user.
    // Memory: "推送严格不打扰睡眠" (2026-05-11). All severities (incl. Critical) are deferred.
    private func quietHoursTrigger(now: Date) -> UNNotificationTrigger? {
        let calendar = Calendar.current
        let comps = calendar.dateComponents([.hour, .minute], from: now)
        guard let hour = comps.hour, let minute = comps.minute else { return nil }
        let totalMinutes = hour * 60 + minute
        let quietStart = 22 * 60       // 22:00
        let quietEnd = 8 * 60 + 30     // 08:30
        let isQuiet = totalMinutes >= quietStart || totalMinutes < quietEnd
        if !isQuiet { return nil }

        // Compute next 08:30 in local calendar.
        var target = calendar.dateComponents([.year, .month, .day], from: now)
        target.hour = 8
        target.minute = 30
        target.second = 0
        guard var fireDate = calendar.date(from: target) else { return nil }
        if fireDate <= now {
            // It's after midnight but before 08:30 — same day. If we computed 08:30 today and it's already
            // past, push to tomorrow.
            fireDate = calendar.date(byAdding: .day, value: 1, to: fireDate) ?? fireDate
        }
        // If we're in the 22:00-23:59 window, fireDate is today's 08:30 (already passed); push to tomorrow.
        if totalMinutes >= quietStart {
            fireDate = calendar.date(byAdding: .day, value: 1, to: calendar.date(from: target) ?? now) ?? fireDate
        }

        let fireComps = calendar.dateComponents([.year, .month, .day, .hour, .minute], from: fireDate)
        return UNCalendarNotificationTrigger(dateMatching: fireComps, repeats: false)
    }

    private static func quietHoursDateKey(for date: Date) -> String {
        let calendar = Calendar.current
        let comps = calendar.dateComponents([.hour], from: date)
        let hour = comps.hour ?? 0
        // Nights are keyed by the calendar date their 22:00 started on, so 02:00 still maps to the previous day.
        let base: Date
        if hour < 12 {
            base = calendar.date(byAdding: .day, value: -1, to: date) ?? date
        } else {
            base = date
        }
        let dayComps = calendar.dateComponents([.year, .month, .day], from: base)
        return String(format: "%04d-%02d-%02d", dayComps.year ?? 0, dayComps.month ?? 0, dayComps.day ?? 0)
    }
}
