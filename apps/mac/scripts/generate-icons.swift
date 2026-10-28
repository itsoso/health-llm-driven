#!/usr/bin/env swift

import AppKit
import Foundation

let scriptURL = URL(fileURLWithPath: #filePath)
let projectRoot = scriptURL
    .deletingLastPathComponent()
    .deletingLastPathComponent()
let resourcesURL = projectRoot
    .appendingPathComponent("Sources")
    .appendingPathComponent("HealthAgentMac")
    .appendingPathComponent("Resources")
let iconsetURL = resourcesURL.appendingPathComponent("HealthAgentIcon.iconset")

try FileManager.default.createDirectory(at: resourcesURL, withIntermediateDirectories: true)
try? FileManager.default.removeItem(at: iconsetURL)
try FileManager.default.createDirectory(at: iconsetURL, withIntermediateDirectories: true)

func drawAppIcon(size: CGFloat) -> NSImage {
    let image = NSImage(size: NSSize(width: size, height: size))
    image.lockFocus()

    let rect = NSRect(x: 0, y: 0, width: size, height: size)
    NSGraphicsContext.current?.imageInterpolation = .high

    let sourceURL = projectRoot
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("mobile/assets/images/icon.png")
    guard let artwork = NSImage(contentsOf: sourceURL) else {
        fatalError("Missing canonical app icon: \(sourceURL.path)")
    }
    let background = NSBezierPath(roundedRect: rect, xRadius: size * 0.22, yRadius: size * 0.22)
    background.addClip()
    artwork.draw(in: rect)

    image.unlockFocus()
    return image
}

func drawTemplateIcon(size: CGFloat) -> NSImage {
    let image = NSImage(size: NSSize(width: size, height: size))
    image.lockFocus()

    let stroke = NSColor.black
    stroke.setStroke()
    NSColor.black.setFill()

    let pulse = NSBezierPath()
    pulse.lineCapStyle = .round
    pulse.lineJoinStyle = .round
    pulse.lineWidth = max(1.8, size * 0.095)
    pulse.move(to: NSPoint(x: size * 0.14, y: size * 0.43))
    pulse.line(to: NSPoint(x: size * 0.30, y: size * 0.43))
    pulse.line(to: NSPoint(x: size * 0.40, y: size * 0.63))
    pulse.line(to: NSPoint(x: size * 0.50, y: size * 0.25))
    pulse.line(to: NSPoint(x: size * 0.61, y: size * 0.56))
    pulse.line(to: NSPoint(x: size * 0.72, y: size * 0.43))
    pulse.line(to: NSPoint(x: size * 0.88, y: size * 0.43))
    pulse.stroke()

    let sparkle = NSBezierPath()
    let center = CGPoint(x: size * 0.70, y: size * 0.73)
    let radius = size * 0.16
    sparkle.move(to: NSPoint(x: center.x, y: center.y + radius))
    sparkle.line(to: NSPoint(x: center.x + radius * 0.30, y: center.y + radius * 0.30))
    sparkle.line(to: NSPoint(x: center.x + radius, y: center.y))
    sparkle.line(to: NSPoint(x: center.x + radius * 0.30, y: center.y - radius * 0.30))
    sparkle.line(to: NSPoint(x: center.x, y: center.y - radius))
    sparkle.line(to: NSPoint(x: center.x - radius * 0.30, y: center.y - radius * 0.30))
    sparkle.line(to: NSPoint(x: center.x - radius, y: center.y))
    sparkle.line(to: NSPoint(x: center.x - radius * 0.30, y: center.y + radius * 0.30))
    sparkle.close()
    sparkle.fill()

    image.unlockFocus()
    image.isTemplate = true
    return image
}

func writePNG(_ image: NSImage, to url: URL, pixels: Int) throws {
    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: pixels,
        pixelsHigh: pixels,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    ) else {
        throw NSError(domain: "IconGenerator", code: 1)
    }

    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    image.draw(in: NSRect(x: 0, y: 0, width: pixels, height: pixels))
    NSGraphicsContext.restoreGraphicsState()

    guard let data = rep.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "IconGenerator", code: 2)
    }
    try data.write(to: url)
}

let appIconSizes: [(String, CGFloat, Int)] = [
    ("icon_16x16.png", 16, 16),
    ("icon_16x16@2x.png", 16, 32),
    ("icon_32x32.png", 32, 32),
    ("icon_32x32@2x.png", 32, 64),
    ("icon_128x128.png", 128, 128),
    ("icon_128x128@2x.png", 128, 256),
    ("icon_256x256.png", 256, 256),
    ("icon_256x256@2x.png", 256, 512),
    ("icon_512x512.png", 512, 512),
    ("icon_512x512@2x.png", 512, 1024),
]

for (name, points, pixels) in appIconSizes {
    try writePNG(drawAppIcon(size: points), to: iconsetURL.appendingPathComponent(name), pixels: pixels)
}

let process = Process()
process.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
process.arguments = [
    "-c", "icns",
    iconsetURL.path,
    "-o", resourcesURL.appendingPathComponent("HealthAgentIcon.icns").path,
]
try process.run()
process.waitUntilExit()
guard process.terminationStatus == 0 else {
    throw NSError(domain: "IconGenerator", code: Int(process.terminationStatus))
}

try writePNG(
    drawTemplateIcon(size: 18),
    to: resourcesURL.appendingPathComponent("StatusBarIconTemplate.png"),
    pixels: 36
)

try? FileManager.default.removeItem(at: iconsetURL)
print("Generated HealthAgentIcon.icns and StatusBarIconTemplate.png")
