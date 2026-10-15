// Monochrome, white-dominant palette (same tokens as frontend/tailwind.config.js).

import 'dart:io';

import 'package:flutter/material.dart';

abstract final class C {
  static const ground = Color(0xFFFFFFFF); // chat surface
  static const ground2 = Color(0xFFFAFAFA); // app background, sidebar
  static const bubble = Color(0xFFF4F4F4); // user bubble, code blocks
  static const bubbleHover = Color(0xFFECECEC);
  static const hover = Color(0xFFF3F3F3);
  static const ink = Color(0xFF0A0A0A); // text
  static const muted = Color(0xFF6B7280); // secondary text
  static const line = Color(0xFFECECEC); // hairline borders
}

const contentMaxWidth = 720.0;

final String monoFont = Platform.isMacOS ? 'Menlo' : 'Consolas';

ThemeData buildTheme() {
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: C.ink,
      brightness: Brightness.light,
    ).copyWith(primary: C.ink, onPrimary: C.ground, surface: C.ground, onSurface: C.ink),
    scaffoldBackgroundColor: C.ground2,
    splashFactory: NoSplash.splashFactory,
    visualDensity: VisualDensity.standard,
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: C.ink, displayColor: C.ink),
    textSelectionTheme: const TextSelectionThemeData(
      cursorColor: C.ink,
      selectionColor: Color(0x220A0A0A),
    ),
    tooltipTheme: const TooltipThemeData(waitDuration: Duration(milliseconds: 500)),
    scrollbarTheme: ScrollbarThemeData(
      thickness: WidgetStateProperty.all(6),
      radius: const Radius.circular(8),
      thumbColor: WidgetStateProperty.all(const Color(0xFFD7D7D7)),
    ),
  );
}

/// A small icon button in the app's muted style.
class IconBtn extends StatelessWidget {
  const IconBtn({super.key, required this.icon, required this.tooltip, this.onPressed, this.size = 18});

  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;
  final double size;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      onPressed: onPressed,
      tooltip: tooltip,
      icon: Icon(icon, size: size),
      color: C.muted,
      hoverColor: C.hover,
      visualDensity: VisualDensity.compact,
      style: IconButton.styleFrom(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))),
    );
  }
}

/// Small pulsing dot used for "working…" states.
class PulseDot extends StatefulWidget {
  const PulseDot({super.key, this.delay = Duration.zero});

  final Duration delay;

  @override
  State<PulseDot> createState() => _PulseDotState();
}

class _PulseDotState extends State<PulseDot> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1200));

  @override
  void initState() {
    super.initState();
    Future.delayed(widget.delay, () {
      if (mounted) _c.repeat();
    });
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _c,
      builder: (_, _) {
        final t = _c.value;
        final o = t < 0.4 ? 0.25 + 0.75 * (t / 0.4) : (t < 0.8 ? 1 - 0.75 * ((t - 0.4) / 0.4) : 0.25);
        return Opacity(
          opacity: o,
          child: Container(
            width: 6,
            height: 6,
            decoration: const BoxDecoration(color: C.muted, shape: BoxShape.circle),
          ),
        );
      },
    );
  }
}
