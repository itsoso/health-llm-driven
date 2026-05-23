import HealthAgentMacCore
import SwiftUI

@main
struct HealthAgentMacApp: App {
    var body: some Scene {
        WindowGroup {
            AppRootView()
        }
        MenuBarExtra("Health Agent", systemImage: "heart.text.square") {
            MenuBarRootView()
        }
    }
}

struct AppRootView: View {
    @State private var selection: SidebarDestination? = .today

    var body: some View {
        NavigationSplitView {
            List(SidebarDestination.allCases, selection: $selection) { destination in
                Label(destination.title, systemImage: destination.systemImage)
                    .tag(destination)
            }
            .navigationTitle("Health Agent")
        } detail: {
            ContentPlaceholder(destination: selection ?? .today)
        }
        .frame(minWidth: 980, minHeight: 680)
    }
}

struct ContentPlaceholder: View {
    let destination: SidebarDestination

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(destination.title, systemImage: destination.systemImage)
                .font(.title.bold())
            Text("Native macOS client surface backed by \(APIEndpoint.defaultBaseURL.absoluteString)")
                .foregroundStyle(.secondary)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

struct MenuBarRootView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Health Agent", systemImage: "heart.text.square")
                .font(.headline)
            Divider()
            Button("Open Today") {}
            Button("Ask Agent") {}
            Button("Import File") {}
        }
        .padding(8)
        .frame(width: 220)
    }
}
