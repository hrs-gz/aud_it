; Inno Setup script for aud_it Windows installer.
; Requires Inno Setup 6+: https://jrsoftware.org/isinfo.php
;
; Build after PyInstaller:
;   pyinstaller aud_it.spec
;   iscc install\aud_it.iss

#define AppName "aud_it"
#define AppVersion "1.0.0"
#define AppPublisher "aud_it"
#define AppExeName "aud_it.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=aud_it-setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Ship the entire PyInstaller one-folder output.
Source: "..\dist\aud_it\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Messages]
WelcomeLabel2=This will install {#AppName}, a local-first PDF redaction desktop app.%n%nUser documents and projects are stored in %APPDATA%\aud_it, not in the install folder.%n%nWebView2 Runtime is required (usually pre-installed on Windows 10/11).
