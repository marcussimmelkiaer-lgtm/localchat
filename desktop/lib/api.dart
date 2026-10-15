// HTTP client for the local Python backend (backend/app.py + backend/routes/).
// Same endpoints the browser UI uses. Answers stream as server-sent events
// (SSE) over a POST, parsed by [Api.streamChat].

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

/// Thrown for a non-2xx response; [message] is the backend's `detail` text.
class ApiError implements Exception {
  ApiError(this.message);
  final String message;
  @override
  String toString() => message;
}

/// One event from a streaming answer.
sealed class ChatEvent {}

class TokenEvent extends ChatEvent {
  TokenEvent(this.text);
  final String text;
}

class ToolEvent extends ChatEvent {
  ToolEvent(this.call);
  final ToolCall call;
}

class StatsEvent extends ChatEvent {
  StatsEvent(this.stats);
  final Stats stats;
}

class DoneEvent extends ChatEvent {
  DoneEvent(this.status);
  final String status; // done | stopped
}

class ErrorEvent extends ChatEvent {
  ErrorEvent(this.message);
  final String message;
}

class Api {
  Api(this.base, {http.Client? client}) : _client = client ?? http.Client();

  final Uri base;
  final http.Client _client;

  Uri _u(String path) => base.resolve(path);

  Uri attachmentUrl(String messageId, int index) => _u('/api/attachments/$messageId/$index');

  Future<dynamic> _send(String method, String path, [Object? body, Duration? timeout]) async {
    final req = http.Request(method, _u(path));
    if (body != null) {
      req.headers['Content-Type'] = 'application/json';
      req.body = jsonEncode(body);
    }
    final res = await http.Response.fromStream(
      await _client.send(req).timeout(timeout ?? const Duration(seconds: 15)),
    );
    final text = utf8.decode(res.bodyBytes);
    final data = text.isEmpty ? null : jsonDecode(text);
    if (res.statusCode >= 400) throw ApiError(_detail(data, res.statusCode));
    return data;
  }

  // ---- health ----

  Future<Health> health() async {
    try {
      final j = await _send('GET', '/healthz', null, const Duration(seconds: 5)) as Map;
      final task = j['model_task'] as Map?;
      return Health(
        available: true,
        modelLoaded: j['model_loaded'] == true,
        modelError: j['model_error'] as String?,
        taskStatus: task?['status'] as String?,
        taskFraction: (task?['fraction'] as num?)?.toDouble() ?? 0,
        fileUploads: j['file_uploads'] != false,
      );
    } catch (_) {
      return Health.down;
    }
  }

  Future<void> warmup() async {
    try {
      await _send('POST', '/api/warmup', null, const Duration(seconds: 30));
    } catch (_) {
      // The health poll surfaces any error.
    }
  }

  Future<void> shutdown() => _send('POST', '/api/shutdown', null, const Duration(seconds: 3));

  // ---- conversations ----

  Future<List<Conversation>> listConversations() async {
    final list = await _send('GET', '/api/conversations') as List;
    return list.map((c) => Conversation.fromJson((c as Map).cast<String, dynamic>())).toList();
  }

  Future<Conversation> createConversation() async {
    final j = await _send('POST', '/api/conversations', {'title': null}) as Map;
    return Conversation.fromJson(j.cast<String, dynamic>());
  }

  Future<List<Message>> messages(String conversationId) async {
    final j = await _send('GET', '/api/conversations/$conversationId') as Map;
    return ((j['messages'] as List?) ?? const [])
        .map((m) => Message.fromJson((m as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<void> renameConversation(String id, String title) =>
      _send('PATCH', '/api/conversations/$id', {'title': title});

  Future<void> deleteConversation(String id) => _send('DELETE', '/api/conversations/$id');

  Future<void> stop(String conversationId) =>
      _send('POST', '/api/chat/stop', {'conversation_id': conversationId});

  // ---- models ----

  Future<ModelList> listModels() async {
    final j = (await _send('GET', '/api/models') as Map).cast<String, dynamic>();
    return _modelList(j);
  }

  Future<ModelTask> modelStatus() async {
    final j = await _send('GET', '/api/models/status') as Map;
    return ModelTask.fromJson(j.cast<String, dynamic>());
  }

  Future<void> downloadModel(String spec, {bool thenSwitch = true, List<String> extraSpecs = const []}) =>
      _send('POST', '/api/models/download',
          {'spec': spec, 'then_switch': thenSwitch, 'extra_specs': extraSpecs});

  Future<void> switchModel(String path) => _send('POST', '/api/models/switch', {'path': path});

  Future<ModelList> deleteModel(String path) async {
    final j = (await _send('DELETE', '/api/models', {'path': path}) as Map).cast<String, dynamic>();
    return _modelList(j);
  }

  ModelList _modelList(Map<String, dynamic> j) {
    final catalog = <ModelEntry>[];
    for (final r in (j['catalog'] as List? ?? const []).whereType<Map>()) {
      catalog.add(ModelEntry(
        title: '${r['name']}',
        subtitle: '${r['quant']} · ${r['size_gb']} GB · ${r['note']}',
        path: r['path'] as String?,
        spec: r['spec'] as String?,
        projection: r['projection'] as String?,
        active: r['active'] == true,
        downloaded: r['downloaded'] == true,
      ));
    }
    final custom = <ModelEntry>[];
    for (final c in (j['cached'] as List? ?? const []).whereType<Map>()) {
      if (c['in_catalog'] == true) continue;
      final name = '${c['name']}'.replaceAll(RegExp(r'\.gguf$', caseSensitive: false), '');
      final gb = ((c['size_bytes'] as num?) ?? 0) / 1e9;
      custom.add(ModelEntry(
        title: name,
        subtitle: '${gb.toStringAsFixed(1)} GB',
        path: c['path'] as String?,
        active: c['active'] == true,
        downloaded: true,
      ));
    }
    final active = j['active'] as Map?;
    return ModelList(catalog: catalog, custom: custom, activeName: active?['name'] as String?);
  }

  // ---- chat (SSE) ----

  /// Streams one answer. Cancel the subscription to abort (the caller also
  /// POSTs /api/chat/stop so the backend stops generating).
  Stream<ChatEvent> streamChat({
    required String conversationId,
    required String assistantMessageId,
    String? userMessageId,
    String content = '',
    List<Map<String, String>> attachments = const [],
    bool regenerate = false,
  }) async* {
    final req = http.Request('POST', _u(regenerate ? '/api/chat/regenerate' : '/api/chat/stream'));
    req.headers['Content-Type'] = 'application/json';
    req.body = jsonEncode(regenerate
        ? {'conversation_id': conversationId, 'assistant_message_id': assistantMessageId}
        : {
            'conversation_id': conversationId,
            'content': content,
            'user_message_id': userMessageId,
            'assistant_message_id': assistantMessageId,
            'attachments': attachments,
          });

    final http.StreamedResponse res;
    try {
      res = await _client.send(req);
    } catch (e) {
      yield ErrorEvent('Could not reach the local server ($e)');
      return;
    }
    if (res.statusCode >= 400) {
      final text = await res.stream.bytesToString();
      Object? data;
      try {
        data = jsonDecode(text);
      } catch (_) {}
      yield ErrorEvent(_detail(data, res.statusCode));
      return;
    }

    var terminal = false;
    var event = 'message';
    final dataLines = <String>[];
    ChatEvent? dispatch() {
      if (dataLines.isEmpty) {
        event = 'message';
        return null;
      }
      final raw = dataLines.join('\n');
      dataLines.clear();
      final name = event;
      event = 'message';
      Object? data;
      try {
        data = jsonDecode(raw);
      } catch (_) {
        data = raw;
      }
      switch (name) {
        case 'token':
          return TokenEvent(data is Map ? '${data['text'] ?? ''}' : '$data');
        case 'tool':
          return data is Map ? ToolEvent(ToolCall.fromJson(data.cast<String, dynamic>())) : null;
        case 'stats':
          final s = Stats.fromJson(data);
          return s == null ? null : StatsEvent(s);
        case 'done':
          terminal = true;
          return DoneEvent(data is Map ? '${data['status'] ?? 'done'}' : 'done');
        case 'error':
          terminal = true;
          return ErrorEvent(data is Map ? '${data['message'] ?? 'Generation error'}' : 'Generation error');
      }
      return null;
    }

    try {
      final lines = res.stream.transform(utf8.decoder).transform(const LineSplitter());
      await for (final line in lines) {
        if (line.isEmpty) {
          final e = dispatch();
          if (e != null) yield e;
          if (terminal) return;
          continue;
        }
        if (line.startsWith(':')) continue; // keep-alive comment
        final i = line.indexOf(':');
        final field = i == -1 ? line : line.substring(0, i);
        var value = i == -1 ? '' : line.substring(i + 1);
        if (value.startsWith(' ')) value = value.substring(1);
        if (field == 'event') {
          event = value;
        } else if (field == 'data') {
          dataLines.add(value);
        }
      }
      final e = dispatch();
      if (e != null) yield e;
    } catch (e) {
      if (!terminal) yield ErrorEvent('Connection to the local server was lost ($e)');
      return;
    }
    if (!terminal) yield DoneEvent('done');
  }
}

/// FastAPI's `detail` may be a string, an object or a list; always a string here.
String _detail(Object? data, int status) {
  final d = data is Map ? data['detail'] : null;
  if (d is String && d.isNotEmpty) return d;
  if (d is List && d.isNotEmpty) {
    return d.map((e) => e is Map ? (e['msg'] ?? jsonEncode(e)) : '$e').join('; ');
  }
  if (d is Map) return '${d['msg'] ?? jsonEncode(d)}';
  return 'Server error ($status)';
}
