#ifndef SiaVersion
  #error SiaVersion must be supplied using /DSiaVersion=v18.14
#endif
#define AppName "시아애비 블로그 자동작성기"
#define MainExe "SiaAebiBlogWriter.exe"

[Setup]
AppId=SiaAebiBlogWriter
AppName={#AppName}
AppVersion={#SiaVersion}
AppVerName={#AppName} {#SiaVersion}
AppPublisher=시아애비
DefaultDirName={localappdata}\Programs\SiaAebiBlogWriter
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=..\installer_dist
OutputBaseFilename=SiaAebiBlogWriter_Setup_{#SiaVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=siaaebi_icon.ico
UninstallDisplayIcon={app}\siaaebi_icon.ico
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "payload\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "siaaebi_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\app\{#MainExe}"; WorkingDir: "{app}\app"; IconFilename: "{app}\siaaebi_icon.ico"
Name: "{userprograms}\{#AppName}"; Filename: "{app}\app\{#MainExe}"; WorkingDir: "{app}\app"; IconFilename: "{app}\siaaebi_icon.ico"

[Run]
Filename: "{app}\app\{#MainExe}"; Description: "시아애비 블로그 자동작성기 실행"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: dirifempty; Name: "{app}\app"
