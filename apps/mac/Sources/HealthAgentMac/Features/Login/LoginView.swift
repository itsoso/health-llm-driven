import SwiftUI
import HealthAgentMacCore

struct LoginView: View {
    let authClient: AuthClient
    let onLogin: () -> Void
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var username = ""
    @State private var password = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 20) {
            VStack(spacing: 8) {
                Image(systemName: "heart.text.square.fill")
                    .font(.system(size: 44))
                    .foregroundStyle(Color.accentColor)
                Text(appText("Health Agent", appLanguageRaw))
                    .font(.largeTitle.bold())
                Text(appText("Sign in with your executor.life account.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 12) {
                TextField(appText("Username or email", appLanguageRaw), text: $username)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { submitIfReady() }
                SecureField(appText("Password", appLanguageRaw), text: $password)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { submitIfReady() }

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                }

                Button {
                    submitIfReady()
                } label: {
                    Label(appText(isSubmitting ? "Signing in..." : "Sign In", appLanguageRaw), systemImage: "person.crop.circle.badge.checkmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(isSubmitting || username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || password.isEmpty)
                .keyboardShortcut(.return, modifiers: .command)
            }
            .frame(width: 360)
        }
        .padding(36)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func submitIfReady() {
        guard !isSubmitting else { return }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty, !password.isEmpty else { return }
        Task { await signIn(username: trimmedUsername, password: password) }
    }

    private func signIn(username: String, password: String) async {
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }
        do {
            _ = try await authClient.login(username: username, password: password)
            self.password = ""
            onLogin()
        } catch APIError.unauthorized {
            errorMessage = "用户名或密码错误。"
        } catch APIError.httpStatus(let status, let message) {
            errorMessage = message.map { "登录失败，HTTP \(status)：\($0)" } ?? "登录失败，HTTP \(status)。"
        } catch {
            errorMessage = "登录失败：\(error.localizedDescription)"
        }
    }
}
