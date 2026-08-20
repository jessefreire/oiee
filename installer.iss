; Instalador do Oiee — compile com Inno Setup 6:
;   ISCC.exe installer.iss
; Requisito: rodar build_exe.ps1 antes (gera dist\Oiee.exe).

#define MyAppName "Oiee"
#define MyAppVersion "0.1.0"
#define MyAppExeName "Oiee.exe"

[Setup]
AppId={{8C4F9D2E-5B7A-4C3D-9E1F-2A6B8C0D4E5F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Oiee
AppPublisherURL=https://github.com/SEU_USUARIO/oiee
; Instalação por usuário: sem necessidade de administrador (sem UAC)
PrivilegesRequired=lowest
DefaultDirName={autopf}\Oiee
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=Oiee-Setup-{#MyAppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
