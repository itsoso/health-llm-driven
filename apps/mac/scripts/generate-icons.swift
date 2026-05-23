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

    let background = NSBezierPath(roundedRect: rect, xRadius: size * 0.22, yRadius: size * 0.22)
    NSColor(calibratedRed: 0.02, green: 0.55, blue: 0.55, alpha: 1).setFill()
    background.fill()

    let glow = NSBezierPath(ovalIn: NSRect(x: size * 0.46, y: size * 0.47, width: size * 0.42, height: size * 0.42))
    NSColor(calibratedRed: 0.27, green: 1.0, blue: 0.86, alpha: 0.20).setFill()
    glow.fill()

    let cardRect = NSRect(x: size * 0.16, y: size * 0.18, width: size * 0.68, height: size * 0.64)
    let card = NSBezierPath(roundedRect: cardRect, xRadius: size * 0.12, yRadius: size * 0.12)
    NSColor.white.withAlphaComponent(0.16).setFill()
    card.fill()

    let pulse = NSBezierPath()
    pulse.lineCapStyle = .round
    pulse.lineJoinStyle = .round
    pulse.lineWidth = size * 0.055
    pulse.move(to: NSPoint(x: size * 0.24, y: size * 0.48))
    pulse.line(to: NSPoint(x: size * 0.36, y: size * 0.48))
    pulse.line(to: NSPoint(x: size * 0.43, y: size * 0.62))
    pulse.line(to: NSPoint(x: size * 0.50, y: size * 0.36))
    pulse.line(to: NSPoint(x: size * 0.58, y: size * 0.57))
    pulse.line(to: NSPoint(x: size * 0.66, y: size * 0.48))
    pulse.line(to: NSPoint(x: size * 0.76, y: size * 0.48))
    NSColor.white.setStroke()
    pulse.stroke()

    func sparkle(center: CGPoint, radius: CGFloat, alpha: CGFloat) {
        let path = NSBezierPath()
        path.move(to: NSPoint(x: center.x, y: center.y + radius))
        path.line(to: NSPoint(x: center.x + radius * 0.25, y: center.y + radius * 0.25))
        path.line(to: NSPoint(x: center.x + radius, y: center.y))
        path.line(to: NSPoint(x: center.x + radius * 0.25, y: center.y - radius * 0.25))
        path.line(to: NSPoint(x: center.x, y: center.y - radius))
        path.line(to: NSPoint(x: center.x - radius * 0.25, y: center.y - radius * 0.25))
        path.line(to: NSPoint(x: center.x - radius, y: center.y))
        path.line(to: NSPoint(x: center.x - radius * 0.25, y: center.y + radius * 0.25))
        path.close()
        NSColor(calibratedRed: 0.37, green: 1.0, blue: 0.88, alpha: alpha).setFill()
        path.fill()
    }

    sparkle(center: CGPoint(x: size * 0.67, y: size * 0.68), radius: size * 0.11, alpha: 1)
    sparkle(center: CGPoint(x: size * 0.38, y: size * 0.68), radius: size * 0.055, alpha: 0.72)
    sparkle(center: CGPoint(x: size * 0.78, y: size * 0.58), radius: size * 0.045, alpha: 0.48)

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
