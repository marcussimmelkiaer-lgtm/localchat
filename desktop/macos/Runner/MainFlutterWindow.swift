import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let windowFrame = self.frame
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)
    self.title = "LocalChat"
    self.minSize = NSSize(width: 720, height: 520)
    // Open large: most of the screen's visible area (minus menu bar and Dock).
    if let visible = NSScreen.main?.visibleFrame {
      self.setFrame(visible.insetBy(dx: visible.width * 0.05, dy: visible.height * 0.05), display: true)
    }

    RegisterGeneratedPlugins(registry: flutterViewController)

    super.awakeFromNib()
  }
}
