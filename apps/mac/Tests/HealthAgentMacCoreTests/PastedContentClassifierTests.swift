import XCTest
@testable import HealthAgentMacCore

final class PastedContentClassifierTests: XCTestCase {
    // MARK: 截屏(纯位图)

    func testScreenshotBitmapOnlyAttaches() {
        XCTAssertEqual(
            PastedContentClassifier.decide(pastedString: nil, hasBitmapImage: true, fileURLs: []),
            .attachBitmap
        )
    }

    func testBitmapWithWhitespaceOnlyTextAttaches() {
        XCTAssertEqual(
            PastedContentClassifier.decide(pastedString: "  \n ", hasBitmapImage: true, fileURLs: []),
            .attachBitmap
        )
    }

    // MARK: 浏览器"拷贝图像"(位图 + URL 伴生文本)—— #142 首版的判定盲区

    func testBrowserCopyImageWithHTTPSCompanionURLAttaches() {
        XCTAssertEqual(
            PastedContentClassifier.decide(
                pastedString: "https://hospital.example.com/report/mri-knee.png",
                hasBitmapImage: true,
                fileURLs: []
            ),
            .attachBitmap
        )
    }

    func testBrowserCopyImageWithDataURLAttaches() {
        XCTAssertEqual(
            PastedContentClassifier.decide(
                pastedString: "data:image/png;base64,iVBORw0KGgo=",
                hasBitmapImage: true,
                fileURLs: []
            ),
            .attachBitmap
        )
    }

    // MARK: 富文本选区(散文 + 位图 flavor)→ 保守让位给文本

    func testProseWithBitmapFlavorPastesText() {
        XCTAssertEqual(
            PastedContentClassifier.decide(
                pastedString: "左膝关节内外侧盘状半月板考虑,请结合临床。",
                hasBitmapImage: true,
                fileURLs: []
            ),
            .pasteText
        )
    }

    func testMultilineURLishTextPastesText() {
        // 多行内容即使首行像 URL 也按用户文本处理
        XCTAssertEqual(
            PastedContentClassifier.decide(
                pastedString: "https://a.example\n第二行说明",
                hasBitmapImage: true,
                fileURLs: []
            ),
            .pasteText
        )
    }

    // MARK: Finder ⌘C 文件(file-url + 文件名伴生文本)

    func testFinderCopiedImageFileAttachesOriginalFile() {
        let url = URL(fileURLWithPath: "/tmp/mri-report.jpg")
        XCTAssertEqual(
            PastedContentClassifier.decide(pastedString: "mri-report.jpg", hasBitmapImage: false, fileURLs: [url]),
            .attachFiles([url])
        )
    }

    func testFinderCopiedPDFAttaches() {
        let url = URL(fileURLWithPath: "/tmp/诊断报告.PDF")
        XCTAssertEqual(
            PastedContentClassifier.decide(pastedString: nil, hasBitmapImage: false, fileURLs: [url]),
            .attachFiles([url])
        )
    }

    func testFileURLsWinOverBitmap() {
        // 同时有 file-url 和位图(Finder 拷图常见)→ 附原文件保原格式
        let url = URL(fileURLWithPath: "/tmp/photo.heic")
        XCTAssertEqual(
            PastedContentClassifier.decide(pastedString: "photo.heic", hasBitmapImage: true, fileURLs: [url]),
            .attachFiles([url])
        )
    }

    func testMixedFileURLsKeepOnlyAttachable() {
        let png = URL(fileURLWithPath: "/tmp/a.png")
        let docx = URL(fileURLWithPath: "/tmp/b.docx")
        XCTAssertEqual(
            PastedContentClassifier.decide(pastedString: nil, hasBitmapImage: false, fileURLs: [docx, png]),
            .attachFiles([png])
        )
    }

    func testUnattachableFileWithoutBitmapPastesText() {
        let docx = URL(fileURLWithPath: "/tmp/b.docx")
        XCTAssertEqual(
            PastedContentClassifier.decide(pastedString: "b.docx", hasBitmapImage: false, fileURLs: [docx]),
            .pasteText
        )
    }

    // MARK: 纯文本

    func testPlainTextPastesText() {
        XCTAssertEqual(
            PastedContentClassifier.decide(pastedString: "血压 128/82", hasBitmapImage: false, fileURLs: []),
            .pasteText
        )
    }

    func testEmptyPasteboardPastesText() {
        XCTAssertEqual(
            PastedContentClassifier.decide(pastedString: nil, hasBitmapImage: false, fileURLs: []),
            .pasteText
        )
    }
}
