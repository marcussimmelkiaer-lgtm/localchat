// The window's top bar (the one you drag the window by), drawn by the app in
// the app's white and taller than the system one.
//
// Windows: the native title bar is hidden (window_manager, see main.dart) and
// this bar provides dragging (double-click maximizes) and minimize / maximize /
// close buttons. Close goes through WM_CLOSE like the system button, so the app
// still stops the backend on the way out.
// macOS: the native title bar is transparent and made taller with a unified
// toolbar (macos/Runner/MainFlutterWindow.swift), so the real traffic lights sit
// centred on this bar and the system handles dragging. Hidden in full screen.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

import 'theme.dart';

const double windowsBarHeight = 44;
const double macBarHeight = 52; // height of a unified toolbar title bar

class TitleBar extends StatefulWidget {
  const TitleBar({super.key});

  @override
  State<TitleBar> createState() => _TitleBarState();
}

class _TitleBarState extends State<TitleBar> with WindowListener {
  bool _maximized = false;
  bool _fullScreen = false;

  @override
  void initState() {
    super.initState();
    windowManager.addListener(this);
    windowManager.isMaximized().then((m) => mounted ? setState(() => _maximized = m) : null);
  }

  @override
  void dispose() {
    windowManager.removeListener(this);
    super.dispose();
  }

  @override
  void onWindowMaximize() => setState(() => _maximized = true);
  @override
  void onWindowUnmaximize() => setState(() => _maximized = false);
  @override
  void onWindowEnterFullScreen() => setState(() => _fullScreen = true);
  @override
  void onWindowLeaveFullScreen() => setState(() => _fullScreen = false);

  @override
  Widget build(BuildContext context) {
    if (Platform.isMacOS) {
      if (_fullScreen) return const SizedBox.shrink();
      return const _Bar(height: macBarHeight, child: SizedBox.expand());
    }
    if (!Platform.isWindows) return const SizedBox.shrink();
    return _Bar(
      height: windowsBarHeight,
      child: Row(
        children: [
          Expanded(
            child: DragToMoveArea(
              child: Padding(
                padding: const EdgeInsets.only(left: 16),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text('LocalChat',
                      style: TextStyle(fontSize: 12, color: C.muted.withValues(alpha: 0.9))),
                ),
              ),
            ),
          ),
          _CaptionButton(
            icon: Icons.remove,
            tooltip: 'Minimize',
            onPressed: windowManager.minimize,
          ),
          _CaptionButton(
            icon: _maximized ? Icons.filter_none : Icons.crop_square,
            iconSize: _maximized ? 13 : 15,
            tooltip: _maximized ? 'Restore' : 'Maximize',
            onPressed: () => _maximized ? windowManager.unmaximize() : windowManager.maximize(),
          ),
          _CaptionButton(
            icon: Icons.close,
            tooltip: 'Close',
            onPressed: windowManager.close,
            danger: true,
          ),
        ],
      ),
    );
  }
}

class _Bar extends StatelessWidget {
  const _Bar({required this.height, required this.child});

  final double height;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      color: C.ground, // the same white as the chat area
      child: child,
    );
  }
}

/// A Windows-style caption button: full bar height, 46 px wide, grey hover
/// (red with a white icon for close).
class _CaptionButton extends StatefulWidget {
  const _CaptionButton({
    required this.icon,
    required this.tooltip,
    required this.onPressed,
    this.danger = false,
    this.iconSize = 16,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;
  final bool danger;
  final double iconSize;

  @override
  State<_CaptionButton> createState() => _CaptionButtonState();
}

class _CaptionButtonState extends State<_CaptionButton> {
  bool _hover = false;
  bool _down = false;

  @override
  Widget build(BuildContext context) {
    final bg = !_hover
        ? Colors.transparent
        : widget.danger
            ? (_down ? const Color(0xFFB0281A) : const Color(0xFFC42B1C))
            : (_down ? C.bubbleHover : C.hover);
    final fg = _hover && widget.danger ? Colors.white : C.ink;
    return Tooltip(
      message: widget.tooltip,
      waitDuration: const Duration(milliseconds: 800),
      child: MouseRegion(
        onEnter: (_) => setState(() => _hover = true),
        onExit: (_) => setState(() {
          _hover = false;
          _down = false;
        }),
        child: GestureDetector(
          onTapDown: (_) => setState(() => _down = true),
          onTapCancel: () => setState(() => _down = false),
          onTapUp: (_) => setState(() => _down = false),
          onTap: widget.onPressed,
          child: Container(
            width: 46,
            height: double.infinity,
            color: bg,
            child: Icon(widget.icon, size: widget.iconSize, color: fg),
          ),
        ),
      ),
    );
  }
}
