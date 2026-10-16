import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  private var fullScreenObservers: [NSObjectProtocol] = []

  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let windowFrame = self.frame
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)
    self.title = "LocalChat"
    // Same white as the app wherever the system draws window background.
    self.backgroundColor = .white
    // Taller, app-coloured title bar: the Flutter content runs underneath a
    // transparent title bar, and an empty unified toolbar makes it 52 pt tall
    // with the traffic lights centred (the app draws the bar: ui/title_bar.dart).
    self.titleVisibility = .hidden
    self.titlebarAppearsTransparent = true
    self.styleMask.insert(.fullSizeContentView)
    self.toolbar = Self.makeToolbar()
    self.toolbarStyle = .unified
    self.minSize = NSSize(width: 720, height: 520)
    // Open large: most of the screen's visible area (minus menu bar and Dock).
    if let visible = NSScreen.main?.visibleFrame {
      self.setFrame(visible.insetBy(dx: visible.width * 0.05, dy: visible.height * 0.05), display: true)
    }

    // In full screen macOS keeps a toolbar visible as a grey strip above the
    // content. Remove it there (the app hides its own bar too) and put it back
    // when leaving full screen. Notifications, not the window delegate: a plugin
    // (window_manager) owns the delegate.
    let center = NotificationCenter.default
    fullScreenObservers = [
      center.addObserver(forName: NSWindow.willEnterFullScreenNotification, object: self, queue: .main) {
        [weak self] _ in self?.toolbar = nil
      },
      center.addObserver(forName: NSWindow.willExitFullScreenNotification, object: self, queue: .main) {
        [weak self] _ in self?.toolbar = Self.makeToolbar()
      },
    ]

    RegisterGeneratedPlugins(registry: flutterViewController)

    super.awakeFromNib()
  }

  private static func makeToolbar() -> NSToolbar {
    let toolbar = NSToolbar(identifier: "LocalChatToolbar")
    toolbar.showsBaselineSeparator = false
    return toolbar
  }
}
