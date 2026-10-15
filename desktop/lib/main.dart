// LocalChat desktop app. Starts the Python backend (backend.dart), shows the
// chat UI, and stops the backend when the window closes or the app quits.

import 'dart:async';
import 'dart:io';
import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'backend.dart';
import 'state.dart';
import 'ui/chat.dart';
import 'ui/sidebar.dart';
import 'ui/theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const LocalChatApp());
}

class LocalChatApp extends StatefulWidget {
  const LocalChatApp({super.key});

  @override
  State<LocalChatApp> createState() => _LocalChatAppState();
}

class _LocalChatAppState extends State<LocalChatApp> {
  Backend? _backend;
  AppState? _state;
  Object? _startError;
  late final AppLifecycleListener _lifecycle;

  @override
  void initState() {
    super.initState();
    // Closing the window (or Cmd+Q / Alt+F4) asks here first: stop the backend,
    // then let the app exit.
    _lifecycle = AppLifecycleListener(onExitRequested: () async {
      await _backend?.stop();
      return AppExitResponse.exit;
    });
    _start();
  }

  Future<void> _start() async {
    setState(() => _startError = null);
    try {
      final backend = await Backend.start();
      final state = AppState(Api(backend.url));
      _backend = backend;
      setState(() => _state = state);
      await state.init();
    } catch (e) {
      setState(() => _startError = e);
    }
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    _state?.dispose();
    unawaited(_backend?.stop());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'LocalChat',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: Scaffold(
        body: _startError != null
            ? _StartError(error: _startError!, onRetry: _start)
            : _state == null
                ? const _Starting()
                : HomeScreen(state: _state!),
      ),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.state});

  final AppState state;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _collapsed = false;

  @override
  Widget build(BuildContext context) {
    return CallbackShortcuts(
      bindings: {
        // Cmd+N / Ctrl+N: new chat
        SingleActivator(LogicalKeyboardKey.keyN, meta: Platform.isMacOS, control: !Platform.isMacOS): () {
          if (!widget.state.isStreaming) widget.state.newConversation();
        },
      },
      child: ListenableBuilder(
        listenable: widget.state,
        builder: (context, _) {
          if (!widget.state.ready) return const _Starting();
          return Row(
            children: [
              if (!_collapsed) Sidebar(state: widget.state, onCollapse: () => setState(() => _collapsed = true)),
              Expanded(
                child: ChatPane(
                  state: widget.state,
                  sidebarCollapsed: _collapsed,
                  onExpandSidebar: () => setState(() => _collapsed = false),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Starting extends StatelessWidget {
  const _Starting();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Image.asset('assets/logo-nobodywho.png', height: 28),
        const SizedBox(height: 24),
        const Row(mainAxisSize: MainAxisSize.min, children: [
          PulseDot(),
          SizedBox(width: 4),
          PulseDot(delay: Duration(milliseconds: 160)),
          SizedBox(width: 4),
          PulseDot(delay: Duration(milliseconds: 320)),
        ]),
        const SizedBox(height: 12),
        const Text('Starting LocalChat…', style: TextStyle(color: C.muted, fontSize: 13)),
      ]),
    );
  }
}

class _StartError extends StatelessWidget {
  const _StartError({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Image.asset('assets/logo-nobodywho.png', height: 28),
          const SizedBox(height: 24),
          const Text('LocalChat could not start', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          SelectableText('$error',
              textAlign: TextAlign.center, style: const TextStyle(color: C.muted, fontSize: 13, height: 1.5)),
          const SizedBox(height: 20),
          OutlinedButton(onPressed: onRetry, child: const Text('Try again')),
        ]),
      ),
    );
  }
}
