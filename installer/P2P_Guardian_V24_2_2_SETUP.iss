#define MyAppName "P2P Guardian"
#define MyAppVersion "V24.2.2"
#define MyAppPublisher "Bas | Razor"

[Setup]
AppId={{E1B2F1D0-5A7A-4C7D-A4F1-OSRSMONITOR241}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\OSRS Discord Monitor
DefaultGroupName={#MyAppName}
UsePreviousAppDir=yes
OutputDir=Output
OutputBaseFilename=P2P_Guardian_Setup_V24_2_2
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dark polar includetitlebar
WizardSizePercent=120,120
DisableWelcomePage=yes
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
Source: "..\src\osrs_discord_bot.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\src\start_osrs_bot.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\src\support_report.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\src\P2P_Guardian_Control.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\src\P2P_Guardian_Control.vbs"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\P2P Guardian Control"; Filename: "wscript.exe"; Parameters: """{app}\P2P_Guardian_Control.vbs"""; WorkingDir: "{app}"; Comment: "Manage your P2P Guardian Discord bot"
Name: "{group}\P2P Guardian Control"; Filename: "wscript.exe"; Parameters: """{app}\P2P_Guardian_Control.vbs"""; WorkingDir: "{app}"
Name: "{group}\README"; Filename: "{app}\README.md"
Name: "{group}\Create Support Package"; Filename: "pythonw.exe"; Parameters: """{app}\support_report.py"""; WorkingDir: "{app}"
Name: "{userstartup}\OSRS Discord Monitor"; Filename: "pythonw.exe"; Parameters: """{app}\osrs_discord_bot.py"""; WorkingDir: "{app}"

[InstallDelete]
Type: files; Name: "{autodesktop}\OSRS Discord Monitor.lnk"
Type: files; Name: "{group}\OSRS Discord Monitor.lnk"

[Code]
var
  WelcomePage: TWizardPage;
  NoticePage: TWizardPage;
  UpdatePage: TWizardPage;
  PrereqPage: TWizardPage;
  ConfigPage: TInputQueryWizardPage;
  IsExistingInstall: Boolean;
  ConfirmCheck: TNewCheckBox;
  HelpButton: TNewButton;
  ResultCode: Integer;

function IsExistingInstallation(): Boolean;
begin
  Result := RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-OSRSMONITOR241}_is1') or
            RegKeyExists(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-OSRSMONITOR241}_is1') or
            RegKeyExists(HKLM, 'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-OSRSMONITOR241}_is1') or
            RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-9A2E7C6B2410}_is1') or
            RegKeyExists(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-9A2E7C6B2410}_is1') or
            RegKeyExists(HKLM, 'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-9A2E7C6B2410}_is1');
end;

procedure HelpButtonClick(Sender: TObject);
begin
  MsgBox(
    'P2P Guardian needs your own Discord bot.' + #13#10 + #13#10 +
    '1. Create an application in the Discord Developer Portal.' + #13#10 +
    '2. Open Bot and create the bot.' + #13#10 +
    '3. Copy the Bot Token and keep it private.' + #13#10 +
    '4. Open OAuth2 > URL Generator.' + #13#10 +
    '5. Select: bot and applications.commands.' + #13#10 +
    '6. Select: View Channels, Send Messages,' + #13#10 +
    '   Embed Links, Attach Files.' + #13#10 +
    '7. Use the generated URL to add the bot to your server.' + #13#10 +
    '8. Return here and enter your token and Discord IDs.' + #13#10 + #13#10 +
    'Administrator permission is not required.' + #13#10 +
    'Never share your bot token.',
    mbInformation, MB_OK);
  ShellExec('open', 'https://discord.com/developers/applications', '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
end;

procedure InitializeWizard;
var
  TitleText: TNewStaticText;
  SubtitleText: TNewStaticText;
  InfoText: TNewStaticText;
  BrandText: TNewStaticText;
begin
  IsExistingInstall := IsExistingInstallation();

  WelcomePage := CreateCustomPage(wpWelcome,
    'P2P GUARDIAN',
    'V24.2.2 - Guided Windows Setup');
  WelcomePage.Surface.Color := $202838;

  TitleText := TNewStaticText.Create(WizardForm);
  TitleText.Parent := WelcomePage.Surface;
  TitleText.Caption := 'Welcome to P2P Guardian';
  TitleText.Left := ScaleX(30);
  TitleText.Top := ScaleY(35);
  TitleText.Width := WelcomePage.SurfaceWidth - ScaleX(60);
  TitleText.Height := ScaleY(30);
  TitleText.Font.Size := 14;

  SubtitleText := TNewStaticText.Create(WizardForm);
  SubtitleText.Parent := WelcomePage.Surface;
  SubtitleText.Caption := 'A clean, guided setup for the P2P Guardian Discord Monitor.';
  SubtitleText.Left := ScaleX(30);
  SubtitleText.Top := ScaleY(80);
  SubtitleText.Width := WelcomePage.SurfaceWidth - ScaleX(60);
  SubtitleText.Height := ScaleY(25);
  SubtitleText.Font.Size := 10;

  InfoText := TNewStaticText.Create(WizardForm);
  InfoText.Parent := WelcomePage.Surface;
  if IsExistingInstall then
    InfoText.Caption :=
      'UPDATE AVAILABLE:' + #13#10 +
      'An existing P2P Guardian installation was detected.' + #13#10 +
      'Your Discord token and configuration will be preserved.' + #13#10 +
      'Only the program files will be updated.'
  else
    InfoText.Caption :=
      'NEW INSTALLATION:' + #13#10 +
      'A Discord bot created through the Discord Developer Portal is required.';
  InfoText.Left := ScaleX(30);
  InfoText.Top := ScaleY(125);
  InfoText.Width := WelcomePage.SurfaceWidth - ScaleX(60);
  InfoText.Height := ScaleY(75);
  InfoText.Font.Size := 10;

  BrandText := TNewStaticText.Create(WizardForm);
  BrandText.Parent := WelcomePage.Surface;
  BrandText.Caption := 'Developed by Bas | Razor';
  BrandText.Left := WelcomePage.SurfaceWidth - ScaleX(200);
  BrandText.Top := WelcomePage.SurfaceHeight - ScaleY(28);
  BrandText.Width := ScaleX(180);
  BrandText.Height := ScaleY(18);
  BrandText.Alignment := taRightJustify;
  BrandText.Font.Size := 9;

  if IsExistingInstall then
  begin
    UpdatePage := CreateCustomPage(WelcomePage.ID,
      'What''s New in V24.2.2',
      'New features and improvements in this update');
    UpdatePage.Surface.Color := $202838;

    InfoText := TNewStaticText.Create(WizardForm);
    InfoText.Parent := UpdatePage.Surface;
    InfoText.Caption :=
      '- Improved installer update detection' + #13#10 +
      '- Existing token and Discord settings are preserved' + #13#10 +
      '- Guided first-time Discord bot setup' + #13#10 +
      '- Developer Portal instructions and required permissions' + #13#10 +
      '- Improved P2P Guardian Control interface' + #13#10 +
      '- Improved bot startup and management';
    InfoText.Left := ScaleX(25);
    InfoText.Top := ScaleY(25);
    InfoText.Width := UpdatePage.SurfaceWidth - ScaleX(50);
    InfoText.Height := ScaleY(150);
    InfoText.Font.Size := 10;
  end
  else
  begin
    NoticePage := CreateCustomPage(WelcomePage.ID,
      'Important Notice',
      'Please read before installing P2P Guardian');
    NoticePage.Surface.Color := $202838;

    InfoText := TNewStaticText.Create(WizardForm);
    InfoText.Parent := NoticePage.Surface;
    InfoText.Caption :=
      'P2P Guardian is provided as-is.' + #13#10 + #13#10 +
      'You are responsible for how you use this software.' + #13#10 +
      'The developer is not responsible for OSRS or Discord bans,' + #13#10 +
      'account restrictions, data loss, system damage, or other' + #13#10 +
      'direct or indirect consequences resulting from its use.' + #13#10 + #13#10 +
      'USE AT YOUR OWN RISK.';
    InfoText.Left := ScaleX(25);
    InfoText.Top := ScaleY(22);
    InfoText.Width := NoticePage.SurfaceWidth - ScaleX(50);
    InfoText.Height := ScaleY(180);
    InfoText.Font.Size := 10;
  end;

  if IsExistingInstall then
    PrereqPage := CreateCustomPage(UpdatePage.ID,
      'Discord Bot Requirement',
      'P2P Guardian requires a Discord bot created in the Discord Developer Portal')
  else
    PrereqPage := CreateCustomPage(NoticePage.ID,
      'Discord Bot Requirement',
      'P2P Guardian requires a Discord bot created in the Discord Developer Portal');
  PrereqPage.Surface.Color := $202838;

  InfoText := TNewStaticText.Create(WizardForm);
  InfoText.Parent := PrereqPage.Surface;
  InfoText.Caption :=
    'IMPORTANT: P2P Guardian does not create a Discord bot.' + #13#10 + #13#10 +
    'You need:' + #13#10 +
    '- A bot created in the Discord Developer Portal' + #13#10 +
    '- The bot added to your Discord server' + #13#10 +
    '- Your bot token' + #13#10 + #13#10 +
    'OAuth2 scopes: bot + applications.commands' + #13#10 +
    'Permissions: View Channels, Send Messages,' + #13#10 +
    'Embed Links, Attach Files' + #13#10 +
    'Administrator permission is not required.';
  InfoText.Left := ScaleX(20);
  InfoText.Top := ScaleY(18);
  InfoText.Width := PrereqPage.SurfaceWidth - ScaleX(40);
  InfoText.Height := ScaleY(180);
  InfoText.Font.Size := 9;

  ConfirmCheck := TNewCheckBox.Create(WizardForm);
  ConfirmCheck.Parent := PrereqPage.Surface;
  ConfirmCheck.Caption := 'I already have the required Discord bot and token.';
  ConfirmCheck.Left := ScaleX(20);
  ConfirmCheck.Top := ScaleY(195);
  ConfirmCheck.Width := PrereqPage.SurfaceWidth - ScaleX(40);
  ConfirmCheck.Height := ScaleY(22);

  HelpButton := TNewButton.Create(WizardForm);
  HelpButton.Parent := PrereqPage.Surface;
  HelpButton.Caption := 'I do not have a Discord bot yet - show me how';
  HelpButton.Left := ScaleX(20);
  HelpButton.Top := ScaleY(228);
  HelpButton.Width := ScaleX(330);
  HelpButton.Height := ScaleY(28);
  HelpButton.OnClick := @HelpButtonClick;

  ConfigPage := CreateInputQueryPage(PrereqPage.ID,
    'Discord Configuration',
    'Enter your Discord bot settings',
    'These settings are requested only during a first-time installation. Existing installations keep their current settings during updates.');
  ConfigPage.Add('Discord bot token:', True);
  ConfigPage.Add('Notification channel ID:', False);
  ConfigPage.Add('Task notification channel ID:', False);
  ConfigPage.Add('Level-up channel ID:', False);
  ConfigPage.Add('Your Discord user ID (for personal pings):', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = PrereqPage.ID then
  begin
    if not ConfirmCheck.Checked then
    begin
      MsgBox('Please confirm that you already have a Discord bot created in the Discord Developer Portal before installing P2P Guardian.', mbInformation, MB_OK);
      Result := False;
    end;
  end
  else if CurPageID = ConfigPage.ID then
  begin
    if Trim(ConfigPage.Values[0]) = '' then
    begin
      MsgBox('Please enter your Discord bot token.', mbInformation, MB_OK);
      Result := False;
    end
    else if (Trim(ConfigPage.Values[1]) = '') or (Trim(ConfigPage.Values[2]) = '') or
            (Trim(ConfigPage.Values[3]) = '') or (Trim(ConfigPage.Values[4]) = '') then
    begin
      MsgBox('Please enter all Discord channel IDs and your Discord user ID.', mbInformation, MB_OK);
      Result := False;
    end;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if IsExistingInstall then
  begin
    if (PageID = PrereqPage.ID) or (PageID = ConfigPage.ID) or
       (PageID = wpSelectDir) or (PageID = wpSelectProgramGroup) then
      Result := True;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  TokenText: String;
  ConfigText: String;
begin
  if (CurStep = ssPostInstall) and (not IsExistingInstall) then
  begin
    TokenText := ConfigPage.Values[0];
    ConfigText := '{' + #13#10 +
      '  "notify_channel_id": ' + ConfigPage.Values[1] + ',' + #13#10 +
      '  "task_notify_channel_id": ' + ConfigPage.Values[2] + ',' + #13#10 +
      '  "level_notify_channel_id": ' + ConfigPage.Values[3] + ',' + #13#10 +
      '  "ping_user_id": ' + ConfigPage.Values[4] + #13#10 +
      '}';
    SaveStringToFile(ExpandConstant('{app}\discord_token.txt'), TokenText + #13#10, False);
    SaveStringToFile(ExpandConstant('{app}\osrs_bot_config.json'), ConfigText + #13#10, False);
  end;
end;
