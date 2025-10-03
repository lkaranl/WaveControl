; Script de instalação para WaveControl
; Empacota o executável gerado pelo PyInstaller com ícone personalizado

[Setup]
AppName=WaveControl
AppVersion=1.0
AppPublisher=Karan Luciano
AppPublisherURL=https://github.com/lkaranl
AppSupportURL=https://github.com/lkaranl/suporte
AppUpdatesURL=https://github.com/lkaranl/atualizacoes
DefaultDirName={pf}\WaveControl
DefaultGroupName=WaveControl
AllowNoIcons=yes
OutputDir=C:\Users\karan\Documents\GitHub\WaveControl\instalador
OutputBaseFilename=WaveControlSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
SetupIconFile=C:\Users\karan\Documents\GitHub\WaveControl\appimage\img\WaveControll.png

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked
Name: "startmenuicon"; Description: "Criar atalho no menu Iniciar"; GroupDescription: "Atalhos adicionais:"

[Files]
Source: "C:\Users\karan\Documents\GitHub\WaveControl\dist\WaveControl.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\karan\Documents\GitHub\WaveControl\appimage\img\WaveControll.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\WaveControl"; Filename: "{app}\WaveControl.exe"; IconFilename: "{app}\WaveControll.png"
Name: "{userdesktop}\WaveControl"; Filename: "{app}\WaveControl.exe"; IconFilename: "{app}\WaveControll.png"; Tasks: desktopicon
Name: "{userstartmenu}\WaveControl"; Filename: "{app}\WaveControl.exe"; IconFilename: "{app}\WaveControll.png"; Tasks: startmenuicon

[Run]
Filename: "{app}\WaveControl.exe"; Description: "Executar WaveControl"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
