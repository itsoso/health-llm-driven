import HealthAgentMacCore

func appText(_ key: String, _ rawLanguage: String) -> String {
    L10n.text(key, language: AppLanguage(storedValue: rawLanguage))
}
