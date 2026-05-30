import Foundation

/// Turns an arbitrary `Error` into a short, user-safe detail string for the UI.
/// `APIError` already carries friendly Chinese copy (incl. the 5xx-generic /
/// HTML-stripping logic); for everything else we sanitize the raw
/// `localizedDescription` so markup or overlong system text never reaches the
/// user, falling back to a generic message when it isn't presentable.
public enum ErrorPresentation {
    public static func detail(_ error: Error, language: AppLanguage) -> String {
        if let apiError = error as? APIError {
            return apiError.errorDescription ?? generic(language)
        }
        let raw = (error as NSError).localizedDescription.trimmingCharacters(in: .whitespacesAndNewlines)
        if raw.isEmpty || raw.contains("<") || raw.contains(">") || raw.count > 200 {
            return generic(language)
        }
        return raw
    }

    private static func generic(_ language: AppLanguage) -> String {
        L10n.text("Something went wrong. Please try again.", language: language)
    }
}
