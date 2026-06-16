import SwiftUI

/// 打点屏:腕上一键记录(喝水/运动/语音记餐)。校验走 WatchCompanionCore.QuickRecord。
struct QuickRecordView: View {
    @ObservedObject var store: WatchStore

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                Text("打点").font(.headline)

                // 喝水:常用量一键
                HStack {
                    waterButton(250)
                    waterButton(500)
                }

                // 运动:俯卧撑 / 跑步(示例量;真机可加 Digital Crown 调量)
                Button("俯卧撑 +20") {
                    Task { await store.submit { try QuickRecord.exercise(type: "俯卧撑", reps: 20) } }
                }
                Button("跑步 30 分钟") {
                    Task { await store.submit { try QuickRecord.exercise(type: "跑步", durationMin: 30) } }
                }

                // 语音记餐:走解析草稿(确认在 iPhone)
                Button("语音记一餐") {
                    Task {
                        let text = await dictate()
                        guard let text, !text.isEmpty else { return }
                        await store.submit { try QuickRecord.dietVoice(rawText: text) }
                    }
                }

                if store.lastRecordOK == true {
                    Text("✓ 已记录").font(.caption).foregroundStyle(.green)
                } else if store.lastRecordOK == false, let e = store.lastError {
                    Text(e).font(.caption2).foregroundStyle(.red)
                }
            }
            .padding(.horizontal, 4)
        }
        .navigationTitle("打点")
    }

    private func waterButton(_ ml: Int) -> some View {
        Button("\(ml)ml") {
            Task { await store.submit { try QuickRecord.water(amountML: ml) } }
        }
    }

    /// 腕上听写(WKExtension/Dictation)。占位:真机用 presentTextInputController 取语音转写。
    private func dictate() async -> String? {
        await WatchDictation.present()
    }
}
