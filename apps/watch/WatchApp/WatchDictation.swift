import Foundation
#if canImport(WatchKit)
import WatchKit
#endif

/// 腕上语音听写(记一餐用)。封装 WKExtension 的 presentTextInputController 语音转写。
enum WatchDictation {
    static func present() async -> String? {
        #if canImport(WatchKit)
        await withCheckedContinuation { cont in
            guard let controller = WKExtension.shared().visibleInterfaceController
                ?? WKExtension.shared().rootInterfaceController else {
                cont.resume(returning: nil); return
            }
            controller.presentTextInputController(
                withSuggestions: nil, allowedInputMode: .plain
            ) { results in
                let text = (results?.first as? String)?
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                cont.resume(returning: (text?.isEmpty == false) ? text : nil)
            }
        }
        #else
        return nil
        #endif
    }
}
