import Foundation
import os

/// Single project-wide logger keyed by category. Wraps `os.Logger` so the
/// rest of the codebase doesn't need to import `os` or pick subsystem strings.
///
/// Why this exists: scattered `} catch { }` blocks silently lost network /
/// auth / decode failures. With this logger you can `AppLogger.network.error("…")`
/// and the failure shows up in Console.app under the bundle's subsystem,
/// without polluting the UI or blocking the surrounding flow.
public enum AppLogger {
    private static let subsystem = "life.executor.health.mac"

    public static let network = Logger(subsystem: subsystem, category: "network")
    public static let safety = Logger(subsystem: subsystem, category: "safety")
    public static let briefing = Logger(subsystem: subsystem, category: "briefing")
    public static let agent = Logger(subsystem: subsystem, category: "agent")
    public static let auth = Logger(subsystem: subsystem, category: "auth")
    public static let importer = Logger(subsystem: subsystem, category: "import")
    public static let record = Logger(subsystem: subsystem, category: "record")
    public static let dashboard = Logger(subsystem: subsystem, category: "dashboard")
    public static let nocturnal = Logger(subsystem: subsystem, category: "nocturnal")
    public static let labs = Logger(subsystem: subsystem, category: "labs")
    public static let interventions = Logger(subsystem: subsystem, category: "interventions")
    public static let general = Logger(subsystem: subsystem, category: "general")
}
