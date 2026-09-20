#define MyAppName "P2P Guardian"
#define MyAppVersion "24.2.5"
#define MyAppVersionDisplay "V24.2.5"
#define MyAppVersionFile "24_2_5"
#define MyAppPublisher "Bas | Razor"

; PRIVATE BUILD CONFIG (optional): keep private_install_tracking.iss out of GitHub.
#ifexist "private_install_tracking.iss"
#include "private_install_tracking.iss"
#else
#define GUARDIAN_INSTALL_ENDPOINT ""
#define GUARDIAN_INSTALL_CLIENT_KEY ""
#endif

#define MyAppChange1 "Windows Graphics Capture for minimized and background OSRS clients"
#define MyAppChange2 "Persistent WGC capture sessions for faster screenshots"
#define MyAppChange3 "Per-account status and PID-specific screenshot selection"
#define MyAppChange4 "Adaptive Discord embed text and automatic Python dependency setup"

[Setup]
AppId={{E1B2F1D0-5A7A-4C7D-A4F1-OSRSMONITOR241}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersionDisplay}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\P2P Guardian
DefaultGroupName={#MyAppName}
UsePreviousAppDir=yes
OutputDir=Output
OutputBaseFilename=P2P_Guardian_Setup
Compression=lzma2/fast
SolidCompression=no
WizardStyle=modern dark polar hidebevels includetitlebar
WizardBackColor=$001F1303
WizardBackColorDynamicDark=$001F1303
WizardImageFile=
WizardSmallImageFile=
WizardSizePercent=100,100
DisableWelcomePage=yes
DisableDirPage=no
SetupIconFile=..\payload\P2P_Guardian_Logo.ico
UninstallDisplayIcon={app}\P2P_Guardian_Logo.ico
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=no
SetupLogging=yes
; V27: background is loaded once in InitializeWizard; no runtime page-change reloads.
Uninstallable=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\payload\osrs_discord_bot.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\payload\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\payload\dependency_check.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\payload\support_report.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\payload\native_controller_publish\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "..\payload\P2P_Guardian_Logo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\payload\P2P_Guardian_Desktop.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\payload\P2P_Guardian_Logo.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\payload\P2P_Guardian_Folder.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\payload\guardian_version.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\payload\P2P_Guardian_Logo.png"; Flags: dontcopy
Source: "..\payload\P2P_Guardian_Logo.ico"; Flags: dontcopy
Source: "..\payload\P2P_Guardian_Wizard_Back_New_1152.png"; Flags: dontcopy
Source: "..\payload\P2P_Guardian_Wizard_Back_Update_1152.png"; Flags: dontcopy

[Icons]
Name: "{autodesktop}\P2P Guardian Control"; Filename: "{app}\P2P_Guardian_Control.exe"; WorkingDir: "{app}"; Comment: "Manage your P2P Guardian Discord bot"; IconFilename: "{app}\P2P_Guardian_Desktop.ico"; IconIndex: 0; AppUserModelID: "P2PGuardian.Control"
Name: "{group}\P2P Guardian Control"; Filename: "{app}\P2P_Guardian_Control.exe"; WorkingDir: "{app}"; IconFilename: "{app}\P2P_Guardian_Desktop.ico"; IconIndex: 0; AppUserModelID: "P2PGuardian.Control"
Name: "{userstartup}\P2P Guardian"; Filename: "pythonw.exe"; Parameters: """{app}\osrs_discord_bot.py"""; WorkingDir: "{app}"; IconFilename: "{app}\P2P_Guardian_Logo.ico"; IconIndex: 0

[InstallDelete]
Type: files; Name: "{autodesktop}\OSRS Discord Monitor.lnk"
Type: files; Name: "{group}\OSRS Discord Monitor.lnk"
Type: files; Name: "{userstartup}\OSRS Discord Monitor.lnk"
Type: files; Name: "{app}\P2P_Guardian_Control.ps1"
Type: files; Name: "{app}\P2P_Guardian_Control.vbs"
Type: files; Name: "{app}\start_osrs_bot.bat"
Type: files; Name: "{app}\README.txt"
Type: files; Name: "{app}\P2P_Guardian_Control_TESTED_BASELINE.exe"
Type: filesandordirs; Name: "{app}\native_controller"
Type: files; Name: "{app}\P2P_Guardian_Control.pdb"

[UninstallDelete]
Type: files; Name: "{app}\P2P_Guardian_Control.ps1"
Type: files; Name: "{app}\P2P_Guardian_Control.vbs"
Type: files; Name: "{app}\start_osrs_bot.bat"
Type: files; Name: "{app}\README.txt"
Type: files; Name: "{app}\P2P_Guardian_Control_TESTED_BASELINE.exe"
Type: filesandordirs; Name: "{app}\native_controller"
Type: files; Name: "{app}\P2P_Guardian_Control.pdb"
Type: files; Name: "{userstartup}\OSRS Discord Monitor.lnk"

[Code]
const
  GuardianBg = $001F1303;       { #03131F }
  GuardianCard = $00291A06;    { #061A29 }
  GuardianInner = $00352209;   { #092235 }
  GuardianBorder = $004F3817;  { #17384F }
  GuardianLine = $00D98F00;    { #008FD9 }
  GuardianBlue = $00EFAE00;    { #00AEEF }
  GuardianBright = $00FF8800;  { #0088FF }
  GuardianNext = $00D96600;    { #0066D9 }
  GuardianText = $00FAF6F2;    { #F2F6FA }
  GuardianMuted = $00D8C9B8;   { #B8C9D8 }
  GuardianSuccess = $0053DB4D; { #4DDB83 }

var
  LandingPage: TWizardPage;
  PrereqPage: TWizardPage;
  ConfigPage: TWizardPage;
  DirPage: TWizardPage;
  ReadyGuardianPage: TWizardPage;
  FinishedGuardianPage: TWizardPage;
  FinishedPageActive: Boolean;
  IsExistingInstall: Boolean;
  ExistingInstallDir: String;
  ConfirmCheck: TNewCheckBox;
  HelpButton: TNewButton;
  TokenEdit: TNewEdit;
  NotifyEdit: TNewEdit;
  TaskEdit: TNewEdit;
  LevelEdit: TNewEdit;
  PingEdit: TNewEdit;
  GuardianDirEdit: TNewEdit;
  ReadySummary: TNewStaticText;
  ChangeSummaryMemo: TNewMemo;
  InstalledVersion: String;
  InstallStatus: TNewStaticText;
  InstallPercent: TNewStaticText;
  InstallProgressBack: TPanel;
  InstallProgressFill: TPanel;
  ResultCode: Integer;
  GuardianBackButton: TPanel;
  GuardianNextButton: TPanel;
  GuardianCancelButton: TPanel;
  GuardianNextLabel: TNewStaticText;
  GuardianCancelLabel: TNewStaticText;
  GuardianFooter: TPanel;
GuardianFooterInfo: TPanel;
  LandingImage: TBitmapImage;
  LandingPng: TPngImage;
  BrandPng: TPngImage;
  LandingOverlay: TPanel;
  GuardianTopRight: TPanel;
  GuardianTopRightTitle: TNewStaticText;
  GuardianTopRightSlogan: TNewStaticText;
  GuardianTopRightLine: TPanel;
  InstallTrackingId: String;
  PythonExecutable: String;

function UnscaleX(Pixels: Integer): Integer;
begin
  Result := (Pixels * 100) div ScaleX(100);
end;

function UnscaleY(Pixels: Integer): Integer;
begin
  Result := (Pixels * 100) div ScaleY(100);
end;

function GetSystemMetrics(nIndex: Integer): Integer;
external 'GetSystemMetrics@user32.dll stdcall';

procedure PostMessage(hWnd: Integer; Msg, wParam, lParam: Integer);
external 'PostMessageA@user32.dll stdcall';

const
  WM_CLOSE = $0010;

{ V84: full-client Guardian frame; landing raster frame disabled; common footer used on every page. }
procedure SizeWizardToScreen;
var
  ScreenW, ScreenH, TargetW, TargetH: Integer;
begin
  ScreenW := UnscaleX(GetSystemMetrics(0));
  ScreenH := UnscaleY(GetSystemMetrics(1));
  TargetW := (ScreenW * 60) div 100;
  if TargetW < 960 then TargetW := 960;
  if TargetW > 1200 then TargetW := 1200;
  TargetH := (TargetW * 760) div 1152;
  if TargetH < 650 then TargetH := 650;
  if TargetH > 780 then TargetH := 780;
  if TargetH > (ScreenH * 80) div 100 then TargetH := (ScreenH * 80) div 100;
  if TargetW > (ScreenW * 72) div 100 then TargetW := (ScreenW * 72) div 100;
  WizardForm.ClientWidth := ScaleX(TargetW);
  WizardForm.ClientHeight := ScaleY(TargetH);
end;

procedure ExpandWizardCanvas;
var
  ContentH: Integer;
begin
  { V86: the modern Inno wizard keeps the custom page notebook inside
    an inset InnerPage/OuterNotebook. Resize those real containers, not
    only TWizardPage.Surface, so the Guardian frame can reach the window
    client edges. The custom footer is overlaid afterwards. }
  ContentH := WizardForm.ClientHeight - ScaleY(74);
  if ContentH < ScaleY(500) then ContentH := WizardForm.ClientHeight;

  WizardForm.OuterNotebook.Left := 0;
  WizardForm.OuterNotebook.Top := 0;
  WizardForm.OuterNotebook.Width := WizardForm.ClientWidth;
  WizardForm.OuterNotebook.Height := ContentH;

  WizardForm.InnerPage.Left := 0;
  WizardForm.InnerPage.Top := 0;
  WizardForm.InnerPage.Width := WizardForm.OuterNotebook.ClientWidth;
  WizardForm.InnerPage.Height := WizardForm.OuterNotebook.ClientHeight;

  WizardForm.InnerNotebook.Left := 0;
  WizardForm.InnerNotebook.Top := 0;
  WizardForm.InnerNotebook.Width := WizardForm.InnerPage.ClientWidth;
  WizardForm.InnerNotebook.Height := WizardForm.InnerPage.ClientHeight;
end;

procedure HelpButtonClick(Sender: TObject); forward;
procedure BrowseDirClick(Sender: TObject); forward;
procedure BackPanelClick(Sender: TObject); forward;
procedure NextPanelClick(Sender: TObject); forward;
procedure CancelPanelClick(Sender: TObject); forward;
procedure FinishCloseClick(Sender: TObject); forward;
procedure CreateGlobalTopRight; forward;
procedure WizardCloseQuery(Sender: TObject; var CanClose: Boolean); forward;
procedure ExitProcess(ExitCode: Integer); external 'ExitProcess@kernel32.dll stdcall';


procedure StyleEdit(Control: TNewEdit; X, Y, W, H: Integer);
begin
  Control.Left := ScaleX(X);
  Control.Top := ScaleY(Y);
  Control.Width := ScaleX(W);
  Control.Height := ScaleY(H);
  Control.Color := GuardianCard;
  Control.Font.Name := 'Segoe UI';
  Control.Font.Size := 10;
  Control.Font.Color := GuardianText;
  Control.StyleElements := [];
end;

procedure StyleText(Control: TNewStaticText; Size: Integer; Bold: Boolean; TextColor: TColor);
begin
  Control.StyleElements := [];
  if Bold then Control.Font.Name := 'Segoe UI Semibold'
  else Control.Font.Name := 'Segoe UI';
  Control.Font.Size := Size;
  Control.Font.Color := TextColor;
  Control.Font.Style := [];
end;

function AddText(Parent: TWinControl; CaptionText: String; X, Y, W, H, Size: Integer; Bold: Boolean; TextColor: TColor): TNewStaticText;
begin
  Result := TNewStaticText.Create(WizardForm);
  Result.Parent := Parent;
  Result.Caption := CaptionText;
  Result.Left := ScaleX(X);
  Result.Top := ScaleY(Y);
  Result.Width := ScaleX(W);
  Result.Height := ScaleY(H);
  Result.AutoSize := False;
  Result.Alignment := taLeftJustify;
  StyleText(Result, Size, Bold, TextColor);
end;

function AddCard(Parent: TWinControl; X, Y, W, H: Integer): TPanel;
var
  Border: TPanel;
begin
  Border := TPanel.Create(WizardForm);
  Border.Parent := Parent;
  Border.Left := ScaleX(X);
  Border.Top := ScaleY(Y);
  Border.Width := ScaleX(W);
  Border.Height := ScaleY(H);
  Border.Color := GuardianLine;
  Border.BevelOuter := bvNone;
  Border.ParentBackground := False;
  Border.StyleElements := [];

  Result := TPanel.Create(WizardForm);
  Result.Parent := Parent;
  Result.Left := ScaleX(X + 1);
  Result.Top := ScaleY(Y + 1);
  Result.Width := ScaleX(W - 2);
  Result.Height := ScaleY(H - 2);
  Result.Color := GuardianCard;
  Result.BevelOuter := bvNone;
  Result.ParentBackground := False;
  Result.StyleElements := [];
end;

function AddFlatSection(Parent: TWinControl; X, Y, W, H: Integer): TPanel;
begin
  Result := TPanel.Create(WizardForm);
  Result.Parent := Parent;
  Result.Left := ScaleX(X);
  Result.Top := ScaleY(Y);
  Result.Width := ScaleX(W);
  Result.Height := ScaleY(H);
  Result.Color := GuardianCard;
  Result.BevelOuter := bvNone;
  Result.ParentBackground := False;
  Result.StyleElements := [];
end;

procedure AddVerticalDivider(Parent: TWinControl; X, Y, H: Integer);
var
  Line: TPanel;
begin
  Line := TPanel.Create(WizardForm);
  Line.Parent := Parent;
  Line.Left := ScaleX(X);
  Line.Top := ScaleY(Y);
  Line.Width := ScaleX(1);
  Line.Height := ScaleY(H);
  Line.Color := GuardianBorder;
  Line.BevelOuter := bvNone;
  Line.ParentBackground := False;
  Line.StyleElements := [];
end;

procedure AddBrandPanel(Parent: TWinControl; X, Y, W, H: Integer; TitleText, SubText: String);
var
  LogoBitmap: TBitmapImage;
  Line: TPanel;
  BrandTitle, BrandSub, BrandSlogan: TNewStaticText;
begin
  { Clean branding column: no box around the logo, matching the landing composition. }
  if not Assigned(BrandPng) then
  begin
    ExtractTemporaryFile('P2P_Guardian_Logo.png');
    BrandPng := TPngImage.Create;
    BrandPng.LoadFromFile(ExpandConstant('{tmp}\P2P_Guardian_Logo.png'));
  end;

  LogoBitmap := TBitmapImage.Create(WizardForm);
  LogoBitmap.Parent := Parent;
  LogoBitmap.Left := ScaleX(X + ((W - 220) div 2));
  LogoBitmap.Top := ScaleY(Y + 28);
  LogoBitmap.Width := ScaleX(220);
  LogoBitmap.Height := ScaleY(220);
  LogoBitmap.Stretch := True;
  LogoBitmap.BackColor := GuardianCard;
  LogoBitmap.PngImage := BrandPng;

  BrandTitle := AddText(Parent, TitleText, X + 8, Y + 255, W - 16, 30, 17, True, GuardianBlue);
  BrandTitle.Alignment := taCenter;
  BrandSub := AddText(Parent, SubText, X + 8, Y + 287, W - 16, 22, 10, True, GuardianMuted);
  BrandSub.Alignment := taCenter;

  Line := TPanel.Create(WizardForm);
  Line.Parent := Parent;
  Line.Left := ScaleX(X + 48);
  Line.Top := ScaleY(Y + 321);
  Line.Width := ScaleX(W - 96);
  Line.Height := ScaleY(1);
  Line.Color := GuardianBorder;
  Line.BevelOuter := bvNone;
  Line.ParentBackground := False;
  Line.StyleElements := [];
  BrandSlogan := AddText(Parent, 'PLAY SMARTER  •  STAY SAFER', X + 8, Y + 337, W - 16, 24, 10, True, GuardianBlue);
  BrandSlogan.Alignment := taCenter;
end;

procedure AddLandingFooter;
var
  Line: TPanel;
  LogoImage: TBitmapImage;
begin
  { Cover the rasterized footer text from the artwork and redraw it sharply. }
  LandingOverlay := TPanel.Create(WizardForm);
  LandingOverlay.Parent := LandingPage.Surface;
  LandingOverlay.Left := ScaleX(24);
  LandingOverlay.Top := ScaleY(553);
  LandingOverlay.Width := ScaleX(1104);
  LandingOverlay.Height := ScaleY(40);
  LandingOverlay.Color := GuardianBg;
  LandingOverlay.BevelOuter := bvNone;
  LandingOverlay.ParentBackground := False;
  LandingOverlay.StyleElements := [];

  Line := TPanel.Create(WizardForm);
  Line.Parent := LandingOverlay;
  Line.Left := ScaleX(17);
  Line.Top := 0;
  Line.Width := LandingOverlay.Width - ScaleX(34);
  Line.Height := ScaleY(1);
  Line.Color := GuardianLine;
  Line.BevelOuter := bvNone;
  Line.ParentBackground := False;
  Line.StyleElements := [];

  LogoImage := TBitmapImage.Create(WizardForm);
  LogoImage.Parent := LandingOverlay;
  LogoImage.Left := ScaleX(18);
  LogoImage.Top := ScaleY(15);
  LogoImage.Width := ScaleX(24);
  LogoImage.Height := ScaleY(24);
  LogoImage.Stretch := True;
  LogoImage.BackColor := GuardianBg;
  LogoImage.PngImage := BrandPng;

  AddText(LandingOverlay, 'P2P Guardian', 52, 12, 135, 28, 11, True, GuardianBlue);
  AddText(LandingOverlay, 'OSRS Discord Monitor', 190, 12, 170, 28, 11, False, GuardianMuted);
  AddText(LandingOverlay, 'Developed by Bas  |  Razor', 372, 12, 260, 28, 11, False, GuardianMuted);
  AddText(LandingOverlay, 'V24.2.5', 1008, 12, 78, 28, 11, False, GuardianMuted);
end;

procedure CreateLandingOverlay;
var
  Cover, MainCard, InnerCard, RightFrame, UpdateCard, Line, Divider: TPanel;
  LogoImage: TBitmapImage;
  StatusTitle, StatusLine1, StatusLine2: String;
  BrandTitle, BrandSub, BrandSlogan: TNewStaticText;
begin
  { The original landing artwork remains the visual backdrop. The central
    content is redrawn with native controls so text stays crisp at runtime. }
  Cover := TPanel.Create(WizardForm);
  Cover.Parent := LandingPage.Surface;
  Cover.Left := ScaleX(24);
  Cover.Top := ScaleY(18);
  Cover.Width := ScaleX(1104);
  Cover.Height := ScaleY(84);
  Cover.Color := GuardianBg;
  Cover.BevelOuter := bvNone;
  Cover.ParentBackground := False;
  Cover.StyleElements := [];

  LogoImage := TBitmapImage.Create(WizardForm);
  LogoImage.Parent := Cover;
  LogoImage.Left := ScaleX(2);
  LogoImage.Top := ScaleY(10);
  LogoImage.Width := ScaleX(48);
  LogoImage.Height := ScaleY(52);
  LogoImage.Stretch := True;
  LogoImage.BackColor := GuardianBg;
  LogoImage.PngImage := BrandPng;
  AddText(Cover, 'P2P GUARDIAN', 56, 12, 360, 30, 17, True, GuardianBlue);
  AddText(Cover, 'V24.2.5  •  GUARDIAN WINDOWS SETUP', 56, 40, 420, 20, 9, True, GuardianMuted);
  { The right-side branding is supplied by the single WizardForm-level
    GuardianTopRight panel created after all pages. Do not create a second
    page-local copy here; that was the source of the page-to-page shift. }

  MainCard := TPanel.Create(WizardForm);
  MainCard.Parent := LandingPage.Surface;
  MainCard.Left := ScaleX(24);
  MainCard.Top := ScaleY(108);
  MainCard.Width := ScaleX(1104);
  MainCard.Height := ScaleY(500);
  MainCard.Color := GuardianLine;
  MainCard.BevelOuter := bvNone;
  MainCard.ParentBackground := False;
  MainCard.StyleElements := [];

  InnerCard := TPanel.Create(WizardForm);
  InnerCard.Parent := MainCard;
  InnerCard.Left := 1;
  InnerCard.Top := 1;
  InnerCard.Width := MainCard.Width - 2;
  InnerCard.Height := MainCard.Height - 2;
  InnerCard.Color := GuardianCard;
  InnerCard.BevelOuter := bvNone;
  InnerCard.ParentBackground := False;
  InnerCard.StyleElements := [];

  Divider := TPanel.Create(WizardForm);
  Divider.Parent := InnerCard;
  Divider.Left := ScaleX(746);
  Divider.Top := ScaleY(24);
  Divider.Width := ScaleX(1);
  Divider.Height := ScaleY(388);
  Divider.Color := GuardianBorder;
  Divider.BevelOuter := bvNone;
  Divider.ParentBackground := False;
  Divider.StyleElements := [];

  AddText(InnerCard, 'P2P GUARDIAN', 64, 68, 520, 44, 30, True, GuardianBlue);
  AddText(InnerCard, 'OSRS DISCORD MONITOR', 64, 115, 600, 38, 24, True, GuardianText);
  Line := TPanel.Create(WizardForm);
  Line.Parent := InnerCard;
  Line.Left := ScaleX(64);
  Line.Top := ScaleY(181);
  Line.Width := ScaleX(635);
  Line.Height := ScaleY(1);
  Line.Color := GuardianLine;
  Line.BevelOuter := bvNone;
  Line.ParentBackground := False;
  Line.StyleElements := [];
  AddText(InnerCard, 'Real-time monitoring for your OSRS journey.', 64, 198, 640, 32, 15, False, GuardianMuted);

  UpdateCard := TPanel.Create(WizardForm);
  UpdateCard.Parent := InnerCard;
  UpdateCard.Left := ScaleX(48);
  UpdateCard.Top := ScaleY(248);
  UpdateCard.Width := ScaleX(652);
  UpdateCard.Height := ScaleY(128);
  UpdateCard.Color := GuardianLine;
  UpdateCard.BevelOuter := bvNone;
  UpdateCard.ParentBackground := False;
  UpdateCard.StyleElements := [];
  Cover := TPanel.Create(WizardForm);
  Cover.Parent := UpdateCard;
  Cover.Left := 1; Cover.Top := 1;
  Cover.Width := UpdateCard.Width - 2; Cover.Height := UpdateCard.Height - 2;
  Cover.Color := GuardianCard;
  Cover.BevelOuter := bvNone;
  Cover.ParentBackground := False;
  Cover.StyleElements := [];

  if IsExistingInstall then
  begin
    StatusTitle := 'UPDATE READY';
    StatusLine1 := 'Your existing P2P Guardian installation was detected.';
    StatusLine2 := 'Your Discord token and configuration will be preserved.';
  end
  else
  begin
    StatusTitle := 'NEW INSTALLATION';
    StatusLine1 := 'A Discord bot is required before continuing.';
    StatusLine2 := 'Your private token and IDs are stored locally only.';
  end;

  AddText(Cover, 'i', 20, 29, 36, 40, 22, True, GuardianBlue);
  AddText(Cover, StatusTitle, 92, 17, 500, 30, 17, True, GuardianBlue);
  AddText(Cover, StatusLine1, 92, 50, 520, 24, 11, False, GuardianText);
  AddText(Cover, StatusLine2, 92, 76, 520, 24, 11, False, GuardianMuted);

  RightFrame := TPanel.Create(WizardForm);
  RightFrame.Parent := InnerCard;
  RightFrame.Left := ScaleX(782);
  RightFrame.Top := ScaleY(24);
  RightFrame.Width := ScaleX(294);
  RightFrame.Height := ScaleY(418);
  RightFrame.Color := GuardianBorder;
  RightFrame.BevelOuter := bvNone;
  RightFrame.ParentBackground := False;
  RightFrame.StyleElements := [];
  Cover := TPanel.Create(WizardForm);
  Cover.Parent := RightFrame;
  Cover.Left := 1; Cover.Top := 1;
  Cover.Width := RightFrame.Width - 2; Cover.Height := RightFrame.Height - 2;
  Cover.Color := GuardianCard;
  Cover.BevelOuter := bvNone;
  Cover.ParentBackground := False;
  Cover.StyleElements := [];
  LogoImage := TBitmapImage.Create(WizardForm);
  LogoImage.Parent := Cover;
  LogoImage.Left := ScaleX(41);
  LogoImage.Top := ScaleY(16);
  LogoImage.Width := ScaleX(202);
  LogoImage.Height := ScaleY(202);
  LogoImage.Stretch := True;
  LogoImage.BackColor := GuardianCard;
  LogoImage.PngImage := BrandPng;
  BrandTitle := AddText(Cover, 'P2P GUARDIAN', 18, 230, 256, 30, 17, True, GuardianBlue);
  BrandTitle.Alignment := taCenter;
  BrandSub := AddText(Cover, 'OSRS DISCORD MONITOR', 18, 262, 256, 22, 10, True, GuardianMuted);
  BrandSub.Alignment := taCenter;
  Line := TPanel.Create(WizardForm);
  Line.Parent := Cover;
  Line.Left := ScaleX(52); Line.Top := ScaleY(289);
  Line.Width := ScaleX(190); Line.Height := ScaleY(1);
  Line.Color := GuardianLine;
  Line.BevelOuter := bvNone;
  Line.ParentBackground := False;
  Line.StyleElements := [];
  BrandSlogan := AddText(Cover, 'PLAY SMARTER  •  STAY SAFER', 18, 306, 256, 24, 10, True, GuardianBlue);
  BrandSlogan.Alignment := taCenter;

end;

procedure NormalizePageSurface(Page: TWizardPage);
begin
  { Use the complete client area above the custom Guardian footer.
    This removes the default modern-wizard page inset so every page shares
    one continuous Guardian frame with the landing page. }
  Page.Surface.Left := 0;
  Page.Surface.Top := 0;
  Page.Surface.Width := WizardForm.ClientWidth;
  Page.Surface.Height := WizardForm.ClientHeight;
end;

procedure CreatePageShell(Page: TWizardPage);
var
  Shell, Fill: TPanel;
begin
  NormalizePageSurface(Page);
  Shell := TPanel.Create(WizardForm);
  Shell.Parent := Page.Surface;
  Shell.Left := 0;
  Shell.Top := 0;
  Shell.Width := Page.SurfaceWidth;
  Shell.Height := Page.SurfaceHeight;
  Shell.Color := GuardianLine;
  Shell.BevelOuter := bvNone;
  Shell.ParentBackground := False;
  Shell.StyleElements := [];

  Fill := TPanel.Create(WizardForm);
  Fill.Parent := Shell;
  Fill.Left := 1;
  Fill.Top := 1;
  Fill.Width := Shell.Width - 2;
  Fill.Height := Shell.Height - 2;
  Fill.Color := GuardianBg;
  Fill.BevelOuter := bvNone;
  Fill.ParentBackground := False;
  Fill.StyleElements := [];
end;

procedure AddPageFooter(Parent: TWinControl; Y, W: Integer);
var
  Line: TPanel;
  LogoImage: TBitmapImage;
begin
  Line := TPanel.Create(WizardForm);
  Line.Parent := Parent;
  Line.Left := ScaleX(17);
  Line.Top := ScaleY(Y);
  Line.Width := ScaleX(W - 34);
  Line.Height := ScaleY(1);
  Line.Color := GuardianBorder;
  Line.BevelOuter := bvNone;
  Line.ParentBackground := False;
  Line.StyleElements := [];

  LogoImage := TBitmapImage.Create(WizardForm);
  LogoImage.Parent := Parent;
  LogoImage.Left := ScaleX(18);
  LogoImage.Top := ScaleY(Y + 12);
  LogoImage.Width := ScaleX(24);
  LogoImage.Height := ScaleY(24);
  LogoImage.Stretch := True;
  LogoImage.BackColor := GuardianCard;
  LogoImage.PngImage := BrandPng;

  AddText(Parent, 'P2P Guardian', 52, Y + 11, 125, 26, 10, True, GuardianBlue);
  AddText(Parent, 'OSRS Discord Monitor', 182, Y + 11, 165, 26, 10, False, GuardianMuted);
  AddText(Parent, 'Developed by Bas  |  Razor', 355, Y + 11, 250, 26, 10, False, GuardianMuted);
  AddText(Parent, 'V24.2.5', W - 112, Y + 11, 78, 26, 10, False, GuardianMuted);
end;

procedure AddHeader(Parent: TWinControl; TitleText, SubText: String);
var
  Header: TPanel;
  Line: TPanel;
  LogoImage: TBitmapImage;
begin
  { V99: use a dedicated topmost header layer on the actual page.  In the
    previous revision the logo was a direct child of the page surface while
    the page shell/notebook could still win the z-order during page creation.
    Putting logo + title in one header panel and bringing that panel to front
    makes the shield deterministic on every custom and native wizard page. }
  Header := TPanel.Create(WizardForm);
  Header.Parent := Parent;
  Header.Left := 0;
  Header.Top := 0;
  Header.Width := Parent.ClientWidth;
  Header.Height := ScaleY(68);
  Header.Color := GuardianBg;
  Header.BevelOuter := bvNone;
  Header.ParentBackground := False;
  Header.StyleElements := [];

  LogoImage := TBitmapImage.Create(WizardForm);
  LogoImage.Parent := Header;
  LogoImage.Left := ScaleX(24);
  LogoImage.Top := ScaleY(8);
  LogoImage.Width := ScaleX(48);
  LogoImage.Height := ScaleY(52);
  LogoImage.Stretch := True;
  LogoImage.Center := True;
  LogoImage.BackColor := GuardianBg;
  LogoImage.PngImage := BrandPng;
  LogoImage.Visible := True;

  AddText(Header, 'P2P GUARDIAN', 82, 12, 360, 30, 17, True, GuardianBlue);
  AddText(Header, 'V24.2.5  •  GUARDIAN WINDOWS SETUP', 82, 40, 420, 20, 9, True, GuardianMuted);
  Header.BringToFront;

  AddText(Parent, TitleText, 34, 76, 760, 40, 24, True, GuardianText);
  AddText(Parent, SubText, 34, 114, 860, 28, 10, True, GuardianMuted);
end;

procedure CreateGuardianFooter;
var
  Line: TPanel;
  T: TNewStaticText;
begin
  { Button host: remains visible on every page so the custom buttons work. }
  GuardianFooter := TPanel.Create(WizardForm);
  GuardianFooter.Parent := WizardForm;
  GuardianFooter.Left := 1;
  GuardianFooter.Top := WizardForm.ClientHeight - ScaleY(74) - 1;
  GuardianFooter.Width := WizardForm.ClientWidth - 2;
  GuardianFooter.Height := ScaleY(74);
  GuardianFooter.Color := GuardianBg;
  GuardianFooter.BevelOuter := bvNone;
  GuardianFooter.ParentBackground := False;
  GuardianFooter.StyleElements := [];

  { Footer information is a separate layer so the landing artwork can hide it
    without hiding the NEXT/CANCEL buttons. }
  GuardianFooterInfo := TPanel.Create(WizardForm);
  GuardianFooterInfo.Parent := GuardianFooter;
  GuardianFooterInfo.Left := 0;
  GuardianFooterInfo.Top := 0;
  GuardianFooterInfo.Width := GuardianFooter.Width;
  GuardianFooterInfo.Height := GuardianFooter.Height;
  GuardianFooterInfo.Color := GuardianBg;
  GuardianFooterInfo.BevelOuter := bvNone;
  GuardianFooterInfo.ParentBackground := False;
  GuardianFooterInfo.StyleElements := [];

  Line := TPanel.Create(WizardForm);
  Line.Parent := GuardianFooterInfo;
  Line.Left := ScaleX(24);
  Line.Top := 0;
  Line.Width := GuardianFooterInfo.Width - ScaleX(48);
  Line.Height := ScaleY(1);
  Line.Color := GuardianBorder;
  Line.BevelOuter := bvNone;
  Line.ParentBackground := False;
  Line.StyleElements := [];

  T := AddText(GuardianFooterInfo, 'P2P Guardian', 24, 20, 145, 30, 11, True, GuardianBlue);
  T := AddText(GuardianFooterInfo, 'OSRS Discord Monitor', 184, 20, 185, 30, 11, True, GuardianMuted);
  T := AddText(GuardianFooterInfo, 'Developed by Bas  |  Razor', 388, 20, 260, 30, 11, True, GuardianMuted);
  T := AddText(GuardianFooterInfo, 'V24.2.5', 650, 21, 85, 28, 11, True, GuardianMuted);
end;

procedure SetButtonPanel(P: TPanel; CaptionText: String; X, W: Integer; Primary: Boolean);
var
  Inner: TPanel;
  LabelControl: TNewStaticText;
  ClickProc: TNotifyEvent;
begin
  if CaptionText = 'BACK' then ClickProc := @BackPanelClick
  else if CaptionText = 'NEXT' then ClickProc := @NextPanelClick
  else ClickProc := @CancelPanelClick;

  P.Parent := GuardianFooter;
  P.Left := ScaleX(X);
  P.Top := ScaleY(12);
  P.Width := ScaleX(W);
  P.Height := ScaleY(46);
  P.Color := GuardianLine;
  P.BevelOuter := bvNone;
  P.ParentBackground := False;
  P.StyleElements := [];
  P.OnClick := ClickProc;

  Inner := TPanel.Create(WizardForm);
  Inner.Parent := P;
  Inner.Left := 1;
  Inner.Top := 1;
  Inner.Width := P.Width - 2;
  Inner.Height := P.Height - 2;
  Inner.BevelOuter := bvNone;
  Inner.ParentBackground := False;
  Inner.StyleElements := [];
  Inner.Color := GuardianCard;
  if Primary then Inner.Color := GuardianNext;
  Inner.OnClick := ClickProc;

  LabelControl := TNewStaticText.Create(WizardForm);
  if CaptionText = 'NEXT' then GuardianNextLabel := LabelControl;
  if CaptionText = 'CANCEL' then GuardianCancelLabel := LabelControl;
  LabelControl.Parent := Inner;
  LabelControl.Caption := CaptionText;
  LabelControl.Left := 0;
  LabelControl.Top := ScaleY(11);
  LabelControl.Width := Inner.Width;
  LabelControl.Height := ScaleY(22);
  LabelControl.Alignment := taCenter;
  LabelControl.AutoSize := False;
  LabelControl.StyleElements := [];
  LabelControl.OnClick := ClickProc;
  StyleText(LabelControl, 10, True, GuardianText);
end;

procedure BackPanelClick(Sender: TObject);
begin
  WizardForm.BackButton.OnClick(nil);
end;

procedure NextPanelClick(Sender: TObject);
begin
  WizardForm.NextButton.OnClick(nil);
end;

procedure CancelPanelClick(Sender: TObject);
begin
  { The custom Guardian CANCEL/CLOSE panel must not call the native
    CancelButton.OnClick handler because that handler is deliberately hidden
    and cleared on our custom pages. Calling the nil handler caused the
    "Out of Proc Range" error. Use the same forced exit path directly. }
  ExitProcess(0);
end;

procedure FinishCloseClick(Sender: TObject);
begin
  { Inno Setup deliberately disables its normal close/cancel processing after
    the installation has completed. A normal WizardForm.Close is therefore
    intercepted by Inno on the finish page. Use the documented WinAPI
    ExitProcess workaround so the real native-looking CLOSE button actually
    terminates Setup. }
  ExitProcess(0);
end;

procedure CreateGlobalTopRight;
begin
  { No background panel here. The previous implementation created a visible
    230x68 rectangle that looked like a floating block. These are now plain
    WizardForm-level controls, anchored to the exact same right margin, so
    they remain fixed while Inno swaps notebook pages. }
  GuardianTopRight := TPanel.Create(WizardForm);
  GuardianTopRight.Parent := WizardForm;
  GuardianTopRight.Left := 0;
  GuardianTopRight.Top := 0;
  GuardianTopRight.Width := 1;
  GuardianTopRight.Height := 1;
  GuardianTopRight.Visible := False;

  GuardianTopRightTitle := AddText(WizardForm, 'OSRS DISCORD MONITOR',
    UnscaleX(WizardForm.ClientWidth) - 297, 11, 230, 22, 9, True, GuardianMuted);
  GuardianTopRightTitle.Anchors := [akTop, akRight];

  GuardianTopRightSlogan := AddText(WizardForm, 'PLAY SMARTER  •  STAY SAFER',
    UnscaleX(WizardForm.ClientWidth) - 297, 34, 230, 22, 9, True, GuardianBlue);
  GuardianTopRightSlogan.Anchors := [akTop, akRight];

  GuardianTopRightLine := TPanel.Create(WizardForm);
  GuardianTopRightLine.Parent := WizardForm;
  GuardianTopRightLine.Left := ScaleX(UnscaleX(WizardForm.ClientWidth) - 297);
  GuardianTopRightLine.Top := ScaleY(58);
  GuardianTopRightLine.Width := ScaleX(230);
  GuardianTopRightLine.Height := ScaleY(1);
  GuardianTopRightLine.Anchors := [akTop, akRight];
  GuardianTopRightLine.Color := GuardianLine;
  GuardianTopRightLine.BevelOuter := bvNone;
  GuardianTopRightLine.ParentBackground := False;
  GuardianTopRightLine.StyleElements := [];

  GuardianTopRightTitle.BringToFront;
  GuardianTopRightSlogan.BringToFront;
  GuardianTopRightLine.BringToFront;
end;

procedure CreateGuardianButtons;
var
  W, Gap, RightX: Integer;
begin
  W := 118;
  Gap := 14;
  RightX := UnscaleX(WizardForm.ClientWidth) - 28;

  GuardianBackButton := TPanel.Create(WizardForm);
  GuardianBackButton.OnClick := @BackPanelClick;
  SetButtonPanel(GuardianBackButton, 'BACK', RightX - W*3 - Gap*2, W, False);

  GuardianNextButton := TPanel.Create(WizardForm);
  GuardianNextButton.OnClick := @NextPanelClick;
  SetButtonPanel(GuardianNextButton, 'NEXT', RightX - W*2 - Gap, W, True);

  GuardianCancelButton := TPanel.Create(WizardForm);
  GuardianCancelButton.OnClick := @CancelPanelClick;
  SetButtonPanel(GuardianCancelButton, 'CANCEL', RightX - W, W, False);

  { The footer info panel is a visual layer. Keep the interactive buttons above it. }
  GuardianBackButton.BringToFront;
  GuardianNextButton.BringToFront;
  GuardianCancelButton.BringToFront;
end;

procedure UpdateGuardianButtons(CurPageID: Integer);
var
  InstallTransition: Boolean;
begin
  { Native wpPreparing/wpInstalling are transient installation pages. Do not
    leave the Guardian navigation footer visible during that transition. }
  InstallTransition := (CurPageID = wpPreparing) or (CurPageID = wpInstalling);
  GuardianBackButton.Visible := (CurPageID <> LandingPage.ID) and
    (CurPageID <> FinishedGuardianPage.ID) and (not InstallTransition);
  GuardianNextButton.Visible := (CurPageID <> wpInstalling) and
    (CurPageID <> wpPreparing) and (CurPageID <> FinishedGuardianPage.ID);
  GuardianCancelButton.Visible := (CurPageID <> LandingPage.ID) and
    (CurPageID <> FinishedGuardianPage.ID) and (not InstallTransition);
  if CurPageID = FinishedGuardianPage.ID then
  begin
    { Keep the Guardian-styled custom button on the finish page. It uses the
      same dark card + border styling as CANCEL on all other pages. }
    GuardianCancelLabel.Caption := 'CLOSE';
    GuardianCancelButton.Visible := True;
    GuardianCancelButton.OnClick := @FinishCloseClick;
    GuardianCancelLabel.OnClick := @FinishCloseClick;
    WizardForm.CancelButton.Visible := True;
    WizardForm.CancelButton.Enabled := True;
    WizardForm.CancelButton.OnClick := nil;
  end
  else
  begin
    GuardianCancelLabel.Caption := 'CANCEL';
    GuardianCancelButton.OnClick := @CancelPanelClick;
    GuardianCancelLabel.OnClick := @CancelPanelClick;
    WizardForm.CancelButton.OnClick := nil;
    WizardForm.CancelButton.Visible := True;
    WizardForm.CancelButton.Enabled := True;
  end;
  GuardianBackButton.BringToFront;
  GuardianNextButton.BringToFront;
  if CurPageID <> FinishedGuardianPage.ID then
    GuardianCancelButton.BringToFront;

  if Assigned(GuardianNextLabel) then
  begin
    if CurPageID = ReadyGuardianPage.ID then GuardianNextLabel.Caption := 'INSTALL'
    else GuardianNextLabel.Caption := 'NEXT';
  end;
end;

procedure CreateLandingPage;
var
  TempName: String;
begin
  LandingPage := CreateCustomPage(wpWelcome, '', '');
  LandingPage.Surface.Color := GuardianBg;
  LandingPage.Surface.StyleElements := [];
  CreatePageShell(LandingPage);
  if IsExistingInstall then TempName := 'P2P_Guardian_Wizard_Back_Update_1152.png'
  else TempName := 'P2P_Guardian_Wizard_Back_New_1152.png';
  ExtractTemporaryFile(TempName);
  LandingPng := TPngImage.Create;
  LandingPng.LoadFromFile(ExpandConstant('{tmp}\\' + TempName));
  LandingImage := TBitmapImage.Create(WizardForm);
  LandingImage.Parent := LandingPage.Surface;
  LandingImage.Left := 0;
  LandingImage.Top := 0;
  LandingImage.Width := ScaleX(1152);
  LandingImage.Height := ScaleY(686);
  LandingImage.Anchors := [akLeft, akTop];
  LandingImage.Stretch := False;
  LandingImage.PngImage := LandingPng;
  LandingImage.Visible := False;
  ExtractTemporaryFile('P2P_Guardian_Logo.png');
  if not Assigned(BrandPng) then
  begin
    BrandPng := TPngImage.Create;
    BrandPng.LoadFromFile(ExpandConstant('{tmp}\P2P_Guardian_Logo.png'));
  end;
  CreateLandingOverlay;
end;

procedure CreatePrereqPage;
var
  Card, LeftCard, RightCard, Line: TPanel;
begin
  PrereqPage := CreateCustomPage(LandingPage.ID, '', '');
  PrereqPage.Surface.Color := GuardianBg;
  PrereqPage.Surface.StyleElements := [];
  CreatePageShell(PrereqPage);
  AddHeader(PrereqPage.Surface, 'DISCORD BOT REQUIREMENT', 'P2P Guardian connects to your own Discord bot.');

  Card := AddCard(PrereqPage.Surface, 34, 136, 1084, 420);
  LeftCard := AddFlatSection(Card, 22, 18, 710, 374);
  AddText(LeftCard, 'YOUR DISCORD BOT', 24, 20, 400, 28, 17, True, GuardianBlue);
  AddText(LeftCard, 'P2P Guardian does not create a Discord bot for you.', 24, 56, 620, 24, 10, False, GuardianText);
  AddText(LeftCard, 'You need an existing bot and its private token before continuing.', 24, 82, 620, 24, 9, False, GuardianMuted);

  Line := TPanel.Create(WizardForm);
  Line.Parent := LeftCard; Line.Left := ScaleX(24); Line.Top := ScaleY(116);
  Line.Width := LeftCard.Width - ScaleX(48); Line.Height := ScaleY(1);
  Line.Color := GuardianBorder; Line.BevelOuter := bvNone;
  Line.ParentBackground := False; Line.StyleElements := [];

  AddText(LeftCard, 'REQUIRED', 24, 134, 180, 22, 9, True, GuardianBlue);
  AddText(LeftCard,
    '1. Discord application with a bot' + #13#10 +
    '2. Bot added to your Discord server' + #13#10 +
    '3. Bot token ready to enter during setup' + #13#10 +
    '4. Notification, task, level and user IDs',
    24, 164, 590, 92, 9, False, GuardianMuted);

  ConfirmCheck := TNewCheckBox.Create(WizardForm);
  ConfirmCheck.Parent := LeftCard;
  ConfirmCheck.Caption := 'I already have the required Discord bot and token.';
  ConfirmCheck.Left := ScaleX(24);
  ConfirmCheck.Top := ScaleY(274);
  ConfirmCheck.Width := LeftCard.Width - ScaleX(48);
  ConfirmCheck.Height := ScaleY(22);
  ConfirmCheck.Font.Name := 'Segoe UI';
  ConfirmCheck.Font.Color := GuardianText;
  ConfirmCheck.StyleElements := [seFont];

  HelpButton := TNewButton.Create(WizardForm);
  HelpButton.Parent := LeftCard;
  HelpButton.Caption := 'Discord bot setup help';
  HelpButton.Left := ScaleX(24);
  HelpButton.Top := ScaleY(300);
  HelpButton.Width := ScaleX(240);
  HelpButton.Height := ScaleY(28);
  HelpButton.OnClick := @HelpButtonClick;
  HelpButton.Font.Name := 'Segoe UI';

  RightCard := AddFlatSection(Card, 754, 18, 282, 374);
  AddVerticalDivider(Card, 736, 18, 374);
  AddBrandPanel(RightCard, 0, 0, 282, 374, 'P2P GUARDIAN', 'OSRS DISCORD MONITOR');
end;

procedure CreateConfigPage;
var
  Card, LeftCard, RightCard, Line: TPanel;
begin
  ConfigPage := CreateCustomPage(PrereqPage.ID, '', '');
  ConfigPage.Surface.Color := GuardianBg;
  ConfigPage.Surface.StyleElements := [];
  CreatePageShell(ConfigPage);
  AddHeader(ConfigPage.Surface, 'DISCORD CONFIGURATION', 'Enter the Discord settings used by your P2P Guardian monitor.');

  Card := AddCard(ConfigPage.Surface, 34, 136, 1084, 420);
  LeftCard := AddFlatSection(Card, 22, 18, 710, 374);
  AddText(LeftCard, 'BOT CONNECTION', 24, 20, 360, 28, 17, True, GuardianBlue);
  AddText(LeftCard, 'DISCORD BOT TOKEN', 24, 54, 320, 22, 11, True, GuardianText);
  TokenEdit := TNewEdit.Create(WizardForm); TokenEdit.Parent := LeftCard; TokenEdit.PasswordChar := '*';
  StyleEdit(TokenEdit, 24, 79, 642, 32);

  AddText(LeftCard, 'NOTIFICATION CHANNEL ID', 24, 124, 300, 22, 11, True, GuardianText);
  NotifyEdit := TNewEdit.Create(WizardForm); NotifyEdit.Parent := LeftCard;
  StyleEdit(NotifyEdit, 24, 149, 305, 30);
  AddText(LeftCard, 'TASK NOTIFICATION CHANNEL ID', 360, 124, 305, 22, 11, True, GuardianText);
  TaskEdit := TNewEdit.Create(WizardForm); TaskEdit.Parent := LeftCard;
  StyleEdit(TaskEdit, 360, 149, 305, 30);

  AddText(LeftCard, 'LEVEL-UP CHANNEL ID', 24, 194, 300, 22, 11, True, GuardianText);
  LevelEdit := TNewEdit.Create(WizardForm); LevelEdit.Parent := LeftCard;
  StyleEdit(LevelEdit, 24, 219, 305, 30);
  AddText(LeftCard, 'YOUR DISCORD USER ID (PERSONAL PINGS)', 360, 194, 305, 22, 11, True, GuardianText);
  PingEdit := TNewEdit.Create(WizardForm); PingEdit.Parent := LeftCard;
  StyleEdit(PingEdit, 360, 219, 305, 30);

  Line := TPanel.Create(WizardForm);
  Line.Parent := LeftCard; Line.Left := ScaleX(24); Line.Top := ScaleY(270);
  Line.Width := LeftCard.Width - ScaleX(48); Line.Height := ScaleY(1);
  Line.Color := GuardianBorder; Line.BevelOuter := bvNone;
  Line.ParentBackground := False; Line.StyleElements := [];
  AddText(LeftCard, 'Your token is used locally by the installed monitor.', 24, 286, 610, 22, 8, False, GuardianMuted);

  RightCard := AddFlatSection(Card, 754, 18, 282, 374);
  AddVerticalDivider(Card, 736, 18, 374);
  AddBrandPanel(RightCard, 0, 0, 282, 374, 'P2P GUARDIAN', 'OSRS DISCORD MONITOR');
end;

procedure BrowseDirClick(Sender: TObject);
var
  Dir: String;
begin
  Dir := GuardianDirEdit.Text;
  if BrowseForFolder('Select P2P Guardian installation folder', Dir, True) then
    GuardianDirEdit.Text := Dir;
end;

procedure CreateDirPage;
var
  Card, LeftCard, RightCard, BrowsePanel, Line: TPanel;
  BrowseLabel: TNewStaticText;
begin
  DirPage := CreateCustomPage(ConfigPage.ID, '', '');
  DirPage.Surface.Color := GuardianBg;
  DirPage.Surface.StyleElements := [];
  CreatePageShell(DirPage);
  AddHeader(DirPage.Surface, 'INSTALL LOCATION', 'Choose where P2P Guardian should be installed.');

  Card := AddCard(DirPage.Surface, 34, 136, 1084, 420);
  LeftCard := AddFlatSection(Card, 22, 18, 710, 374);
  AddText(LeftCard, 'INSTALLATION FOLDER', 24, 20, 420, 26, 15, True, GuardianBlue);
  AddText(LeftCard, 'P2P Guardian will be installed in this folder.', 24, 56, 620, 22, 9, False, GuardianMuted);
  AddText(LeftCard, 'P2P Guardian folder', 24, 96, 360, 20, 9, True, GuardianText);
  GuardianDirEdit := TNewEdit.Create(WizardForm);
  GuardianDirEdit.Parent := LeftCard;
  StyleEdit(GuardianDirEdit, 24, 121, 530, 34);
  BrowsePanel := TPanel.Create(WizardForm);
  BrowsePanel.Parent := LeftCard;
  BrowsePanel.Left := ScaleX(566); BrowsePanel.Top := ScaleY(121);
  BrowsePanel.Width := ScaleX(100); BrowsePanel.Height := ScaleY(34);
  BrowsePanel.Color := GuardianBorder; BrowsePanel.BevelOuter := bvNone;
  BrowsePanel.ParentBackground := False; BrowsePanel.StyleElements := [];
  BrowseLabel := TNewStaticText.Create(WizardForm);
  BrowseLabel.Parent := BrowsePanel; BrowseLabel.Caption := 'BROWSE';
  BrowseLabel.Left := 0; BrowseLabel.Top := ScaleY(7); BrowseLabel.Width := BrowsePanel.Width; BrowseLabel.Height := ScaleY(20);
  BrowseLabel.Alignment := taCenter; BrowseLabel.AutoSize := False;
  StyleText(BrowseLabel, 8, True, GuardianText);
  BrowsePanel.OnClick := @BrowseDirClick; BrowseLabel.OnClick := @BrowseDirClick;

  Line := TPanel.Create(WizardForm);
  Line.Parent := LeftCard; Line.Left := ScaleX(24); Line.Top := ScaleY(178);
  Line.Width := LeftCard.Width - ScaleX(48); Line.Height := ScaleY(1);
  Line.Color := GuardianBorder; Line.BevelOuter := bvNone;
  Line.ParentBackground := False; Line.StyleElements := [];
  AddText(LeftCard, 'INSTALL BEHAVIOR', 24, 196, 240, 22, 9, True, GuardianBlue);
  AddText(LeftCard, 'Native Windows controller included', 24, 228, 300, 22, 9, False, GuardianText);
  AddText(LeftCard, 'Windows startup entry included', 24, 254, 300, 22, 9, False, GuardianMuted);
  AddText(LeftCard, 'Existing installations keep their current location.', 24, 282, 620, 22, 8, False, GuardianMuted);

  RightCard := AddFlatSection(Card, 754, 18, 282, 374);
  AddVerticalDivider(Card, 736, 18, 374);
  AddBrandPanel(RightCard, 0, 0, 282, 374, 'P2P GUARDIAN', 'OSRS DISCORD MONITOR');

  GuardianDirEdit.Text := WizardForm.DirEdit.Text;
  if GuardianDirEdit.Text = '' then GuardianDirEdit.Text := ExpandConstant('{localappdata}\P2P Guardian');
end;

function VersionNumber(VersionText: String): Integer;
var
  S, A, B, C: String;
  P1, P2: Integer;
begin
  S := Trim(VersionText);
  if (Length(S) > 0) and ((S[1] = 'v') or (S[1] = 'V')) then
    Delete(S, 1, 1);
  A := S; B := '0'; C := '0';
  P1 := Pos('.', S);
  if P1 > 0 then
  begin
    A := Copy(S, 1, P1 - 1);
    S := Copy(S, P1 + 1, Length(S));
    P2 := Pos('.', S);
    if P2 > 0 then
    begin
      B := Copy(S, 1, P2 - 1);
      C := Copy(S, P2 + 1, Length(S));
    end
    else
      B := S;
  end;
  Result := StrToIntDef(A, 0) * 1000000 + StrToIntDef(B, 0) * 1000 + StrToIntDef(C, 0);
end;

function ReadVersionFromFile(FileName: String): String;
var
  ContentA: AnsiString;
  Content: String;
  Marker, ColonPos, StartPos, EndPos: Integer;
begin
  Result := '';
  if not FileExists(FileName) then Exit;
  if not LoadStringFromFile(FileName, ContentA) then Exit;
  Content := String(ContentA);
  Marker := Pos('"version"', Content);
  if Marker = 0 then Exit;
  ColonPos := Pos(':', Copy(Content, Marker, Length(Content) - Marker + 1));
  if ColonPos = 0 then Exit;
  StartPos := Marker + ColonPos;
  while (StartPos <= Length(Content)) and ((Content[StartPos] = ' ') or (Content[StartPos] = #9) or (Content[StartPos] = '"') or (Content[StartPos] = ':')) do
    Inc(StartPos);
  EndPos := StartPos;
  while (EndPos <= Length(Content)) and (Content[EndPos] <> '"') and (Content[EndPos] <> #13) and (Content[EndPos] <> #10) and (Content[EndPos] <> ',') do
    Inc(EndPos);
  Result := Trim(Copy(Content, StartPos, EndPos - StartPos));
end;

function GetInstalledVersion(): String;
var
  KeyNames: array[0..3] of String;
  I: Integer;
  V: String;
begin
  Result := '';
  KeyNames[0] := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-OSRSMONITOR241}_is1';
  KeyNames[1] := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-9A2E7C6B2410}_is1';
  KeyNames[2] := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-9A2E7C6B2410}_is1';
  KeyNames[3] := 'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-9A2E7C6B2410}_is1';
  for I := 0 to 3 do
  begin
    if RegQueryStringValue(HKCU, KeyNames[I], 'DisplayVersion', V) and (Trim(V) <> '') then begin Result := V; Exit; end;
    if RegQueryStringValue(HKLM, KeyNames[I], 'DisplayVersion', V) and (Trim(V) <> '') then begin Result := V; Exit; end;
  end;
  if Trim(ExistingInstallDir) <> '' then
  begin
    V := ReadVersionFromFile(AddBackslash(ExistingInstallDir) + 'guardian_version.json');
    if Trim(V) <> '' then begin Result := V; Exit; end;
  end;
  V := ReadVersionFromFile(ExpandConstant('{app}\guardian_version.json'));
  if Trim(V) <> '' then begin Result := V; Exit; end;
  V := ReadVersionFromFile(ExpandConstant('{localappdata}\P2P Guardian\guardian_version.json'));
  if Trim(V) <> '' then begin Result := V; Exit; end;
  V := ReadVersionFromFile(ExpandConstant('{localappdata}\Programs\OSRS Discord Monitor\guardian_version.json'));
  if Trim(V) <> '' then Result := V;
end;

procedure PopulateChangeSummary;
var
  InstalledN: Integer;
begin
  if not Assigned(ChangeSummaryMemo) then Exit;
  ChangeSummaryMemo.Clear;
  InstalledN := VersionNumber(InstalledVersion);

  if not IsExistingInstall then
  begin
    ChangeSummaryMemo.Lines.Add('V24.1.0  — First stable release: Discord monitor, installer, Windows startup, slash commands and monitoring.');
    ChangeSummaryMemo.Lines.Add('V24.2.2  — Better update detection, preserved Discord configuration and guided first-time bot setup.');
    ChangeSummaryMemo.Lines.Add('          — Developer Portal instructions, improved Control interface, bot management and monitoring.');
    ChangeSummaryMemo.Lines.Add('V24.2.4  — Automatic release updates, Guardian update confirmation and official GitHub installer download.');
    ChangeSummaryMemo.Lines.Add('          — Automatic installer launch, improved bot startup/management and Discord monitoring notifications.');
    ChangeSummaryMemo.Lines.Add('          — Startup/periodic screenshots, OSRS task monitoring/alerts and level-up notifications.');
    ChangeSummaryMemo.Lines.Add('          — Windows Graphics Capture for minimized/background clients and faster screenshot sessions.');
    ChangeSummaryMemo.Lines.Add('          — Per-account status/PID screenshot selection and adaptive Discord embed text sizing.');
    ChangeSummaryMemo.Lines.Add('          — Python dependencies, including WGC, are installed automatically.');
    ChangeSummaryMemo.Lines.Add('V24.2.5  — Dependency pre-check: already-satisfied Python packages are not reinstalled.');
    ChangeSummaryMemo.Lines.Add('          — WGC dependency remains part of the automatic requirements flow.');
    ChangeSummaryMemo.Lines.Add('          — Public release packaging separates private tracking build configuration from source.');
    Exit;
  end;

  if InstalledN >= VersionNumber('{#MyAppVersion}') then
  begin
    ChangeSummaryMemo.Lines.Add('No version changes detected. This installer matches the installed version.');
    Exit;
  end;

  if Trim(InstalledVersion) = '' then
    ChangeSummaryMemo.Lines.Add('Previous version could not be detected — showing all documented changes included here.')
  else
    ChangeSummaryMemo.Lines.Add('Changes since V' + InstalledVersion + ':');

  if InstalledN < VersionNumber('24.2.2') then
  begin
    ChangeSummaryMemo.Lines.Add('V24.2.2  — Better update detection and preserved Discord configuration.');
    ChangeSummaryMemo.Lines.Add('          — Guided bot setup, Developer Portal instructions and improved Control/bot management.');
    ChangeSummaryMemo.Lines.Add('          — Startup/periodic screenshots, task monitoring/alerts, level-up notifications and Windows startup.');
  end;

  if InstalledN < VersionNumber('24.2.4') then
  begin
    ChangeSummaryMemo.Lines.Add('V24.2.4  — Automatic release updates, Guardian update confirmation and official GitHub installer download.');
    ChangeSummaryMemo.Lines.Add('          — Automatic installer launch, improved bot startup/management and Discord notifications.');
    ChangeSummaryMemo.Lines.Add('          — WGC screenshots for minimized/background clients and faster capture sessions.');
    ChangeSummaryMemo.Lines.Add('          — Per-account status/PID screenshot selection and adaptive Discord embed text sizing.');
    ChangeSummaryMemo.Lines.Add('          — Python dependencies, including WGC, are installed automatically.');
  end;

  if InstalledN < VersionNumber('24.2.5') then
  begin
    ChangeSummaryMemo.Lines.Add('V24.2.5  — Dependency pre-check: already-satisfied Python packages are not reinstalled.');
    ChangeSummaryMemo.Lines.Add('          — WGC dependency remains part of the automatic requirements flow.');
    ChangeSummaryMemo.Lines.Add('          — Public release packaging separates private tracking build configuration from source.');
  end;
end;

procedure CreateReadyPage;
var
  Card, LeftCard, RightCard, RowLine: TPanel;
begin
  ReadyGuardianPage := CreateCustomPage(DirPage.ID, '', '');
  ReadyGuardianPage.Surface.Color := GuardianBg;
  ReadyGuardianPage.Surface.StyleElements := [];
  CreatePageShell(ReadyGuardianPage);
  AddHeader(ReadyGuardianPage.Surface, 'READY TO INSTALL', 'Review the installation before P2P Guardian is installed.');

  Card := AddCard(ReadyGuardianPage.Surface, 34, 136, 1084, 420);
  LeftCard := AddFlatSection(Card, 22, 18, 710, 374);
  AddText(LeftCard, 'INSTALLATION SUMMARY', 24, 20, 450, 28, 16, True, GuardianBlue);

  AddText(LeftCard, 'INSTALL LOCATION', 24, 62, 260, 22, 11, True, GuardianText);
  ReadySummary := AddText(LeftCard, '', 24, 88, 630, 26, 11, True, GuardianText);
  RowLine := TPanel.Create(WizardForm);
  RowLine.Parent := LeftCard; RowLine.Left := ScaleX(24); RowLine.Top := ScaleY(122);
  RowLine.Width := LeftCard.Width - ScaleX(48); RowLine.Height := ScaleY(1);
  RowLine.Color := GuardianBorder; RowLine.BevelOuter := bvNone;
  RowLine.ParentBackground := False; RowLine.StyleElements := [];

  AddText(LeftCard, 'UPDATE STATUS', 24, 140, 240, 22, 11, True, GuardianText);
  if IsExistingInstall then
    AddText(LeftCard, 'UPDATE READY', 24, 166, 280, 26, 14, True, GuardianSuccess)
  else
    AddText(LeftCard, 'NEW INSTALLATION', 24, 166, 280, 26, 14, True, GuardianBlue);
  if IsExistingInstall then
    AddText(LeftCard, 'Existing Discord token and configuration will be preserved.', 24, 194, 620, 24, 10, True, GuardianMuted)
  else
    AddText(LeftCard, 'Discord bot settings will be saved during setup.', 24, 194, 620, 24, 10, True, GuardianMuted);

  if IsExistingInstall then
    AddText(LeftCard, 'WHAT WILL BE UPDATED', 24, 234, 320, 22, 11, True, GuardianBlue)
  else
    AddText(LeftCard, 'WHAT''S INCLUDED', 24, 234, 320, 22, 11, True, GuardianBlue);

  ChangeSummaryMemo := TNewMemo.Create(WizardForm);
  ChangeSummaryMemo.Parent := LeftCard;
  ChangeSummaryMemo.Left := ScaleX(24);
  ChangeSummaryMemo.Top := ScaleY(260);
  ChangeSummaryMemo.Width := ScaleX(680);
  ChangeSummaryMemo.Height := ScaleY(132);
  ChangeSummaryMemo.Font.Name := 'Segoe UI';
  ChangeSummaryMemo.Font.Size := 8;
  ChangeSummaryMemo.Font.Color := GuardianText;
  ChangeSummaryMemo.Color := GuardianCard;
  ChangeSummaryMemo.BorderStyle := bsNone;
  ChangeSummaryMemo.ReadOnly := True;
  ChangeSummaryMemo.ScrollBars := ssVertical;
  ChangeSummaryMemo.WordWrap := True;
  ChangeSummaryMemo.TabStop := False;
  ChangeSummaryMemo.StyleElements := [];
  PopulateChangeSummary;
  if ChangeSummaryMemo.Lines.Count > 8 then
    ChangeSummaryMemo.Font.Size := 7
  else
    ChangeSummaryMemo.Font.Size := 8;

  if IsExistingInstall then
    AddText(LeftCard, 'Existing Discord token and configuration remain preserved.', 24, 392, 680, 22, 9, False, GuardianMuted)
  else
    AddText(LeftCard, 'Click INSTALL to continue with the new installation.', 24, 392, 680, 22, 9, False, GuardianMuted);

  RightCard := AddFlatSection(Card, 754, 18, 282, 374);
  AddVerticalDivider(Card, 736, 18, 374);
  AddBrandPanel(RightCard, 0, 0, 282, 374, 'P2P GUARDIAN', 'OSRS DISCORD MONITOR');
end;

procedure CreateInstallSurface;
var
  Card, ProgressBorder: TPanel;
begin
  { V102: PreparingPage and InstallingPage exposed by TWizardForm are
    TNewNotebookPage controls, not TWizardPage objects. Their page surface
    is the page itself, so configure and paint them directly. }
  WizardForm.InstallingPage.Color := GuardianBg;
  WizardForm.InstallingPage.StyleElements := [];
  WizardForm.PreparingPage.Color := GuardianBg;
  WizardForm.PreparingPage.StyleElements := [];

  { Hide the standard Inno installation controls before either native
    transition page can be displayed. This keeps the transition visually
    consistent even though Inno owns wpPreparing/wpInstalling. }
  WizardForm.PreparingLabel.Visible := False;
  WizardForm.FilenameLabel.Visible := False;
  WizardForm.StatusLabel.Visible := False;
  WizardForm.ProgressGauge.Visible := False;
  WizardForm.InfoAfterMemo.Visible := False;
  WizardForm.FinishedHeadingLabel.Visible := False;
  WizardForm.FinishedLabel.Visible := False;
  WizardForm.RunList.Visible := False;

  { V103: wpPreparing is an internal Inno Setup transition and cannot be skipped
    through ShouldSkipPage. Keep it visually blank so users do not see a second
    Guardian page flash before the real installing page. }
  WizardForm.PreparingPage.Color := GuardianBg;
  WizardForm.InstallingPage.Color := GuardianBg;
  AddHeader(WizardForm.InstallingPage, 'INSTALLING P2P GUARDIAN', 'Please wait while the Guardian components are installed.');

  Card := AddCard(WizardForm.InstallingPage, 34, 156,
    UnscaleX(WizardForm.InstallingPage.Width) - 68, 300);
  AddText(Card, 'INSTALLATION PROGRESS', 28, 24, 420, 26, 13, True, GuardianBlue);
  InstallStatus := AddText(Card, 'INSTALLING P2P GUARDIAN...', 28, 70, 700, 30, 15, True, GuardianText);
  InstallPercent := AddText(Card, '0%', 28, 112, 700, 24, 10, False, GuardianMuted);

  ProgressBorder := TPanel.Create(WizardForm);
  ProgressBorder.Parent := Card;
  ProgressBorder.Left := ScaleX(28); ProgressBorder.Top := ScaleY(154);
  ProgressBorder.Width := Card.Width - ScaleX(56); ProgressBorder.Height := ScaleY(18);
  ProgressBorder.Color := GuardianBorder; ProgressBorder.BevelOuter := bvNone;
  ProgressBorder.ParentBackground := False; ProgressBorder.StyleElements := [];
  InstallProgressBack := TPanel.Create(WizardForm);
  InstallProgressBack.Parent := ProgressBorder;
  InstallProgressBack.Left := ScaleX(1); InstallProgressBack.Top := ScaleY(1);
  InstallProgressBack.Width := ProgressBorder.Width - ScaleX(2); InstallProgressBack.Height := ProgressBorder.Height - ScaleY(2);
  InstallProgressBack.Color := GuardianInner; InstallProgressBack.BevelOuter := bvNone;
  InstallProgressBack.ParentBackground := False; InstallProgressBack.StyleElements := [];
  InstallProgressFill := TPanel.Create(WizardForm);
  InstallProgressFill.Parent := InstallProgressBack;
  InstallProgressFill.Left := 0; InstallProgressFill.Top := 0; InstallProgressFill.Width := 0; InstallProgressFill.Height := InstallProgressBack.Height;
  InstallProgressFill.Color := GuardianNext; InstallProgressFill.BevelOuter := bvNone;
  InstallProgressFill.ParentBackground := False; InstallProgressFill.StyleElements := [];
  AddText(Card, 'P2P Guardian  •  Native Windows controller  •  Discord monitor', 28, 204, 820, 22, 8, False, GuardianMuted);
end;

procedure CreateFinishedPage;
var
  Card, LeftCard, RightCard, Line: TPanel;
begin
  FinishedGuardianPage := CreateCustomPage(wpInstalling, '', '');
  FinishedGuardianPage.Surface.Color := GuardianBg;
  FinishedGuardianPage.Surface.StyleElements := [];
  CreatePageShell(FinishedGuardianPage);
  AddHeader(FinishedGuardianPage.Surface, 'INSTALLATION COMPLETE', 'P2P Guardian is ready to use.');
  Card := AddCard(FinishedGuardianPage.Surface, 34, 136, 1084, 420);
  LeftCard := AddFlatSection(Card, 22, 18, 710, 374);
  AddText(LeftCard, 'P2P GUARDIAN IS READY', 24, 24, 600, 30, 17, True, GuardianSuccess);
  AddText(LeftCard, 'The controller and Discord monitor have been installed.', 24, 68, 620, 24, 10, False, GuardianText);
  AddText(LeftCard, 'Launch P2P Guardian Control from the Desktop or Start Menu.', 24, 96, 620, 24, 9, False, GuardianMuted);
  Line := TPanel.Create(WizardForm);
  Line.Parent := LeftCard; Line.Left := ScaleX(24); Line.Top := ScaleY(136);
  Line.Width := LeftCard.Width - ScaleX(48); Line.Height := ScaleY(1);
  Line.Color := GuardianBorder; Line.BevelOuter := bvNone;
  Line.ParentBackground := False; Line.StyleElements := [];
  AddText(LeftCard, 'INSTALLED COMPONENTS', 24, 154, 280, 22, 9, True, GuardianBlue);
  AddText(LeftCard, 'Native Windows controller', 24, 188, 300, 22, 9, False, GuardianMuted);
  AddText(LeftCard, 'OSRS Discord monitor', 24, 216, 300, 22, 9, False, GuardianMuted);
  AddText(LeftCard, 'Desktop and Start Menu shortcuts', 24, 244, 400, 22, 9, False, GuardianMuted);

  RightCard := AddFlatSection(Card, 754, 18, 282, 374);
  AddVerticalDivider(Card, 736, 18, 374);
  AddBrandPanel(RightCard, 0, 0, 282, 374, 'P2P GUARDIAN', 'OSRS DISCORD MONITOR');
end;

function GetExistingInstallDir(): String;
var
  KeyNames: array[0..3] of String;
  I: Integer;
  InstallDir: String;
begin
  Result := '';
  KeyNames[0] := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-OSRSMONITOR241}_is1';
  KeyNames[1] := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-9A2E7C6B2410}_is1';
  KeyNames[2] := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-9A2E7C6B2410}_is1';
  KeyNames[3] := 'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{E1B2F1D0-5A7A-4C7D-A4F1-9A2E7C6B2410}_is1';
  for I := 0 to 3 do
  begin
    if RegQueryStringValue(HKCU, KeyNames[I], 'InstallLocation', InstallDir) and
       (Trim(InstallDir) <> '') and DirExists(InstallDir) then
    begin
      Result := RemoveBackslashUnlessRoot(InstallDir);
      Exit;
    end;
    if RegQueryStringValue(HKLM, KeyNames[I], 'InstallLocation', InstallDir) and
       (Trim(InstallDir) <> '') and DirExists(InstallDir) then
    begin
      Result := RemoveBackslashUnlessRoot(InstallDir);
      Exit;
    end;
  end;

  { Legacy/current locations are checked explicitly so a valid installation
    is still recognized even if its uninstall registry entry is missing. }
  InstallDir := ExpandConstant('{localappdata}\P2P Guardian');
  if FileExists(AddBackslash(InstallDir) + 'guardian_version.json') then
  begin
    Result := InstallDir;
    Exit;
  end;
  InstallDir := ExpandConstant('{localappdata}\Programs\OSRS Discord Monitor');
  if FileExists(AddBackslash(InstallDir) + 'guardian_version.json') then
    Result := InstallDir;
end;

function IsExistingInstallation(): Boolean;
begin
  ExistingInstallDir := GetExistingInstallDir();
  Result := Trim(ExistingInstallDir) <> '';
end;

procedure HelpButtonClick(Sender: TObject);
begin
  MsgBox('P2P Guardian requires your own Discord bot.' + #13#10 + #13#10 +
    '1. Create an application in the Discord Developer Portal.' + #13#10 +
    '2. Open Bot and create the bot.' + #13#10 +
    '3. Copy the Bot Token and keep it private.' + #13#10 +
    '4. Open OAuth2 > URL Generator.' + #13#10 +
    '5. Select bot and applications.commands.' + #13#10 +
    '6. Grant View Channels, Send Messages, Embed Links, and Attach Files.' + #13#10 +
    '7. Use the generated URL to add the bot to your server.' + #13#10 +
    '8. Return here and enter your token and Discord IDs.' + #13#10 + #13#10 +
    'Administrator permission is not required.' + #13#10 + 'Never share your bot token.', mbInformation, MB_OK);
  ShellExec('open', 'https://discord.com/developers/applications', '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
end;


procedure WizardCloseQuery(Sender: TObject; var CanClose: Boolean);
begin
  { Allow the real Windows X button on every wizard page. The previous
    version only allowed closing on the finish page, which made the title-bar
    X appear dead. Cancel/close confirmation remains handled by Inno itself. }
  CanClose := True;
end;

procedure InitializeWizard;
begin
  IsExistingInstall := IsExistingInstallation();
  InstalledVersion := GetInstalledVersion();
  if IsExistingInstall and (Trim(ExistingInstallDir) <> '') then
    WizardForm.DirEdit.Text := ExistingInstallDir;
  WizardForm.Caption := 'Setup - P2P Guardian V24.2.5';
  WizardForm.Color := GuardianBg;
  WizardForm.MainPanel.Color := GuardianBg;
  WizardForm.MainPanel.StyleElements := [];
  WizardForm.MainPanel.Visible := False;
  WizardForm.PageNameLabel.Visible := False;
  WizardForm.PageDescriptionLabel.Visible := False;
  WizardForm.WelcomeLabel1.Visible := False;
  WizardForm.WelcomeLabel2.Visible := False;
  WizardForm.BackButton.Visible := False;
  WizardForm.NextButton.Visible := False;
  { Keep the native CancelButton alive as the hidden close/cancel anchor.
    Inno uses this control to determine whether the title-bar X is enabled.
    Hiding it makes the X appear dead on custom wizard pages. Keep it enabled
    and move it outside the visible wizard canvas; CancelButtonClick and
    OnCloseQuery still handle the actual close action. }
  WizardForm.CancelButton.Visible := True;
  WizardForm.CancelButton.Enabled := True;
  WizardForm.CancelButton.Left := -ScaleX(100);
  WizardForm.CancelButton.Top := -ScaleY(100);
  WizardForm.CancelButton.Width := ScaleX(1);
  WizardForm.CancelButton.Height := ScaleY(1);
  WizardForm.OnCloseQuery := @WizardCloseQuery;
  { WizardForm.ButtonsPanel is not exposed by Inno Setup Pascal Script; custom Guardian buttons are used instead. }

  SizeWizardToScreen;
  ExpandWizardCanvas;
  CreateLandingPage;
  CreatePrereqPage;
  CreateConfigPage;
  CreateDirPage;
  CreateReadyPage;
  CreateFinishedPage;
  CreateInstallSurface;
  ExpandWizardCanvas;
  NormalizePageSurface(LandingPage);
  NormalizePageSurface(PrereqPage);
  NormalizePageSurface(ConfigPage);
  NormalizePageSurface(DirPage);
  NormalizePageSurface(ReadyGuardianPage);
  NormalizePageSurface(FinishedGuardianPage);
  CreateGuardianFooter;
  CreateGuardianButtons;
  CreateGlobalTopRight;

end;

procedure CurPageChanged(CurPageID: Integer);
begin
  FinishedPageActive := Assigned(FinishedGuardianPage) and (CurPageID = FinishedGuardianPage.ID);
  if Assigned(LandingImage) then LandingImage.Visible := CurPageID = LandingPage.ID;
  if Assigned(LandingOverlay) then LandingOverlay.Visible := CurPageID = LandingPage.ID;
  if Assigned(GuardianFooterInfo) then
    GuardianFooterInfo.Visible := not ((CurPageID = wpPreparing) or (CurPageID = wpInstalling));
  if Assigned(GuardianFooter) then
    GuardianFooter.Visible := not ((CurPageID = wpPreparing) or (CurPageID = wpInstalling));
  if CurPageID = ReadyGuardianPage.ID then
  begin
    ReadySummary.Caption := GuardianDirEdit.Text;
    PopulateChangeSummary;
  end;
  UpdateGuardianButtons(CurPageID);
  if CurPageID = FinishedGuardianPage.ID then
  begin
    { Keep the native Inno Cancel button hidden. The Guardian custom CLOSE
      button is the visible finish control and uses FinishCloseClick. }
    WizardForm.CancelButton.Visible := True;
    WizardForm.CancelButton.Enabled := True;
    WizardForm.CancelButton.OnClick := nil;
    GuardianCancelButton.Visible := True;
    GuardianCancelButton.OnClick := @FinishCloseClick;
    GuardianCancelLabel.OnClick := @FinishCloseClick;
    GuardianCancelButton.BringToFront;
  end;
  if Assigned(GuardianTopRightTitle) then GuardianTopRightTitle.BringToFront;
  if Assigned(GuardianTopRightSlogan) then GuardianTopRightSlogan.BringToFront;
  if Assigned(GuardianTopRightLine) then GuardianTopRightLine.BringToFront;
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
var
  Pct: Integer;
begin
  if (MaxProgress > 0) and Assigned(InstallProgressFill) then
  begin
    Pct := (CurProgress * 100) div MaxProgress;
    if Pct < 0 then Pct := 0;
    if Pct > 100 then Pct := 100;
    InstallProgressFill.Width := (InstallProgressBack.Width * Pct) div 100;
    InstallPercent.Caption := IntToStr(Pct) + '%';
  end;
end;

{ V62: Guardian visual system applied consistently across all wizard pages. }
procedure DeinitializeSetup;
begin
  if Assigned(LandingPng) then LandingPng.Free;
  if Assigned(BrandPng) then BrandPng.Free;
end;

function FindPythonExecutable: String;
var
  Candidate: String;
begin
  Result := '';
  Candidate := ExpandConstant('{sys}\python.exe');
  if FileExists(Candidate) then begin Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{sys}\python3.exe');
  if FileExists(Candidate) then begin Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{userappdata}\Programs\Python\Python312\python.exe');
  if FileExists(Candidate) then begin Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{userappdata}\Programs\Python\Python311\python.exe');
  if FileExists(Candidate) then begin Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{userappdata}\Programs\Python\Python310\python.exe');
  if FileExists(Candidate) then begin Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{localappdata}\Programs\Python\Python312\python.exe');
  if FileExists(Candidate) then begin Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{localappdata}\Programs\Python\Python311\python.exe');
  if FileExists(Candidate) then begin Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{localappdata}\Programs\Python\Python310\python.exe');
  if FileExists(Candidate) then begin Result := Candidate; Exit; end;
  { Fall back to PATH; the existing P2P Guardian startup shortcut also expects
    pythonw.exe to be available through the user's normal Python installation. }
  Result := 'python.exe';
end;

function CheckPythonDependencies: Boolean;
var
  ExitCode: Integer;
  Params: String;
  RequirementsFile: String;
  CheckerFile: String;
begin
  Result := False;
  RequirementsFile := ExpandConstant('{app}\requirements.txt');
  CheckerFile := ExpandConstant('{app}\dependency_check.py');
  if not FileExists(RequirementsFile) then Exit;
  if not FileExists(CheckerFile) then Exit;
  PythonExecutable := FindPythonExecutable;
  InstallStatus.Caption := 'CHECKING PYTHON DEPENDENCIES...';
  InstallPercent.Caption := 'Checking installed packages and required versions';
  WizardForm.Update;
  Params := '"' + CheckerFile + '" "' + RequirementsFile + '"';
  if not Exec(PythonExecutable, Params, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ExitCode) then Exit;
  Result := ExitCode = 0;
end;

function InstallPythonDependencies: Boolean;
var
  ExitCode: Integer;
  Params: String;
  RequirementsFile: String;
begin
  Result := False;
  RequirementsFile := ExpandConstant('{app}\requirements.txt');
  if not FileExists(RequirementsFile) then Exit;
  PythonExecutable := FindPythonExecutable;
  InstallStatus.Caption := 'INSTALLING PYTHON DEPENDENCIES...';
  InstallPercent.Caption := 'Installing missing or incompatible packages';
  WizardForm.Update;
  Params := '-m pip install --disable-pip-version-check --no-input -r "' + RequirementsFile + '"';
  if not Exec(PythonExecutable, Params, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ExitCode) then
  begin
    MsgBox('P2P Guardian could not start Python to install its required Python packages.' + #13#10 + #13#10 +
      'Please make sure Python 3 is installed and available as python.exe, then run the installer again.', mbError, MB_OK);
    Exit;
  end;
  if ExitCode <> 0 then
  begin
    MsgBox('P2P Guardian could not install all required Python packages.' + #13#10 + #13#10 +
      'The installation cannot continue because the WGC screenshot component requires its Python dependency.' + #13#10 + #13#10 +
      'Please check your internet connection and Python/pip installation, then run the installer again.', mbError, MB_OK);
    Exit;
  end;
  Result := True;
end;

function EnsurePythonDependencies: Boolean;
begin
  if CheckPythonDependencies then
  begin
    InstallStatus.Caption := 'PYTHON DEPENDENCIES READY';
    InstallPercent.Caption := 'All required packages are already installed';
    WizardForm.Update;
    Result := True;
    Exit;
  end;
  Result := InstallPythonDependencies;
  if Result then Result := CheckPythonDependencies;
  if Result then
  begin
    InstallStatus.Caption := 'PYTHON DEPENDENCIES READY';
    InstallPercent.Caption := 'Required packages are installed and verified';
    WizardForm.Update;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var StopCode: Integer;
begin
  Result := '';
  NeedsRestart := False;
  Exec(ExpandConstant('{sys}\\taskkill.exe'), '/F /IM P2P_Guardian_Control.exe', '', SW_HIDE, ewWaitUntilTerminated, StopCode);
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
    if Trim(TokenEdit.Text) = '' then
    begin
      MsgBox('Please enter your Discord bot token.', mbInformation, MB_OK);
      Result := False;
    end
    else if (Trim(NotifyEdit.Text) = '') or (Trim(TaskEdit.Text) = '') or
            (Trim(LevelEdit.Text) = '') or (Trim(PingEdit.Text) = '') then
    begin
      MsgBox('Please enter all Discord channel IDs and your Discord user ID.', mbInformation, MB_OK);
      Result := False;
    end;
  end
  else if CurPageID = DirPage.ID then
  begin
    if Trim(GuardianDirEdit.Text) = '' then
    begin
      MsgBox('Please choose an installation folder.', mbInformation, MB_OK);
      Result := False;
    end
    else
      WizardForm.DirEdit.Text := GuardianDirEdit.Text;
  end;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  { The title-bar X arrives here through Inno's normal close processing.
    Keep the transient install pages under Inno's own cancel handling, but
    force-close all user-facing wizard pages without invoking a hidden/nil
    native button handler. }
  if (CurPageID = wpPreparing) or (CurPageID = wpInstalling) then
  begin
    Cancel := True;
    Confirm := True;
  end
  else if Assigned(FinishedGuardianPage) and (CurPageID = FinishedGuardianPage.ID) then
  begin
    Cancel := False;
    Confirm := False;
    ExitProcess(0);
  end
  else
  begin
    Cancel := False;
    Confirm := False;
    ExitProcess(0);
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if IsExistingInstall then
  begin
    if (PageID = PrereqPage.ID) or (PageID = ConfigPage.ID) or (PageID = DirPage.ID) or
       (PageID = wpSelectDir) or (PageID = wpSelectProgramGroup) or (PageID = wpReady) then
      Result := True;
  end
  else
  begin
    if (PageID = wpSelectDir) or (PageID = wpSelectProgramGroup) or (PageID = wpReady) then
      Result := True;
  end;
  if PageID = wpFinished then Result := True;
  { Inno Setup does not call ShouldSkipPage for wpPreparing/wpInstalling.
    Those native transition pages are therefore styled directly above. }
end;

function GetInstallTrackingKey: String;
begin
  Result := 'Software\P2P Guardian\InstallTracking';
end;

function GetOrCreateInstallTrackingId: String;
var
  ExistingId: String;
begin
  if RegQueryStringValue(HKCU, GetInstallTrackingKey, 'InstallId', ExistingId) and
     (Trim(ExistingId) <> '') then
  begin
    Result := ExistingId;
    Exit;
  end;

  Result := GetDateTimeString('yyyymmddhhnnsszzz', '-', ':') + '-' +
    IntToStr(Random(1000000000));
end;

function SendInstallTrackingNotification: Boolean;
var
  DataFile, ScriptFile: String;
  Payload: String;
  Script: String;
  ExitCode: Integer;
begin
  Result := False;
  { Tracking is first-install only. Existing installs are never assigned a new
    Install ID during an update, so an older user cannot be reported as a new install. }
  if IsExistingInstall then Exit;
  if Trim('{#GUARDIAN_INSTALL_ENDPOINT}') = '' then Exit;
  if Trim('{#GUARDIAN_INSTALL_CLIENT_KEY}') = '' then Exit;

  InstallTrackingId := GetOrCreateInstallTrackingId;
  RegWriteStringValue(HKCU, GetInstallTrackingKey, 'InstallId', InstallTrackingId);

  Payload := '{' + #13#10 +
    '  "event": "first_install",' + #13#10 +
    '  "product": "P2P Guardian",' + #13#10 +
    '  "version": "{#MyAppVersionDisplay}",' + #13#10 +
    '  "install_id": "' + InstallTrackingId + '",' + #13#10 +
    '  "installed_at": "' + GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + '"' + #13#10 +
    '}';

  DataFile := ExpandConstant('{tmp}\p2p_guardian_install.json');
  ScriptFile := ExpandConstant('{tmp}\p2p_guardian_install.ps1');
  SaveStringToFile(DataFile, Payload, False);

  Script :=
    '$ErrorActionPreference = ''Stop''' + #13#10 +
    '$payload = Get-Content -Raw -Encoding UTF8 ''' + DataFile + '''' + #13#10 +
    '$headers = @{ ''X-Guardian-Install-Key'' = ''{#GUARDIAN_INSTALL_CLIENT_KEY}'' }' + #13#10 +
    'try {' + #13#10 +
    '  Invoke-RestMethod -Uri ''{#GUARDIAN_INSTALL_ENDPOINT}'' -Method Post -Headers $headers -ContentType ''application/json'' -Body $payload -TimeoutSec 15 | Out-Null' + #13#10 +
    '  exit 0' + #13#10 +
    '} catch {' + #13#10 +
    '  exit 1' + #13#10 +
    '}';
  SaveStringToFile(ScriptFile, Script, False);

  if Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ScriptFile + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ExitCode) and (ExitCode = 0) then
  begin
    Result := True;
  end;

  DeleteFile(DataFile);
  DeleteFile(ScriptFile);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  TokenText: String;
  ConfigText: String;
begin
  if CurStep = ssPostInstall then
  begin
    if not IsExistingInstall then
    begin
      TokenText := TokenEdit.Text;
      ConfigText := '{' + #13#10 +
        '  \"notify_channel_id\": ' + NotifyEdit.Text + ',' + #13#10 +
        '  \"task_notify_channel_id\": ' + TaskEdit.Text + ',' + #13#10 +
        '  \"level_notify_channel_id\": ' + LevelEdit.Text + ',' + #13#10 +
        '  \"ping_user_id\": ' + PingEdit.Text + #13#10 +
        '}';
      SaveStringToFile(ExpandConstant('{app}\\discord_token.txt'), TokenText + #13#10, False);
      SaveStringToFile(ExpandConstant('{app}\\osrs_bot_config.json'), ConfigText + #13#10, False);
    end;

    { Install all Python packages declared by the payload, including the WGC
      capture backend. This runs for both fresh installs and updates so an
      existing installation receives the new dependency automatically. }
    if not EnsurePythonDependencies then
      Abort;

    { First-install tracking only. Existing installations are skipped. }
    SendInstallTrackingNotification;
  end;
end;
