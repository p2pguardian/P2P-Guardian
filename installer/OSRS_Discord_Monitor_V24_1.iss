#define MyAppName "OSRS Discord Monitor"
#define MyAppVersion "V24.1"
#define MyAppPublisher "Bas | Razor"
#define MyAppExeName "osrs_discord_bot.py"

[Setup]
AppId={{E1B2F1D0-5A7A-4C7D-A4F1-OSRSMONITOR241}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://discord.com/
DefaultDirName={autopf}\OSRS Discord Monitor
DefaultGroupName={#MyAppName}
OutputDir=Output
OutputBaseFilename=OSRS_Discord_Monitor_Setup_V24_1
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dark polar includetitlebar
WizardSizePercent=120,120
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=no
SetupLogging=yes
Uninstallable=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "payload\osrs_discord_bot.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "payload\start_osrs_bot.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "payload\README.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "payload\support_report.py"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\OSRS Discord Monitor"; Tasks: desktopicon; Filename: "{code:PythonWExe}"; Parameters: """{app}\osrs_discord_bot.py"""; WorkingDir: "{app}"; Comment: "OSRS Discord Monitor"
Name: "{group}\OSRS Discord Monitor"; Filename: "{code:PythonWExe}"; Parameters: """{app}\osrs_discord_bot.py"""; WorkingDir: "{app}"
Name: "{group}\README"; Filename: "{app}\README.txt"
Name: "{group}\Create Support Package"; Filename: "{code:PythonWExe}"; Parameters: """{app}\support_report.py"""; WorkingDir: "{app}"
Name: "{autodesktop}\OSRS Discord Monitor Support"; Check: SupportShortcutSelected; Filename: "{code:PythonWExe}"; Parameters: """{app}\support_report.py"""; WorkingDir: "{app}"; Comment: "Create a diagnostic package for bug reports"
Name: "{userstartup}\OSRS Discord Monitor"; Filename: "{code:PythonWExe}"; Parameters: """{app}\osrs_discord_bot.py"""; WorkingDir: "{app}"; Tasks: autostart

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "autostart"; Description: "Start automatically when Windows signs in"; Flags: unchecked

[Run]
Filename: "{code:PythonWExe}"; Parameters: """{app}\osrs_discord_bot.py"""; WorkingDir: "{app}"; Description: "Launch OSRS Discord Monitor"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
Type: files; Name: "{app}\discord_token.txt"
Type: files; Name: "{app}\osrs_bot_config.json"

[Code]
var
  WelcomePage: TWizardPage;
  ConfigPage: TInputQueryWizardPage;
  PathPage: TWizardPage;
  DetuksEdit: TNewEdit;
  JagexEdit: TNewEdit;
  DetuksAutoButton: TNewButton;
  DetuksBrowseButton: TNewButton;
  JagexAutoButton: TNewButton;
  JagexBrowseButton: TNewButton;
  DetuksStatus: TNewStaticText;
  JagexStatus: TNewStaticText;
  OptionsPage: TInputOptionWizardPage;
  PythonPage: TInputOptionWizardPage;
  LegalPage: TWizardPage;
  LegalMemo: TNewMemo;
  PythonExePath: String;
  PythonWExePath: String;

function JsonEscape(const S: String): String;
begin
  Result := S;
  StringChangeEx(Result, '\\', '\\\\', True);
  StringChangeEx(Result, '"', '\\"', True);
end;

function FileExistsAny(const Names: array of String; var Found: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  Found := '';
  for I := 0 to GetArrayLength(Names) - 1 do
  begin
    if FileExists(Names[I]) then
    begin
      Found := Names[I];
      Result := True;
      Exit;
    end;
  end;
end;

function FindPythonFromPyLauncher: String;
var
  ResultCode: Integer;
  Output: TExecOutput;
  I: Integer;
  S: String;
begin
  Result := '';
  try
    if ExecAndCaptureOutput(ExpandConstant('{sys}\py.exe'), '-3.13 -c "import sys; print(sys.executable)"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode, Output) then
    begin
      if ResultCode = 0 then
      begin
        for I := 0 to GetArrayLength(Output.StdOut) - 1 do
        begin
          S := Trim(Output.StdOut[I]);
          if (S <> '') and FileExists(S) then
          begin
            Result := S;
            Exit;
          end;
        end;
      end;
    end;
  except
  end;
end;

function FindPythonExe: String;
var
  Candidates: array[0..5] of String;
  Found: String;
begin
  Result := FindPythonFromPyLauncher;
  if Result <> '' then Exit;

  Candidates[0] := ExpandConstant('{localappdata}\Programs\Python\Python313\python.exe');
  Candidates[1] := ExpandConstant('{localappdata}\Programs\Python\Python312\python.exe');
  Candidates[2] := ExpandConstant('{autopf}\Python313\python.exe');
  Candidates[3] := ExpandConstant('{autopf32}\Python313\python.exe');
  Candidates[4] := ExpandConstant('{sys}\python.exe');
  Candidates[5] := ExpandConstant('{syswow64}\python.exe');

  if FileExistsAny(Candidates, Found) then
    Result := Found
  else
    Result := '';
end;

function PythonWExe(Param: String): String;
begin
  if PythonWExePath = '' then
  begin
    if PythonExePath = '' then PythonExePath := FindPythonExe;
    if PythonExePath <> '' then
      PythonWExePath := AddBackslash(ExtractFileDir(PythonExePath)) + 'pythonw.exe';
  end;
  Result := PythonWExePath;
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  PythonExePath := FindPythonExe;
  PythonWExePath := '';
end;

function FindDetuksRoot: String;
var
  Candidate: String;
begin
  Result := '';
  Candidate := AddBackslash(GetEnv('USERPROFILE')) + '.detuksosrs';
  if DirExists(Candidate) then
  begin
    Result := Candidate;
    Exit;
  end;
  Candidate := AddBackslash(GetEnv('LOCALAPPDATA')) + '.detuksosrs';
  if DirExists(Candidate) then
    Result := Candidate;
end;

function IsJagexLauncherDirectory(const Candidate: String): Boolean;
begin
  Result :=
    FileExists(AddBackslash(Candidate) + 'Jagex Launcher.exe') or
    FileExists(AddBackslash(Candidate) + 'JagexLauncher.exe');
end;

function FindJagexInRegistry(const RootKey: HKEY; const UninstallKey: String): String;
var
  Names: TArrayOfString;
  I: Integer;
  SubKey: String;
  InstallLocation: String;
  DisplayIcon: String;
  Candidate: String;
begin
  Result := '';
  if not RegGetSubkeyNames(RootKey, UninstallKey, Names) then Exit;

  for I := 0 to GetArrayLength(Names) - 1 do
  begin
    SubKey := UninstallKey + '\' + Names[I];
    InstallLocation := '';
    DisplayIcon := '';

    if RegQueryStringValue(RootKey, SubKey, 'InstallLocation', InstallLocation) then
    begin
      Candidate := RemoveQuotes(Trim(InstallLocation));
      if IsJagexLauncherDirectory(Candidate) then
      begin
        Result := Candidate;
        Exit;
      end;
    end;

    if RegQueryStringValue(RootKey, SubKey, 'DisplayIcon', DisplayIcon) then
    begin
      Candidate := RemoveQuotes(Trim(DisplayIcon));
      if Pos(',', Candidate) > 0 then
        Candidate := Copy(Candidate, 1, Pos(',', Candidate) - 1);
      if FileExists(Candidate) then
      begin
        if (CompareText(ExtractFileName(Candidate), 'Jagex Launcher.exe') = 0) or
           (CompareText(ExtractFileName(Candidate), 'JagexLauncher.exe') = 0) then
        begin
          Result := ExtractFileDir(Candidate);
          Exit;
        end;
      end;
    end;
  end;
end;

function FindJagexLauncherDirectory: String;
var
  Candidates: array[0..5] of String;
  I: Integer;
  Candidate: String;
begin
  Result := '';

  { Common locations documented by Jagex, plus common per-user locations. }
  Candidates[0] := AddBackslash(GetEnv('ProgramFiles(x86)')) + 'Jagex Launcher';
  Candidates[1] := AddBackslash(GetEnv('ProgramW6432')) + 'Jagex Launcher';
  Candidates[2] := AddBackslash(GetEnv('LOCALAPPDATA')) + 'Programs\Jagex Launcher';
  Candidates[3] := AddBackslash(GetEnv('LOCALAPPDATA')) + 'Jagex Launcher';
  Candidates[4] := AddBackslash(GetEnv('PROGRAMDATA')) + 'Jagex Launcher';
  Candidates[5] := AddBackslash(GetEnv('ProgramFiles')) + 'Jagex Launcher';

  for I := 0 to GetArrayLength(Candidates) - 1 do
  begin
    Candidate := Candidates[I];
    if IsJagexLauncherDirectory(Candidate) then
    begin
      Result := Candidate;
      Exit;
    end;
  end;

  { Fallback: read the installed application's location from Windows registry. }
  Result := FindJagexInRegistry(HKEY_LOCAL_MACHINE_32,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall');
  if Result <> '' then Exit;
  Result := FindJagexInRegistry(HKEY_LOCAL_MACHINE_64,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall');
  if Result <> '' then Exit;
  Result := FindJagexInRegistry(HKEY_CURRENT_USER,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall');
end;

procedure SetPathStatus(StatusLabel: TNewStaticText; const Text: String);
begin
  StatusLabel.Caption := Text;
end;

procedure DetuksAutoClick(Sender: TObject);
var
  Found: String;
begin
  Found := FindDetuksRoot;
  if Found <> '' then
  begin
    DetuksEdit.Text := Found;
    SetPathStatus(DetuksStatus, 'Detected automatically.');
  end
  else
    SetPathStatus(DetuksStatus, 'Not found automatically. Use Browse to select it.');
end;

procedure DetuksBrowseClick(Sender: TObject);
var
  Dir: String;
begin
  Dir := DetuksEdit.Text;
  if BrowseForFolder('Select your .detuksosrs folder', Dir, False) then
  begin
    DetuksEdit.Text := Dir;
    SetPathStatus(DetuksStatus, 'Folder selected.');
  end;
end;

procedure JagexAutoClick(Sender: TObject);
var
  Found: String;
begin
  Found := FindJagexLauncherDirectory;
  if Found <> '' then
  begin
    JagexEdit.Text := Found;
    SetPathStatus(JagexStatus, 'Detected automatically.');
  end
  else
    SetPathStatus(JagexStatus, 'Not found automatically. Use Browse to select it.');
end;

procedure JagexBrowseClick(Sender: TObject);
var
  Dir: String;
begin
  Dir := JagexEdit.Text;
  if BrowseForFolder('Select your Jagex Launcher folder', Dir, False) then
  begin
    JagexEdit.Text := Dir;
    SetPathStatus(JagexStatus, 'Folder selected.');
  end;
end;

function SupportShortcutSelected: Boolean;
begin
  Result := OptionsPage <> nil;
  if Result then
    Result := OptionsPage.Values[3];
end;

procedure AddBrandFooter(Page: TWizardPage);
var
  Brand: TNewStaticText;
begin
  Brand := TNewStaticText.Create(WizardForm);
  Brand.Parent := Page.Surface;
  Brand.Caption := 'Developed by Bas | Razor';
  Brand.Left := ScaleX(20);
  Brand.Top := Page.SurfaceHeight - ScaleY(28);
  Brand.Width := Page.SurfaceWidth - ScaleX(40);
  Brand.Height := ScaleY(18);
  Brand.Alignment := taRightJustify;
  Brand.Font.Size := 9;
end;

procedure AddBrandHeaderRight(Page: TWizardPage);
var
  Brand: TNewStaticText;
begin
  Brand := TNewStaticText.Create(WizardForm);
  Brand.Parent := Page.Surface;
  Brand.Caption := 'Developed by Bas | Razor';
  Brand.Left := Page.SurfaceWidth - ScaleX(190);
  Brand.Top := ScaleY(2);
  Brand.Width := ScaleX(180);
  Brand.Height := ScaleY(18);
  Brand.Alignment := taRightJustify;
  Brand.Font.Size := 9;
end;

procedure InitializeWizard;
begin
  WizardForm.Caption := 'OSRS Discord Monitor Setup V24.1';

  WelcomePage := CreateCustomPage(wpWelcome,
    'OSRS DISCORD MONITOR',
    'V24.1 Stable - Guided Windows Setup');
  with WelcomePage do
  begin
    with Surface do
    begin
      Color := $202838;
    end;
    with TNewStaticText.Create(WizardForm) do
    begin
      Parent := WelcomePage.Surface;
      Caption := 'A clean, guided setup for the stable V24.1 OSRS Discord Monitor.';
      Left := ScaleX(30);
      Top := ScaleY(35);
      Width := ScaleX(680);
      Height := ScaleY(25);
      Font.Size := 12;
    end;
    with TNewStaticText.Create(WizardForm) do
    begin
      Parent := WelcomePage.Surface;
      Caption := 'Simple setup for Discord, client paths, and startup options.';
      Left := ScaleX(30);
      Top := ScaleY(75);
      Width := ScaleX(680);
      Height := ScaleY(25);
      Font.Size := 10;
    end;
  end;

  LegalPage := CreateCustomPage(WelcomePage.ID,
    'Important Notice',
    'Please read this notice before continuing.');
  LegalMemo := TNewMemo.Create(WizardForm);
  LegalMemo.Parent := LegalPage.Surface;
  LegalMemo.Left := ScaleX(15);
  LegalMemo.Top := ScaleY(10);
  LegalMemo.Width := LegalPage.SurfaceWidth - ScaleX(30);
  LegalMemo.Height := ScaleY(210);
  LegalMemo.ReadOnly := True;
  LegalMemo.ScrollBars := ssVertical;
  LegalMemo.Text :=
    'IMPORTANT NOTICE' + #13#10#13#10 +
    'Use this software at your own risk. The developer is not responsible for account restrictions, bans, data loss, system damage, downtime, or any direct or indirect damage resulting from the use of this software.' + #13#10#13#10 +
    'This software is provided as-is. You are responsible for complying with Jagex / OSRS rules, Discord rules, and all other applicable rules.' + #13#10#13#10 +
    'By continuing you confirm that you understand and accept these terms.';

  ConfigPage := CreateInputQueryPage(LegalPage.ID,
    'Bot Configuration',
    'Enter your Discord and Jagex settings.',
    'Required fields are marked. Optional fields may be left empty.');
  ConfigPage.Add('Discord bot token:', True);
  ConfigPage.Add('Alert channel ID:', False);
  ConfigPage.Add('Task channel ID:', False);
  ConfigPage.Add('Level-up channel ID (optional):', False);
  ConfigPage.Add('Ping user ID (optional):', False);

  PathPage := CreateCustomPage(ConfigPage.ID,
    'Client Paths',
    'Automatically detect or browse for the folders used by the monitor.');

  with TNewStaticText.Create(PathPage) do
  begin
    Parent := PathPage.Surface;
    Caption := 'Detuks log root:';
    Left := ScaleX(20);
    Top := ScaleY(18);
    Width := ScaleX(180);
    Height := ScaleY(18);
  end;

  DetuksEdit := TNewEdit.Create(PathPage);
  DetuksEdit.Parent := PathPage.Surface;
  DetuksEdit.Left := ScaleX(20);
  DetuksEdit.Top := ScaleY(40);
  DetuksEdit.Width := ScaleX(300);
  DetuksEdit.Height := ScaleY(23);
  DetuksEdit.Anchors := [akLeft, akTop, akRight];

  DetuksAutoButton := TNewButton.Create(PathPage);
  DetuksAutoButton.Parent := PathPage.Surface;
  DetuksAutoButton.Caption := 'Auto-detect';
  DetuksAutoButton.Left := ScaleX(330);
  DetuksAutoButton.Top := ScaleY(40);
  DetuksAutoButton.Width := ScaleX(95);
  DetuksAutoButton.Height := ScaleY(23);
  DetuksAutoButton.OnClick := @DetuksAutoClick;

  DetuksBrowseButton := TNewButton.Create(PathPage);
  DetuksBrowseButton.Parent := PathPage.Surface;
  DetuksBrowseButton.Caption := 'Browse...';
  DetuksBrowseButton.Left := ScaleX(430);
  DetuksBrowseButton.Top := ScaleY(40);
  DetuksBrowseButton.Width := ScaleX(80);
  DetuksBrowseButton.Height := ScaleY(23);
  DetuksBrowseButton.OnClick := @DetuksBrowseClick;

  DetuksStatus := TNewStaticText.Create(PathPage);
  DetuksStatus.Parent := PathPage.Surface;
  DetuksStatus.Caption := 'Checking...';
  DetuksStatus.Left := ScaleX(20);
  DetuksStatus.Top := ScaleY(68);
  DetuksStatus.Width := ScaleX(490);
  DetuksStatus.Height := ScaleY(18);

  with TNewStaticText.Create(PathPage) do
  begin
    Parent := PathPage.Surface;
    Caption := 'Jagex Launcher folder:';
    Left := ScaleX(20);
    Top := ScaleY(100);
    Width := ScaleX(220);
    Height := ScaleY(18);
  end;

  JagexEdit := TNewEdit.Create(PathPage);
  JagexEdit.Parent := PathPage.Surface;
  JagexEdit.Left := ScaleX(20);
  JagexEdit.Top := ScaleY(122);
  JagexEdit.Width := ScaleX(300);
  JagexEdit.Height := ScaleY(23);

  JagexAutoButton := TNewButton.Create(PathPage);
  JagexAutoButton.Parent := PathPage.Surface;
  JagexAutoButton.Caption := 'Auto-detect';
  JagexAutoButton.Left := ScaleX(330);
  JagexAutoButton.Top := ScaleY(122);
  JagexAutoButton.Width := ScaleX(95);
  JagexAutoButton.Height := ScaleY(23);
  JagexAutoButton.OnClick := @JagexAutoClick;

  JagexBrowseButton := TNewButton.Create(PathPage);
  JagexBrowseButton.Parent := PathPage.Surface;
  JagexBrowseButton.Caption := 'Browse...';
  JagexBrowseButton.Left := ScaleX(430);
  JagexBrowseButton.Top := ScaleY(122);
  JagexBrowseButton.Width := ScaleX(80);
  JagexBrowseButton.Height := ScaleY(23);
  JagexBrowseButton.OnClick := @JagexBrowseClick;

  JagexStatus := TNewStaticText.Create(PathPage);
  JagexStatus.Parent := PathPage.Surface;
  JagexStatus.Caption := 'Checking...';
  JagexStatus.Left := ScaleX(20);
  JagexStatus.Top := ScaleY(150);
  JagexStatus.Width := ScaleX(490);
  JagexStatus.Height := ScaleY(18);

  DetuksEdit.Text := FindDetuksRoot;
  if DetuksEdit.Text <> '' then
    DetuksStatus.Caption := 'Detected automatically.'
  else
    DetuksStatus.Caption := 'Not found automatically. Use Browse to select it.';

  JagexEdit.Text := FindJagexLauncherDirectory;
  if JagexEdit.Text <> '' then
    JagexStatus.Caption := 'Detected automatically.'
  else
    JagexStatus.Caption := 'Not found automatically. Use Browse to select it.';

  PythonPage := CreateInputOptionPage(PathPage.ID,
    'Installation Options',
    'Choose what the installer should do.',
    'Python is installed only if needed and only when you leave the option enabled.',
    False, False);
  PythonPage.Add('Install Python 3.13.15 if needed (download from python.org)');
  PythonPage.Add('Install required Python packages');
  PythonPage.Values[0] := True;
  PythonPage.Values[1] := True;

  OptionsPage := CreateInputOptionPage(PythonPage.ID,
    'Shortcuts and Startup',
    'Choose optional shortcuts and automatic startup.',
    'Choose which shortcuts and startup behavior you want.',
    False, False);
  OptionsPage.Add('Create a desktop shortcut');
  OptionsPage.Add('Start automatically when Windows signs in');
  OptionsPage.Add('Launch the bot after installation');
  OptionsPage.Add('Create a desktop support shortcut');
  OptionsPage.Values[0] := True;
  OptionsPage.Values[1] := False;
  OptionsPage.Values[2] := True;
  OptionsPage.Values[3] := True;

  AddBrandFooter(WelcomePage);
  AddBrandFooter(LegalPage);
  AddBrandHeaderRight(ConfigPage);
  AddBrandFooter(PathPage);
  AddBrandFooter(PythonPage);
  AddBrandFooter(OptionsPage);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if CurPageID = LegalPage.ID then
  begin
    if MsgBox('Do you confirm that you have read and accept the Important Notice?', mbConfirmation, MB_YESNO) <> IDYES then
      Result := False;
  end;

  if (CurPageID = ConfigPage.ID) then
  begin
    if Trim(ConfigPage.Values[0]) = '' then
    begin
      MsgBox('Please enter the Discord bot token.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if Trim(ConfigPage.Values[1]) = '' then
    begin
      MsgBox('Please enter the Alert channel ID.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if Trim(ConfigPage.Values[2]) = '' then
    begin
      MsgBox('Please enter the Task channel ID.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;

  if CurPageID = PathPage.ID then
  begin
    if Trim(DetuksEdit.Text) = '' then
    begin
      MsgBox('Please select your .detuksosrs folder using Auto-detect or Browse.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if not DirExists(Trim(DetuksEdit.Text)) then
    begin
      MsgBox('The selected Detuks log root does not exist. Please use Auto-detect or Browse.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if Trim(JagexEdit.Text) = '' then
    begin
      MsgBox('Please select your Jagex Launcher folder using Auto-detect or Browse.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if not DirExists(Trim(JagexEdit.Text)) then
    begin
      MsgBox('The selected Jagex Launcher folder does not exist. Please use Auto-detect or Browse.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Url, InstallerPath: String;
  ResultCode: Integer;
begin
  Result := '';
  NeedsRestart := False;

  PythonExePath := FindPythonExe;
  if PythonExePath = '' then
  begin
    if not PythonPage.Values[0] then
    begin
      Result := 'Python 3.13 was not found. Enable the Python installation option and run Setup again.';
      Exit;
    end;

    Url := 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe';
    InstallerPath := ExpandConstant('{tmp}\python-3.13.15-amd64.exe');
    try
      DownloadTemporaryFile(Url, 'python-3.13.15-amd64.exe', '', nil);
      if not FileExists(InstallerPath) then
      begin
        Result := 'Python was downloaded but the installer file could not be found.';
        Exit;
      end;
      if Exec(InstallerPath, '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      begin
        if ResultCode <> 0 then
        begin
          Result := 'Python installation failed with exit code ' + IntToStr(ResultCode) + '.';
          Exit;
        end;
      end
      else
      begin
        Result := 'The Python installer could not be started.';
        Exit;
      end;
      PythonExePath := FindPythonExe;
      if PythonExePath = '' then
      begin
        Result := 'Python was installed, but Setup could not locate python.exe. Please restart Setup.';
        Exit;
      end;
    except
      Result := 'Python download/install failed: ' + GetExceptionMessage;
      Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  ConfigPath, TokenPath, PkgCommand, ConfigText: String;
begin
  if CurStep <> ssPostInstall then Exit;

  ConfigPath := ExpandConstant('{app}\osrs_bot_config.json');
  TokenPath := ExpandConstant('{app}\discord_token.txt');

  SaveStringToFile(TokenPath, Trim(ConfigPage.Values[0]) + #13#10, False);
  ConfigText := '{' +
    '"notify_channel_id": "' + JsonEscape(Trim(ConfigPage.Values[1])) + '",' +
    '"task_notify_channel_id": "' + JsonEscape(Trim(ConfigPage.Values[2])) + '",' +
    '"level_notify_channel_id": "' + JsonEscape(Trim(ConfigPage.Values[3])) + '",' +
    '"ping_user_id": "' + JsonEscape(Trim(ConfigPage.Values[4])) + '",' +
    '"log_root_directory": "' + JsonEscape(Trim(DetuksEdit.Text)) + '",' +
    '"jagex_launcher_directory": "' + JsonEscape(Trim(JagexEdit.Text)) + '"' +
    '}';
  SaveStringToFile(ConfigPath, ConfigText + #13#10, False);

  if PythonPage.Values[1] then
  begin
    PkgCommand := '-m pip install --disable-pip-version-check discord.py pillow psutil pytesseract opencv-python numpy pygetwindow pywin32';
    Exec(PythonExePath, PkgCommand, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if ResultCode <> 0 then
      MsgBox('Some Python packages could not be installed. You can rerun the installer or install them manually from the README.', mbError, MB_OK);
  end;

  if OptionsPage.Values[2] then
  begin
    Exec(PythonWExePath, '"' + ExpandConstant('{app}\osrs_discord_bot.py') + '"', ExpandConstant('{app}'), SW_HIDE, ewNoWait, ResultCode);
  end;
end;
