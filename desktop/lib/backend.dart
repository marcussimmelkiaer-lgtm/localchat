// Starts the Python backend (`python -m backend.main`) from the LocalChat folder,
// learns its port from the first line it prints, writes its output to
// "LocalChat data/LocalChat.log", and stops it when the window closes.
//
// The LocalChat folder is found by walking up from this executable until a
// folder containing backend/main.py appears, so it works for the shipped app
// (app/LocalChat/…exe, app/LocalChat.app/Contents/MacOS/…) and for a dev build
// (desktop/build/…) alike. LOCALCHAT_ROOT overrides it.

import 'dart:async';
import 'dart:convert';
import 'dart:io';

class BackendException implements Exception {
  BackendException(this.message);
  final String message;
  @override
  String toString() => message;
}

class Backend {
  Backend._(this.root, this._process, this.url, this._log);

  final Directory root;
  final Process _process;
  final Uri url;
  final IOSink _log;
  bool _stopped = false;

  /// The folder that holds backend/, venv/ and config.toml.
  static Directory findRoot() {
    final override = Platform.environment['LOCALCHAT_ROOT'];
    if (override != null && override.isNotEmpty) return Directory(override);
    var dir = File(Platform.resolvedExecutable).parent;
    for (var i = 0; i < 12; i++) {
      if (File('${dir.path}/backend/main.py').existsSync()) return dir;
      final parent = dir.parent;
      if (parent.path == dir.path) break;
      dir = parent;
    }
    throw BackendException(
      'Could not find the LocalChat folder (backend/main.py) next to this app. '
      'Start LocalChat with the "Start LocalChat" file in the LocalChat folder.',
    );
  }

  static Future<Backend> start() async {
    final root = findRoot();
    final python = Platform.isWindows
        // pythonw: no console window flashes up next to the app.
        ? File('${root.path}\\venv\\Scripts\\pythonw.exe')
        : File('${root.path}/venv/bin/python');
    if (!python.existsSync()) {
      throw BackendException(
        'LocalChat is not set up yet (${python.path} is missing). '
        'Double-click "Start LocalChat" in the LocalChat folder to finish the setup.',
      );
    }

    final dataDir = Directory('${root.path}${Platform.pathSeparator}LocalChat data')
      ..createSync(recursive: true);
    final log = File('${dataDir.path}${Platform.pathSeparator}LocalChat.log')
        .openWrite(mode: FileMode.write);

    final process = await Process.start(
      python.path,
      ['-u', '-m', 'backend.main'],
      workingDirectory: root.path,
      environment: {
        'LOCALCHAT_PARENT_PID': '$pid', // the backend quits if this app dies
        'PYTHONUNBUFFERED': '1',
        'PYTHONIOENCODING': 'utf-8',
      },
    );

    final portFound = Completer<Uri>();
    final listening = RegExp(r'listening on (http://\S+)');
    void onLine(String line) {
      log.writeln(line);
      final m = listening.firstMatch(line);
      if (m != null && !portFound.isCompleted) portFound.complete(Uri.parse(m.group(1)!));
    }

    process.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen(onLine);
    process.stderr.transform(utf8.decoder).transform(const LineSplitter()).listen(onLine);
    unawaited(process.exitCode.then((code) {
      log.writeln('[desktop] backend exited with code $code');
      if (!portFound.isCompleted) {
        portFound.completeError(BackendException(
          'The LocalChat backend stopped while starting (exit code $code). '
          'See "LocalChat data/LocalChat.log" in the LocalChat folder for details.',
        ));
      }
    }));

    try {
      final url = await portFound.future.timeout(const Duration(seconds: 120));
      return Backend._(root, process, url, log);
    } on TimeoutException {
      process.kill();
      throw BackendException('The LocalChat backend did not start within 2 minutes. '
          'See "LocalChat data/LocalChat.log" in the LocalChat folder.');
    }
  }

  /// Ask the backend to stop (it saves any answer in progress as "stopped"),
  /// then make sure it is gone.
  Future<void> stop() async {
    if (_stopped) return;
    _stopped = true;
    try {
      final client = HttpClient()..connectionTimeout = const Duration(seconds: 2);
      final req = await client.postUrl(url.resolve('/api/shutdown'));
      final res = await req.close().timeout(const Duration(seconds: 3));
      await res.drain<void>();
      client.close(force: true);
    } catch (_) {
      // Not answering: fall through to the kill below.
    }
    final exited = await _process.exitCode
        .then((_) => true)
        .timeout(const Duration(seconds: 8), onTimeout: () => false);
    if (!exited) _process.kill(ProcessSignal.sigkill);
    await _log.flush();
    await _log.close();
  }
}
