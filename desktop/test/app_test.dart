// UI test against a fake backend: send a message and check the streamed answer
// renders with its thinking box, tool call and tokens/s line, and that the
// conversation gets a title.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:localchat/api.dart';
import 'package:localchat/main.dart';
import 'package:localchat/state.dart';
import 'package:localchat/ui/theme.dart';

String sse(String event, Object data) => 'event: $event\r\ndata: ${jsonEncode(data)}\r\n\r\n';

class FakeBackend {
  final List<Map<String, dynamic>> streamed = [];
  final List<String> renamed = [];

  late final client = MockClient.streaming((req, body) async {
    final path = req.url.path;
    final text = await body.bytesToString();
    http.StreamedResponse json(Object o, [int status = 200]) => http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode(o))),
          status,
          headers: {'content-type': 'application/json'},
        );

    switch ((req.method, path)) {
      case ('GET', '/healthz'):
        return json({
          'status': 'ok',
          'model_loaded': true,
          'model_error': null,
          'model_task': {'status': 'idle', 'fraction': 0},
          'file_uploads': true,
        });
      case ('POST', '/api/warmup'):
        return json({'model_loaded': true});
      case ('GET', '/api/conversations'):
        return json([]);
      case ('POST', '/api/conversations'):
        return json({'id': 'c1', 'title': '', 'created_at': '2026-10-15T10:00:00', 'updated_at': '2026-10-15T10:00:00'});
      case ('PATCH', '/api/conversations/c1'):
        renamed.add((jsonDecode(text) as Map)['title'] as String);
        return json({'ok': true});
      case ('GET', '/api/models'):
        return json({
          'active': {'name': 'Qwen3-0.6B-Q8_0.gguf', 'path': '/m/Qwen3-0.6B-Q8_0.gguf'},
          'catalog': [],
          'cached': [],
        });
      case ('POST', '/api/chat/stream'):
        streamed.add((jsonDecode(text) as Map).cast<String, dynamic>());
        final frames = [
          sse('token', {'text': '<think>The user wants the time.</think>'}),
          sse('tool', {'id': 1, 'name': 'current_time', 'args': {'city': 'Tokyo'}, 'status': 'running'}),
          sse('tool', {'id': 1, 'name': 'current_time', 'args': {'city': 'Tokyo'}, 'status': 'done', 'result': '14:05'}),
          sse('token', {'text': 'It is **14:05** '}),
          sse('token', {'text': 'in Tokyo.'}),
          sse('stats', {'tokens': 12, 'seconds': 0.5, 'tokens_per_second': 24.0}),
          sse('done', {'status': 'done'}),
        ];
        return http.StreamedResponse(Stream.fromIterable(frames.map(utf8.encode)), 200,
            headers: {'content-type': 'text/event-stream'});
    }
    return json({'detail': 'not found'}, 404);
  });
}

void main() {
  testWidgets('send a message and see the streamed answer', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final backend = FakeBackend();
    final state = AppState(Api(Uri.parse('http://127.0.0.1:1'), client: backend.client));
    await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: Scaffold(body: HomeScreen(state: state))));
    await tester.runAsync(() async {
      await state.init();
      await Future<void>.delayed(const Duration(milliseconds: 100)); // models + health load in the background
    });
    await tester.pump();

    expect(find.text('What can I help with?'), findsOneWidget);
    expect(find.text('Qwen3-0.6B-Q8_0'), findsOneWidget); // model button

    await tester.enterText(find.byType(TextField), 'What time is it in Tokyo?');
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);

    // Let the fake stream play out (tool calls stay "running" >= 1.2 s).
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 1600)));
    // The "Using tool…" hold and the token batching run on the test clock.
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('USING TOOL…'), findsOneWidget);
    await tester.pump(const Duration(seconds: 2));

    expect(backend.streamed.single['content'], 'What time is it in Tokyo?');
    expect(backend.renamed, ['What time is it in Tokyo?']);
    expect(find.text('What time is it in Tokyo?'), findsWidgets); // bubble (+ sidebar title)
    expect(find.text('THOUGHT PROCESS'), findsOneWidget);
    expect(find.text('USED TOOL'), findsOneWidget);
    expect(find.textContaining('24.0 tok/s'), findsOneWidget);
    expect(find.textContaining('14:05', findRichText: true), findsWidgets);
    expect(state.isStreaming, isFalse);
    expect(state.activeMessages.last.status, 'done');
    expect(state.activeMessages.last.content, contains('in Tokyo.'));

    state.dispose();
  });
}
