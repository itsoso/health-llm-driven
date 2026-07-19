import SwiftUI

@main
struct LocalDietBenchmarkHostApp: App {
    @State private var status = "Preparing synthetic benchmark…"

    var body: some Scene {
        WindowGroup {
            ScrollView {
                Text(status)
                    .font(.system(.body, design: .monospaced))
                    .padding()
            }
            .task {
                await runBenchmark()
            }
        }
    }

    @MainActor
    private func runBenchmark() async {
        do {
            let report = try await LocalDietLiveBenchmark.runIfExplicitlyEnabled(
                environment: [LocalDietLiveBenchmark.enableEnvironmentKey: "1"]
            )
            guard let report else {
                status = "Benchmark was not enabled."
                return
            }

            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            let data = try encoder.encode(report)
            let json = String(decoding: data, as: UTF8.self)
            print("LOCAL_DIET_INFERENCE_BENCHMARK=\(json)")
            status = json
        } catch {
            let errorType = String(reflecting: type(of: error))
            print("LOCAL_DIET_INFERENCE_BENCHMARK_ERROR=\(errorType)")
            status = "Benchmark failed: \(errorType)"
        }
    }
}
