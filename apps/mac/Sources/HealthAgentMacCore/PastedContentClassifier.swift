import Foundation

/// ⌘V 粘贴内容分类(纯函数,单测覆盖;AppKit 的 paste 覆写只做剪贴板读取)。
///
/// 真实剪贴板形态(修 #142 首版"有文本就放弃图"的判定盲区):
///  - 截屏 (⌘⇧⌃4):纯位图,无文本 → 附位图
///  - 浏览器"拷贝图像"(医院报告页等):位图 + 图片 URL 文本 → 附位图(URL 是伴生文本,不是用户要粘的字)
///  - Finder ⌘C 图片/PDF 文件:file-url (+ 文件名文本) → 附原文件(保留原格式,不强转 PNG)
///  - 富文本选区(网页/文档划选):散文文本 + 可能的位图 flavor → 照旧粘文本
///
/// 保守方向:宁可把"散文+图"判成文本(用户可改用截屏),绝不把用户要粘的散文吞成图。
public enum PastedContentDecision: Equatable {
    case attachFiles([URL])
    case attachBitmap
    case pasteText
}

public enum PastedContentClassifier {
    /// 与 FileIntakeService 同源的可附件扩展名 —— 附件通路支持什么,粘贴就支持什么。
    public static let attachableExtensions: Set<String> = ["pdf", "jpg", "jpeg", "png", "heic", "webp"]

    public static func decide(
        pastedString: String?,
        hasBitmapImage: Bool,
        fileURLs: [URL]
    ) -> PastedContentDecision {
        let attachable = fileURLs.filter {
            attachableExtensions.contains($0.pathExtension.lowercased())
        }
        if !attachable.isEmpty {
            return .attachFiles(attachable)
        }
        guard hasBitmapImage else { return .pasteText }
        let trimmed = (pastedString ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty || isLikelyImageCompanionURL(trimmed) {
            return .attachBitmap
        }
        return .pasteText
    }

    /// 浏览器"拷贝图像"会同时写入图片地址文本;单行 http(s)/file/data:image URL
    /// 视为位图的伴生文本(让位给图),多行或散文则是用户真要粘的内容。
    static func isLikelyImageCompanionURL(_ s: String) -> Bool {
        guard !s.contains("\n") else { return false }
        let lower = s.lowercased()
        return lower.hasPrefix("http://") || lower.hasPrefix("https://")
            || lower.hasPrefix("file://") || lower.hasPrefix("data:image/")
    }
}
