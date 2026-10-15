// Data shapes shared by the API client, the app state and the UI. They mirror
// the backend's JSON (backend/schemas.py) with Dart-friendly names.

import 'dart:typed_data';

class Conversation {
  Conversation({required this.id, required this.title, required this.updatedAt});

  final String id;
  String title;
  DateTime updatedAt;

  factory Conversation.fromJson(Map<String, dynamic> j) => Conversation(
        id: j['id'] as String,
        title: (j['title'] as String?) ?? '',
        updatedAt: DateTime.tryParse((j['updated_at'] ?? j['created_at'] ?? '') as String) ??
            DateTime.now(),
      );
}

class Stats {
  const Stats({this.tokens = 0, this.seconds = 0, this.tokensPerSecond = 0});

  final int tokens;
  final double seconds;
  final double tokensPerSecond;

  static Stats? fromJson(Object? j) {
    if (j is! Map) return null;
    return Stats(
      tokens: (j['tokens'] as num?)?.toInt() ?? 0,
      seconds: (j['seconds'] as num?)?.toDouble() ?? 0,
      tokensPerSecond: (j['tokens_per_second'] as num?)?.toDouble() ?? 0,
    );
  }
}

class ToolCall {
  ToolCall({required this.id, required this.name, required this.args, required this.status, this.result});

  final int id;
  final String name;
  final Map<String, dynamic> args;
  final String status; // running | done | error
  final String? result;

  factory ToolCall.fromJson(Map<String, dynamic> j) => ToolCall(
        id: (j['id'] as num?)?.toInt() ?? 0,
        name: (j['name'] as String?) ?? '',
        args: (j['args'] as Map?)?.cast<String, dynamic>() ?? const {},
        status: (j['status'] as String?) ?? 'done',
        result: j['result']?.toString(),
      );
}

class Attachment {
  Attachment({required this.name, required this.mime, this.size = 0, this.isImage = false, this.previewBytes});

  final String name;
  final String mime;
  final int size;
  final bool isImage;

  /// Local bytes for an image just sent (before it can be re-served by the backend).
  final Uint8List? previewBytes;

  factory Attachment.fromJson(Map<String, dynamic> j) {
    final mime = (j['mime'] as String?) ?? '';
    return Attachment(
      name: (j['name'] as String?) ?? 'file',
      mime: mime,
      size: (j['size'] as num?)?.toInt() ?? 0,
      isImage: j['is_image'] == true || mime.startsWith('image/'),
    );
  }
}

class Message {
  Message({
    required this.id,
    required this.role,
    this.content = '',
    this.status = 'done',
    this.stats,
    this.error,
    List<Attachment>? attachments,
    List<ToolCall>? toolCalls,
  })  : attachments = attachments ?? [],
        toolCalls = toolCalls ?? [];

  final String id;
  final String role; // user | assistant
  String content;
  String status; // streaming | done | stopped | error
  Stats? stats;
  String? error;
  final List<Attachment> attachments;
  List<ToolCall> toolCalls;

  factory Message.fromJson(Map<String, dynamic> j) => Message(
        id: j['id'] as String,
        role: j['role'] as String,
        content: (j['content'] as String?) ?? '',
        status: (j['status'] as String?) ?? 'done',
        stats: Stats.fromJson(j['stats']),
        error: j['error'] as String?,
        attachments: ((j['attachments'] as List?) ?? const [])
            .whereType<Map>()
            .map((a) => Attachment.fromJson(a.cast<String, dynamic>()))
            .toList(),
        toolCalls: ((j['tool_calls'] as List?) ?? const [])
            .whereType<Map>()
            .map((c) => ToolCall.fromJson(c.cast<String, dynamic>()))
            .toList(),
      );
}

class Health {
  const Health({
    required this.available,
    this.modelLoaded = false,
    this.modelError,
    this.taskStatus,
    this.taskFraction = 0,
    this.fileUploads = true,
  });

  final bool available;
  final bool modelLoaded;
  final String? modelError;
  final String? taskStatus;
  final double taskFraction;
  final bool fileUploads;

  static const down = Health(available: false);
}

/// One row of GET /api/models: a curated catalog entry or a cached custom file.
class ModelEntry {
  ModelEntry({
    required this.title,
    required this.subtitle,
    required this.path,
    this.spec,
    this.projection,
    this.active = false,
    this.downloaded = false,
  });

  final String title;
  final String subtitle;
  final String? path;
  final String? spec;
  final String? projection;
  final bool active;
  final bool downloaded;
}

class ModelList {
  ModelList({required this.catalog, required this.custom, this.activeName});

  final List<ModelEntry> catalog;
  final List<ModelEntry> custom;
  final String? activeName;
}

class ModelTask {
  const ModelTask({this.status = 'idle', this.fraction = 0, this.error, this.target});

  final String status; // idle | downloading | loading | ready | error
  final double fraction;
  final String? error;
  final String? target;

  bool get busy => status == 'downloading' || status == 'loading';

  factory ModelTask.fromJson(Map<String, dynamic> j) => ModelTask(
        status: (j['status'] as String?) ?? 'idle',
        fraction: (j['fraction'] as num?)?.toDouble() ?? 0,
        error: j['error'] as String?,
        target: j['target'] as String?,
      );
}
