import SwiftUI
import HealthAgentMacCore

struct WearablePanelView: View {
    let metrics: [DesktopDashboardMetric]
    let appLanguageRaw: String
    let localizedTitle: (String) -> String
    let localizedDetail: (String) -> String
    var onTap: ((DesktopDashboardMetric) -> Void)? = nil

    var body: some View {
        card {
            sectionHeader(title: appText("Wearable Today", appLanguageRaw), systemImage: "sensor.tag.radiowaves.forward.fill")
            VStack(spacing: 8) {
                ForEach(metrics) { metric in
                    Button {
                        onTap?(metric)
                    } label: {
                        VitalRow(
                            metric: metric,
                            title: localizedTitle(metric.titleKey),
                            detail: localizedDetail(metric.detail),
                            showsDisclosure: true
                        )
                    }
                    .buttonStyle(.plain)
                    .help(appText("Ask Agent with Context", appLanguageRaw))
                }
            }
        }
    }
}
