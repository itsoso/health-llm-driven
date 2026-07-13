import AppKit
@testable import HealthAgentMac
import XCTest

@MainActor
final class CommandReturnTextViewPasteTests: XCTestCase {
    func testReadsScreenshotPngDataFromPasteboard() throws {
        let pasteboard = NSPasteboard(name: NSPasteboard.Name("CommandReturnTextViewPasteTests-\(UUID().uuidString)"))
        pasteboard.clearContents()
        let png = try makePNG()
        pasteboard.setData(png, forType: .png)

        let image = CommandReturnTextView.image(from: pasteboard)

        XCTAssertNotNil(image)
    }

    func testTreatsRawPngPasteboardAsPasteable() throws {
        let pasteboard = NSPasteboard(name: NSPasteboard.Name("CommandReturnTextViewPasteTests-\(UUID().uuidString)"))
        pasteboard.clearContents()
        let png = try makePNG()
        pasteboard.setData(png, forType: .png)

        XCTAssertTrue(CommandReturnTextView.canPasteAttachment(from: pasteboard))
    }

    private func makePNG() throws -> Data {
        let image = NSImage(size: NSSize(width: 8, height: 8))
        image.lockFocus()
        NSColor.systemGreen.setFill()
        NSRect(x: 0, y: 0, width: 8, height: 8).fill()
        image.unlockFocus()

        let tiff = try XCTUnwrap(image.tiffRepresentation)
        let bitmap = try XCTUnwrap(NSBitmapImageRep(data: tiff))
        return try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
    }
}
