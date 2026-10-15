# LocalChat desktop app (Flutter)

The window people use. It starts the Python backend (`python -m backend.main`
from the LocalChat folder), talks to it over `http://127.0.0.1:<port>`, and
stops it when the window closes. The backend writes its output to
`LocalChat data/LocalChat.log`.

- `lib/backend.dart` starts/stops the backend; `lib/api.dart` is the HTTP/SSE
  client; `lib/state.dart` holds conversations, streaming and model state;
  `lib/ui/` is the interface.
- CI (`.github/workflows/desktop-app.yml`) builds it for Windows and macOS. The
  workshop export puts the result in each slim repo as `app/LocalChat.zip`,
  which the `Start LocalChat` launcher unpacks on first run.

Build locally (Flutter stable; on Windows, Developer Mode must be on for plugins):

    cd desktop
    flutter build windows   # or: flutter build macos

`Start LocalChat` in the repo root then uses the build in `desktop/build/`.
Run `flutter test` for the unit tests.
