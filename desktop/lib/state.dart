// App state: conversations + messages, the answer being streamed, backend
// health (model loading / download progress) and the model manager. One
// ChangeNotifier the widgets listen to; the Dart counterpart of the browser
// UI's hooks (frontend/src/hooks/).

import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';

import 'api.dart';
import 'models.dart';

/// A file picked in the composer, not yet sent.
class PickedFile {
  PickedFile({required this.name, required this.bytes}) : mime = mimeFor(name);

  final String name;
  final Uint8List bytes;
  final String mime;

  bool get isImage => mime.startsWith('image/');
}

const uploadExtensions = ['csv', 'pdf', 'xlsx', 'xls', 'docx', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'];

String mimeFor(String name) {
  final ext = name.contains('.') ? name.split('.').last.toLowerCase() : '';
  return const {
        'csv': 'text/csv',
        'pdf': 'application/pdf',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'xls': 'application/vnd.ms-excel',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'webp': 'image/webp',
        'gif': 'image/gif',
        'bmp': 'image/bmp',
      }[ext] ??
      '';
}

final _rand = Random.secure();

String newId() {
  String hex(int n) => List.generate(n, (_) => _rand.nextInt(16).toRadixString(16)).join();
  return '${hex(8)}-${hex(4)}-4${hex(3)}-${(8 + _rand.nextInt(4)).toRadixString(16)}${hex(3)}-${hex(12)}';
}

String _deriveTitle(String content) {
  final first = content.trim().split('\n').first.replaceAll(RegExp(r'\s+'), ' ');
  if (first.isEmpty) return 'New chat';
  return first.length > 42 ? '${first.substring(0, 41)}…' : first;
}

/// Fast tools (e.g. the clock) finish in milliseconds; keep "Using tool" on
/// screen at least this long so people can see it happen.
const _minToolRunning = Duration(milliseconds: 1200);

class AppState extends ChangeNotifier {
  AppState(this.api);

  final Api api;

  // ---- conversations ----
  List<Conversation> conversations = [];
  String? activeId;
  final Map<String, List<Message>> _messages = {};
  bool ready = false;
  String? loadError;

  List<Message> get activeMessages => activeId == null ? const [] : (_messages[activeId] ?? const []);

  // ---- health ----
  Health health = const Health(available: true);
  Timer? _healthTimer;

  bool get modelReady => health.available && health.modelLoaded;

  /// "Downloading model… 42%" while the first-run model download runs.
  int? get downloadPct => !modelReady && health.taskStatus == 'downloading'
      ? (health.taskFraction * 100).round()
      : null;

  // ---- streaming ----
  StreamSubscription<ChatEvent>? _stream;
  String? _streamConv;
  String? _streamMsg;
  final StringBuffer _pending = StringBuffer();
  Timer? _flushTimer;
  final Map<int, DateTime> _toolStarted = {};

  bool get isStreaming => _stream != null;

  // ---- models ----
  ModelList? models;
  ModelTask task = const ModelTask();
  String? modelActionError;
  Timer? _taskTimer;

  // =========================================================================

  Future<void> init() async {
    try {
      conversations = await api.listConversations();
      _sortConversations();
      activeId = conversations.isEmpty ? null : conversations.first.id;
      if (activeId != null) await _hydrate(activeId!);
    } catch (e) {
      loadError = '$e';
    }
    ready = true;
    notifyListeners();
    // Load the model in the background now the UI is up; poll until ready.
    // The model list is fetched once the model has loaded (see _pollHealth).
    _lastWarmup = DateTime.now();
    unawaited(api.warmup());
    _pollHealth();
  }

  DateTime _lastWarmup = DateTime.fromMillisecondsSinceEpoch(0);
  int _healthFailures = 0;

  @override
  void dispose() {
    _healthTimer?.cancel();
    _taskTimer?.cancel();
    _flushTimer?.cancel();
    _stream?.cancel();
    super.dispose();
  }

  void _pollHealth() {
    _healthTimer?.cancel();
    Future<void> tick() async {
      var h = await api.health();
      // One failed check is not "server down" (a connection hiccup); only
      // report it after 3 in a row, ~2 s. Meanwhile keep the last known state.
      if (!h.available) {
        _healthFailures++;
        if (_healthFailures < 3) {
          _healthTimer = Timer(const Duration(milliseconds: 700), tick);
          return;
        }
      } else {
        _healthFailures = 0;
      }
      final justLoaded = h.modelLoaded && !health.modelLoaded;
      health = h;
      notifyListeners();
      // Fetch the model list only once the model is loaded: listing the model
      // cache while a model loads can stall the backend.
      if (h.modelLoaded && (justLoaded || models == null)) unawaited(refreshModels());
      // Not loaded, not loading anything we know of, no error: ask again (the
      // backend ignores this while a load is already running). Covers a lost
      // first request, so the app never sits on "Preparing model…".
      final idle = h.taskStatus != 'downloading' && h.taskStatus != 'loading' && !task.busy;
      if (h.available && !h.modelLoaded && h.modelError == null && idle &&
          DateTime.now().difference(_lastWarmup) > const Duration(seconds: 5)) {
        _lastWarmup = DateTime.now();
        unawaited(api.warmup());
      }
      final settled = h.available && (h.modelLoaded || h.modelError != null) && !task.busy;
      _healthTimer = Timer(Duration(milliseconds: settled ? 5000 : 600), tick);
    }

    tick();
  }

  void _sortConversations() => conversations.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));

  Future<void> _hydrate(String id) async {
    if (_messages.containsKey(id)) return;
    try {
      _messages[id] = await api.messages(id);
    } catch (_) {
      _messages[id] = [];
    }
  }

  Future<void> select(String id) async {
    activeId = id;
    notifyListeners();
    await _hydrate(id);
    notifyListeners();
  }

  Future<Conversation> newConversation() async {
    final conv = await api.createConversation();
    conversations.insert(0, conv);
    _messages[conv.id] = [];
    activeId = conv.id;
    notifyListeners();
    return conv;
  }

  Future<void> rename(String id, String title) async {
    final conv = conversations.firstWhere((c) => c.id == id);
    conv.title = title;
    notifyListeners();
    try {
      await api.renameConversation(id, title);
    } catch (_) {}
  }

  Future<void> delete(String id) async {
    conversations.removeWhere((c) => c.id == id);
    _messages.remove(id);
    if (activeId == id) {
      activeId = conversations.isEmpty ? null : conversations.first.id;
      if (activeId != null) await _hydrate(activeId!);
    }
    notifyListeners();
    try {
      await api.deleteConversation(id);
    } catch (_) {}
  }

  void _touch(String id) {
    for (final c in conversations) {
      if (c.id == id) c.updatedAt = DateTime.now();
    }
    _sortConversations();
  }

  Message? _find(String convId, String msgId) {
    for (final m in _messages[convId] ?? const <Message>[]) {
      if (m.id == msgId) return m;
    }
    return null;
  }

  // ---- sending -------------------------------------------------------------

  Future<void> send(String text, List<PickedFile> files) async {
    final content = text.trim();
    if ((content.isEmpty && files.isEmpty) || isStreaming) return;
    final convId = activeId ?? (await newConversation()).id;

    final conv = conversations.firstWhere((c) => c.id == convId);
    if (conv.title.isEmpty) {
      unawaited(rename(convId, _deriveTitle(content.isNotEmpty ? content : files.first.name)));
    }

    final user = Message(
      id: newId(),
      role: 'user',
      content: content,
      attachments: [
        for (final f in files)
          Attachment(
            name: f.name,
            mime: f.mime,
            size: f.bytes.length,
            isImage: f.isImage,
            previewBytes: f.isImage ? f.bytes : null,
          ),
      ],
    );
    final assistant = Message(id: newId(), role: 'assistant', status: 'streaming');
    (_messages[convId] ??= []).addAll([user, assistant]);
    _touch(convId);
    notifyListeners();

    _run(
      convId,
      assistant.id,
      api.streamChat(
        conversationId: convId,
        content: content,
        userMessageId: user.id,
        assistantMessageId: assistant.id,
        attachments: [
          for (final f in files) {'name': f.name, 'mime': f.mime, 'data_b64': base64Encode(f.bytes)},
        ],
      ),
    );
  }

  void regenerate() {
    final convId = activeId;
    if (convId == null || isStreaming) return;
    final msgs = _messages[convId] ?? const <Message>[];
    final last = msgs.lastWhere((m) => m.role == 'assistant', orElse: () => Message(id: '', role: ''));
    if (last.id.isEmpty) return;
    last
      ..content = ''
      ..status = 'streaming'
      ..stats = null
      ..error = null
      ..toolCalls = [];
    notifyListeners();
    _run(convId, last.id,
        api.streamChat(conversationId: convId, assistantMessageId: last.id, regenerate: true));
  }

  void stop() {
    final convId = _streamConv;
    if (convId == null) return;
    unawaited(api.stop(convId).catchError((_) {}));
  }

  void _run(String convId, String msgId, Stream<ChatEvent> events) {
    _streamConv = convId;
    _streamMsg = msgId;
    _pending.clear();
    _toolStarted.clear();
    _stream = events.listen(
      (e) => _onEvent(convId, msgId, e),
      onDone: () => _finish(convId, msgId, null),
      onError: (Object e) => _finish(convId, msgId, ErrorEvent('$e')),
    );
  }

  void _onEvent(String convId, String msgId, ChatEvent e) {
    final m = _find(convId, msgId);
    if (m == null) return;
    switch (e) {
      case TokenEvent(:final text):
        _pending.write(text);
        // Batch tokens: one rebuild per ~frame, not per token.
        _flushTimer ??= Timer(const Duration(milliseconds: 40), _flush);
      case ToolEvent(:final call):
        void upsert() {
          final mm = _find(convId, msgId);
          if (mm == null) return;
          mm.toolCalls = [...mm.toolCalls.where((c) => c.id != call.id), call]
            ..sort((a, b) => a.id.compareTo(b.id));
          notifyListeners();
        }
        if (call.status == 'running') {
          _toolStarted[call.id] = DateTime.now();
          upsert();
        } else {
          final started = _toolStarted[call.id];
          final wait = started == null ? Duration.zero : _minToolRunning - DateTime.now().difference(started);
          wait > Duration.zero ? Timer(wait, upsert) : upsert();
        }
      case StatsEvent(:final stats):
        m.stats = stats;
      case DoneEvent(:final status):
        _flush();
        m.status = status == 'stopped' ? 'stopped' : 'done';
        _finish(convId, msgId, null);
      case ErrorEvent():
        _finish(convId, msgId, e);
    }
  }

  void _flush() {
    _flushTimer?.cancel();
    _flushTimer = null;
    if (_pending.isEmpty || _streamConv == null || _streamMsg == null) return;
    final m = _find(_streamConv!, _streamMsg!);
    m?.content += _pending.toString();
    _pending.clear();
    notifyListeners();
  }

  void _finish(String convId, String msgId, ErrorEvent? error) {
    if (_streamMsg != msgId) return;
    _flush();
    final m = _find(convId, msgId);
    if (m != null) {
      if (error != null) {
        m.status = 'error';
        m.error = error.message;
      } else if (m.status == 'streaming') {
        m.status = 'done';
      }
    }
    _stream?.cancel();
    _stream = null;
    _streamConv = null;
    _streamMsg = null;
    _touch(convId);
    notifyListeners();
  }

  // ---- models ----------------------------------------------------------------

  Future<void> refreshModels() async {
    try {
      models = await api.listModels();
      notifyListeners();
    } catch (_) {}
  }

  Future<void> _action(Future<void> Function() call, ModelTask optimistic) async {
    modelActionError = null;
    try {
      await call();
    } on ApiError catch (e) {
      modelActionError = e.message;
      notifyListeners();
      return;
    } catch (_) {
      modelActionError = 'Could not reach the local server.';
      notifyListeners();
      return;
    }
    task = optimistic;
    notifyListeners();
    _pollTask();
    _pollHealth(); // the composer re-enables when the new model is loaded
  }

  Future<void> downloadModel(String spec, {bool thenSwitch = true, List<String> extra = const []}) =>
      _action(() => api.downloadModel(spec, thenSwitch: thenSwitch, extraSpecs: extra),
          ModelTask(status: 'downloading', target: spec));

  Future<void> switchModel(String path) =>
      _action(() => api.switchModel(path), ModelTask(status: 'loading', target: path));

  Future<void> deleteModel(String path) async {
    modelActionError = null;
    try {
      models = await api.deleteModel(path);
    } on ApiError catch (e) {
      modelActionError = e.message;
    } catch (_) {
      modelActionError = 'Could not reach the local server.';
    }
    notifyListeners();
  }

  void clearModelError() {
    modelActionError = null;
    notifyListeners();
  }

  void _pollTask() {
    _taskTimer?.cancel();
    Future<void> tick() async {
      try {
        task = await api.modelStatus();
        notifyListeners();
      } catch (_) {}
      if (task.busy) {
        _taskTimer = Timer(const Duration(milliseconds: 600), tick);
      } else {
        await refreshModels();
      }
    }

    _taskTimer = Timer(Duration.zero, tick);
  }
}
