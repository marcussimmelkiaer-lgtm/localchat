import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let windowFrame = self.frame
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)
    self.title = "LocalChat"
    // Taller, app-coloured title bar: the Flutter content runs underneath a
    // transparent title bar, and an empty unified toolbar makes it 52 pt tall
    // with the traffic lights centred (the app draws the bar: ui/title_bar.dart).
    self.titleVisibility = .hidden
    self.titlebarAppearsTransparent = true
    self.styleMask.insert(.fullSizeContentView)
    let toolbar = NSToolbar(identifier: "LocalChatToolbar")
    toolbar.showsBaselineSeparator = false
    self.toolbar = toolbar
    self.toolbarStyle = .unified
    self.minSize = NSSize(width: 720, height: 520)
    // Open large: most of the screen's visible area (minus menu bar and Dock).
    if let visible = NSScreen.main?.visibleFrame {
      self.setFrame(visible.insetBy(dx: visible.width * 0.05, dy: visible.height * 0.05), display: true)
    }

    RegisterGeneratedPlugins(registry: flutterViewController)

    super.awakeFromNib()
  }
}
