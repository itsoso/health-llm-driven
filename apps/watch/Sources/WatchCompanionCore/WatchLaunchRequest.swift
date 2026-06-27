import Foundation

public enum WatchLaunchSurface: String, Equatable, Sendable {
    case assistant
    case quickRecord = "quick_record"
}

public enum WatchLaunchRequest {
    public static let defaultsKey = "reva.watch.launch.surface"
    public static let notificationName = Notification.Name("reva.watch.launch.requested")
    public static let urlScheme = "reva-watch"

    public static func mark(
        _ surface: WatchLaunchSurface,
        in defaults: UserDefaults = .standard,
        notificationCenter: NotificationCenter = .default
    ) {
        defaults.set(surface.rawValue, forKey: defaultsKey)
        notificationCenter.post(name: notificationName, object: surface.rawValue)
    }

    public static func consume(from defaults: UserDefaults = .standard) -> WatchLaunchSurface? {
        guard let raw = defaults.string(forKey: defaultsKey),
              let surface = WatchLaunchSurface(rawValue: raw)
        else {
            defaults.removeObject(forKey: defaultsKey)
            return nil
        }
        defaults.removeObject(forKey: defaultsKey)
        return surface
    }

    public static func url(for surface: WatchLaunchSurface) -> URL {
        URL(string: "\(urlScheme)://\(surface.rawValue)")!
    }

    public static func surface(from url: URL) -> WatchLaunchSurface? {
        guard url.scheme == urlScheme else { return nil }
        let raw = url.host?.isEmpty == false ? url.host : url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let raw else { return nil }
        return WatchLaunchSurface(rawValue: raw)
    }
}
