import SwiftUI
import HealthAgentMacCore

struct RefreshPanelView: View {
    let isLoading: Bool
    let appLanguageRaw: String
    let onRefresh: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(appText("Health Agent", appLanguageRaw))
                    .font(.headline.weight(.semibold))
                if isLoading {
                    Text(appText("Loading desktop context...", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Text(appText("Ready", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            Button {
                onRefresh()
            } label: {
                Image(systemName: "arrow.clockwise")
                    .frame(width: 24, height: 24)
            }
            .buttonStyle(.borderedProminent)
            .help(appText("Refresh", appLanguageRaw))
        }
        .padding(14)
        .background(.background, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(panelStroke(radius: 16))
    }
}
