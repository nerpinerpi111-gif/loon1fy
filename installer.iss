[Setup]
AppName=Loonify
AppVersion=1.0
AppPublisher=Loonify
DefaultDirName={localappdata}\Programs\Loonify
DefaultGroupName=Loonify
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Loonify_Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Loonify.exe
WizardImageFile=wizard_big.bmp
WizardSmallImageFile=wizard_small.bmp
Compression=lzma2
SolidCompression=yes
DisableProgramGroupPage=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; Flags: unchecked
Name: "cleandata"; Description: "Начать с чистого листа: удалить старые лайки, историю, сессию и ключи сервисов"

[Files]
Source: "dist\Loonify\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
Type: filesandordirs; Name: "{%USERPROFILE}\.loonify"; Tasks: cleandata

[Icons]
Name: "{group}\Loonify"; Filename: "{app}\Loonify.exe"; IconFilename: "{app}\Loonify.exe"
Name: "{autodesktop}\Loonify"; Filename: "{app}\Loonify.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Loonify.exe"; Description: "Запустить Loonify"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if MsgBox('Удалить также лайки, историю, сессию и сохранённые ключи сервисов?',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON1) = IDYES then
      DelTree(GetEnv('USERPROFILE') + '\.loonify', True, True, True);
end;
