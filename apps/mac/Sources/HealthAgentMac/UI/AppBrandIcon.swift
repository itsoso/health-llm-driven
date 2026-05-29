import AppKit

enum AppBrandIcon {
    static var statusBarImage: NSImage {
        let image: NSImage
        if let bundledImage = NSImage(named: "StatusBarIconTemplate") {
            image = bundledImage
        } else if let resourceURL = Bundle.module.url(forResource: "StatusBarIconTemplate", withExtension: "png"),
                  let moduleImage = NSImage(contentsOf: resourceURL) {
            image = moduleImage
        } else {
            image = NSImage(systemSymbolName: "heart.text.square", accessibilityDescription: "Health Agent") ?? NSImage()
        }
        image.isTemplate = true
        return image
    }
}
