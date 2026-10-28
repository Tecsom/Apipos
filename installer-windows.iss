; Inno Setup script for Apipos (Windows installer).
; Build with:  iscc installer-windows.iss   (after build-windows.bat created dist\Apipos.exe)
; Download Inno Setup: https://jrsoftware.org/isdl.php

; Defaults — overridable from build-windows.bat via:  iscc /DAppName=... /DAppVersion=... /DAppPublisher=...
#ifndef AppName
  #define AppName "Apipos"
#endif
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Tecsom"
#endif
#define AppExe AppName + ".exe"

[Setup]
AppId={{B8E7B0C2-1A4D-4E6F-9C3A-7D2E5F018A4B}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename={#AppName}-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
; Apipos is a tray app that keeps {app}\Apipos.exe in use. PrepareToInstall
; ([Code]) closes it before any file is copied; CloseApplications stays as the
; fallback. RestartApplications=no: the only new instance is the [Run] entry.
CloseApplications=yes
RestartApplications=no
; Setup log (%TEMP%\Setup Log *.txt); [Code] copies it to {app}\install.log.
SetupLogging=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"

[Registry]
; Start with Windows automatically (always). The app also self-registers on
; first run, but this guarantees autostart even on a silent install.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; \
  Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Ejecutar {#AppName} ahora"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; The uninstaller hits the same "file in use" problem: close the app first.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM {#AppExe}"; \
  Flags: runhidden; RunOnceId: "CloseApp"

[UninstallDelete]
Type: files; Name: "{app}\install.log"

[Code]
// Apipos must not be running while its .exe is replaced; otherwise the old
// instance survives next to the one started by [Run] after the install.

var
  InstallFinished: Boolean;

function AppIsRunning(): Boolean;
var
  ResultCode: Integer;
begin
  // `find` exits with 0 only when the image name appears in tasklist's output.
  Result := Exec(ExpandConstant('{cmd}'),
    '/C tasklist /FI "IMAGENAME eq {#AppExe}" | find /I "{#AppExe}" >nul',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure KillApp();
var
  ResultCode: Integer;
begin
  // /T also kills the PyInstaller onefile child process; /F because the tray
  // process has no visible window to close gracefully.
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM {#AppExe}',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Log(Format('KillApp: taskkill exit code %d.', [ResultCode]));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Attempt: Integer;
begin
  Result := '';
  if not AppIsRunning() then
  begin
    Log('PrepareToInstall: {#AppExe} is not running.');
    Exit;
  end;
  Log('PrepareToInstall: {#AppExe} is running; closing it with taskkill.');
  KillApp();
  // taskkill returns before the processes are fully gone: poll up to ~10 s.
  for Attempt := 1 to 40 do
  begin
    if not AppIsRunning() then
    begin
      Log(Format('PrepareToInstall: {#AppExe} closed (check %d).', [Attempt]));
      Exit;
    end;
    Sleep(250);
  end;
  Log('PrepareToInstall: {#AppExe} still running after 10 s; stopping Setup.');
  Result := 'No se pudo cerrar {#AppName}. Ciérralo desde la bandeja del sistema (Salir) y vuelve a intentar.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then
    InstallFinished := True;
end;

procedure DeinitializeSetup();
begin
  // Setup writes its log to %TEMP%: keep a copy next to the app, where support
  // can ask for it. DeinitializeSetup also runs when Setup is cancelled early
  // ({app} not set yet), hence the flag.
  if InstallFinished then
    FileCopy(ExpandConstant('{log}'), ExpandConstant('{app}\install.log'), False);
end;
