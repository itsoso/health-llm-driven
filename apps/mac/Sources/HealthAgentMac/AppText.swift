import HealthAgentMacCore

func appText(_ key: String, _ rawLanguage: String) -> String {
    L10n.text(key, language: AppLanguage(storedValue: rawLanguage))
}

/// User-safe error detail for the UI — never surfaces raw HTML/overlong system
/// text. See `ErrorPresentation`.
func userFacingError(_ error: Error, _ rawLanguage: String) -> String {
    ErrorPresentation.detail(error, language: AppLanguage(storedValue: rawLanguage))
}
