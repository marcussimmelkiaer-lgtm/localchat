; Inno Setup script for LocalChat (Windows).
;
; Produces ONE file, LocalChat-Setup-x64.exe (~100 MB), that:
;   * installs the frozen app (dist\LocalChat) per-user (no admin needed),
;   * creates Start-menu + optional desktop shortcuts,
;   * ensures the Edge WebView2 runtime is present.
;
; NO models are bundled: Windows won't run a Setup.exe much over ~4 GB, so the
; app downloads its default model (Qwen3-4B, ~2.5 GB) into the NobodyWho cache on
; first launch, with progress in the UI (see backend/bootstrap.py).
;
; The build script (packaging\build_win.ps1) runs PyInstaller BEFORE invoking
; ISCC on this file.
;
; PER-USER by design: PrivilegesRequired=lowest keeps it admin-free, with the app
; under %LOCALAPPDATA%\Programs next to the user's config/DB/model cache.
;
; Signing is deferred: add SignTool config here (and to build_win.ps1) once the
; NobodyWho Authenticode certificate is available.

#define AppName "LocalChat"
#define AppVersion "0.1.0"
#define AppPublisher "NobodyWho"
#define AppExe "LocalChat.exe"

[Setup]
AppId={{7C2E1B90-6E2A-4F1C-9E6E-4B7A2C0D5A10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist\installer
OutputBaseFilename=LocalChat-Setup-x64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Models download on first launch; reserve room for the default so the
; disk-space check warns up front rather than the download failing later.
ExtraDiskSpaceRequired=2600000000
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[InstallDelete]
; Upgrades: wipe the previous version's frozen libraries first. Inno never
; removes files a new version no longer ships, so stale packages (e.g. an old
; nobodywho-*.dist-info or .pyd) would pile up and could shadow the new ones.
; User data lives in %LOCALAPPDATA%\LocalChat, not here, so nothing is lost.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; The frozen app (onedir output from PyInstaller).
Source: "..\..\dist\LocalChat\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Bundled Evergreen WebView2 bootstrapper (tiny; downloads the runtime if needed).
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not WebView2Installed

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

[Run]
; Install the WebView2 runtime silently if it's missing.
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; Flags: waituntilterminated; Check: not WebView2Installed; StatusMsg: "Installing WebView2 runtime..."
; Offer to launch after install.
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2Installed(): Boolean;
var
  v: String;
begin
  // Evergreen runtime registers its version under these keys (per-machine or
  // per-user). Any non-empty pv value means the runtime is present.
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) or
    RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) or
    RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v);
end;
