import Foundation
import Observation

@Observable
@MainActor
public final class AgentChatViewModel {
    public var isStreaming = false
    public var selectedModelID: String?

    public var isModelPickerEnabled: Bool {
        true
    }

    public init(selectedModelID: String? = nil) {
        self.selectedModelID = selectedModelID
    }

    public func selectModel(_ id: String?) {
        selectedModelID = id
    }
}
