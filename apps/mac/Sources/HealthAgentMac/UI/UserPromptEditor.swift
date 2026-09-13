import SwiftUI

struct UserPromptEditor: View {
    @State var text: String
    let hasPendingAttachments: Bool
    let onCancel: () -> Void
    let onSend: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("编辑消息").font(.title2.bold())
            Text("修改后的文字将作为新消息发送，原消息和已有回答会保留。")
                .font(.callout).foregroundStyle(.secondary)
            TextEditor(text: $text)
                .font(.body)
                .padding(8)
                .frame(minHeight: 220, maxHeight: 440)
                .background(.background, in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(.secondary.opacity(0.3)))
                .accessibilityLabel("编辑消息内容")
            if hasPendingAttachments {
                Text("输入框中还有待发送的附件，请先发送或移除附件。")
                    .font(.callout).foregroundStyle(.secondary)
            }
            HStack {
                Spacer()
                Button("取消", action: onCancel).keyboardShortcut(.cancelAction)
                Button("重新发送") { onSend(text.trimmingCharacters(in: .whitespacesAndNewlines)) }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.return, modifiers: .command)
                    .disabled(hasPendingAttachments || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(24)
        .frame(minWidth: 460, idealWidth: 620, maxWidth: 760)
    }
}
