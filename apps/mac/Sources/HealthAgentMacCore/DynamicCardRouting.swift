import Foundation

/// 动态卡片 `route.open` 在 mac 端的解释(mac 没有 mobile 的 expo-router)。
///
/// 三种结局:
///  - `.sidebar(dest)`:已知页面路由 → 跳侧边栏目的地
///  - `.chatPrompt(text)`:`/chat?prompt=…` → 预填输入框(用户确认后再发)
///  - `nil`:mac 无法执行 —— 渲染层据此**不画按钮**,杜绝静默死键
///    (实锤:medication_draft 的"去用药页记录"点了没反应,Rule#1 反模式)。
public enum DynamicCardRouteAction: Equatable {
    case sidebar(SidebarDestination)
    case chatPrompt(String)
}

public enum DynamicCardRouting {
    /// 保守映射:只映射语义确定的 mobile 路由 → mac 侧边栏。未列出的返回 nil。
    static let pathDestinations: [(prefix: String, destination: SidebarDestination)] = [
        ("/medications", .prescriptions),
        ("/agenda", .agenda),
        ("/my-progress", .review),
        ("/timeline", .timeline),
        ("/goals", .goals),
        ("/workouts", .workouts),
        ("/workout-detail", .workouts),
        ("/indicator-history", .data),
        ("/record", .record),
    ]

    public static func resolve(route: String) -> DynamicCardRouteAction? {
        let trimmed = route.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.hasPrefix("/"),
              !trimmed.hasPrefix("//"),
              trimmed.rangeOfCharacter(from: .controlCharacters) == nil,
              let components = URLComponents(string: "reva://local\(trimmed)") else {
            return nil
        }
        let path = components.path
        if path.contains("/chat") {
            let prompt = components.queryItems?
                .first(where: { $0.name == "prompt" })?
                .value?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return prompt.isEmpty ? nil : .chatPrompt(prompt)
        }
        // expo-router 分组段(如 /(tabs)/agenda)剥掉括号段再比对
        let normalized = "/" + path.split(separator: "/")
            .filter { !($0.hasPrefix("(") && $0.hasSuffix(")")) }
            .joined(separator: "/")
        for (prefix, destination) in pathDestinations where normalized.hasPrefix(prefix) {
            return .sidebar(destination)
        }
        return nil
    }

    /// 渲染层守卫:mac 画不画这个 route.open 按钮。
    public static func isActionable(route: String) -> Bool {
        resolve(route: route) != nil
    }
}
