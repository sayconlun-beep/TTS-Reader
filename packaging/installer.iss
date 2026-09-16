; Inno Setup script: iscc /DAppVersion=1.2.3 packaging\installer.iss
; Per-user install (no admin prompt) of dist\TTSReader from PyInstaller.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1E2B7A-3C94-4D1B-9A7E-52C8D0F4A913}
AppName=TTS Reader
AppVersion={#AppVersion}
AppVerName=TTS Reader {#AppVersion}
DefaultDirName={autopf}\TTS Reader
DefaultGroupName=TTS Reader
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=TTSReader-Setup-{#AppVersion}
SetupIconFile=..\build\icon.ico
UninstallDisplayIcon={app}\TTSReader.exe
UninstallDisplayName=TTS Reader
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\TTSReader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\TTS Reader"; Filename: "{app}\TTSReader.exe"
Name: "{autodesktop}\TTS Reader"; Filename: "{app}\TTSReader.exe"; Tasks: desktopicon

[Registry]
; "Open with" entries for EPUB, PDF, DOCX and Markdown, without taking over the default app.
Root: HKA; Subkey: "Software\Classes\Applications\TTSReader.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "TTS Reader"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\TTSReader.exe\shell\open\command"; ValueType: string; ValueData: """{app}\TTSReader.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Applications\TTSReader.exe\SupportedTypes"; ValueType: string; ValueName: ".epub"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\TTSReader.exe\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\TTSReader.exe\SupportedTypes"; ValueType: string; ValueName: ".docx"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\TTSReader.exe\SupportedTypes"; ValueType: string; ValueName: ".md"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\TTSReader.exe\SupportedTypes"; ValueType: string; ValueName: ".markdown"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.epub\OpenWithList\TTSReader.exe"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithList\TTSReader.exe"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.docx\OpenWithList\TTSReader.exe"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.md\OpenWithList\TTSReader.exe"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.markdown\OpenWithList\TTSReader.exe"; Flags: uninsdeletekey

[Run]
Filename: "{app}\TTSReader.exe"; Description: "{cm:LaunchProgram,TTS Reader}"; Flags: nowait postinstall skipifsilent
