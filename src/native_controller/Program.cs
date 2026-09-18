using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Management;
using System.Net.Http;
using System.Text.Json;

namespace P2PGuardian.Control;

internal static class Program
{
    [STAThread]
    static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new GuardianForm());
    }
}

internal sealed class GuardianForm : Form
{
    private readonly string appDir = FindAppDirectory();
    private readonly string botPath;
    private Label statusValue = null!;
    private Label statusDot = null!;
    private Label statusHint = null!;
    private System.Windows.Forms.Timer timer = null!;

    private const string CurrentVersion = "24.2.4";
    private const string ReleasesApi = "https://api.github.com/repos/p2pguardian/P2P-Guardian/releases/latest";
    private const string SetupAssetName = "P2P_Guardian_Setup.exe";

    private static readonly Color Background = Color.FromArgb(3, 19, 31);
    private static readonly Color Card = Color.FromArgb(6, 26, 41);
    private static readonly Color CardBorder = Color.FromArgb(23, 56, 79);
    private static readonly Color White = Color.FromArgb(242, 246, 250);
    private static readonly Color Muted = Color.FromArgb(184, 201, 216);
    private static readonly Color Accent = Color.FromArgb(0, 143, 217);
    private static readonly Color AccentBright = Color.FromArgb(0, 174, 239);
    private static readonly Color Success = Color.FromArgb(77, 219, 131);
    private static readonly Color Danger = Color.FromArgb(255, 87, 108);

    private static string FindAppDirectory()
    {
        string baseDir = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        string[] candidates =
        {
            baseDir,
            Path.Combine(baseDir, "payload"),
            Path.GetFullPath(Path.Combine(baseDir, "..", "..", "..", "payload")),
            Path.GetFullPath(Path.Combine(baseDir, "..", "..", "..", "..", "payload")),
            Path.GetFullPath(Path.Combine(baseDir, "..", "..", "..", "..", "..", "payload"))
        };
        foreach (string candidate in candidates)
            if (File.Exists(Path.Combine(candidate, "osrs_discord_bot.py")))
                return candidate;
        return baseDir;
    }

    public GuardianForm()
    {
        botPath = Path.Combine(appDir, "osrs_discord_bot.py");

        Text = "P2P Guardian Control";
        ClientSize = new Size(900, 620);
        MinimumSize = new Size(900, 620);
        MaximumSize = new Size(900, 620);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        BackColor = Background;
        ForeColor = White;
        Font = new Font("Segoe UI", 9.5F);
        AutoScaleMode = AutoScaleMode.Dpi;
        DoubleBuffered = true;

        // Use the icon embedded in the EXE itself. This keeps the Guardian icon
        // in the title bar and Windows taskbar after installation, without relying
        // on an external .ico file being present beside the EXE.
        try
        {
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath) ?? SystemIcons.Application;
            ShowIcon = true;
        }
        catch
        {
            Icon = SystemIcons.Application;
            ShowIcon = true;
        }

        BuildUi();
        UpdateStatus();
        Shown += async (_, _) => await CheckForUpdateAsync();

        timer = new System.Windows.Forms.Timer { Interval = 1500 };
        timer.Tick += (_, _) => UpdateStatus();
        timer.Start();
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        timer?.Stop();
        timer?.Dispose();
        base.OnFormClosed(e);
    }

    private Label MakeLabel(string text, float size, FontStyle style, Color color)
    {
        return new Label
        {
            Text = text,
            Font = new Font("Segoe UI", size, style),
            ForeColor = color,
            BackColor = Color.Transparent,
            AutoSize = true,
            Margin = Padding.Empty
        };
    }

    private void BuildUi()
    {
        // Header: match the Guardian installer branding — large shield, clean title,
        // monitor subtitle and one-line slogan.
        string logoPath = Path.Combine(appDir, "P2P_Guardian_Logo.png");

        var headerLogo = new PictureBox
        {
            Location = new Point(28, 18),
            Size = new Size(92, 92),
            SizeMode = PictureBoxSizeMode.Zoom,
            BackColor = Color.Transparent
        };
        if (File.Exists(logoPath)) headerLogo.Image = Image.FromFile(logoPath);
        Controls.Add(headerLogo);

        var title = MakeLabel("P2P GUARDIAN", 25F, FontStyle.Bold, White);
        title.Location = new Point(132, 24);
        Controls.Add(title);

        var subtitle = MakeLabel("OSRS DISCORD MONITOR", 11F, FontStyle.Bold, AccentBright);
        subtitle.Location = new Point(134, 66);
        Controls.Add(subtitle);

        var sloganLine = new Panel
        {
            Location = new Point(500, 43),
            Size = new Size(245, 1),
            BackColor = AccentBright
        };
        Controls.Add(sloganLine);

        var slogan = MakeLabel("PLAY SMARTER  •  STAY SAFER", 10F, FontStyle.Bold, AccentBright);
        slogan.Location = new Point(500, 52);
        slogan.AutoSize = false;
        slogan.TextAlign = ContentAlignment.MiddleCenter;
        slogan.Size = new Size(245, 28);
        Controls.Add(slogan);

        var card = new GuardianCard
        {
            Location = new Point(24, 126),
            Size = new Size(852, 380),
            BackColor = Card,
            BorderColor = CardBorder,
            AccentColor = Accent
        };
        Controls.Add(card);

        // Left status/control area.
        var section = MakeLabel("BOT STATUS", 10F, FontStyle.Bold, AccentBright);
        section.Location = new Point(34, 28);
        card.Controls.Add(section);

        statusDot = new Label
        {
            Location = new Point(34, 75),
            Size = new Size(14, 14),
            BackColor = Danger
        };
        card.Controls.Add(statusDot);

        statusValue = MakeLabel("BOT IS STOPPED", 21F, FontStyle.Bold, White);
        statusValue.Location = new Point(64, 67);
        card.Controls.Add(statusValue);

        var detail = MakeLabel("P2P Guardian  •  OSRS Discord Monitor  •  V24.2.4", 10F, FontStyle.Regular, Muted);
        detail.Location = new Point(64, 105);
        card.Controls.Add(detail);

        var divider = new Panel
        {
            Location = new Point(34, 138),
            Size = new Size(470, 1),
            BackColor = CardBorder
        };
        card.Controls.Add(divider);

        statusHint = MakeLabel("Start or stop monitoring from the controls below.", 9.5F, FontStyle.Regular, Muted);
        statusHint.Location = new Point(34, 164);
        card.Controls.Add(statusHint);

        var start = CreateButton("START BOT", Accent, White);
        start.Location = new Point(34, 225);
        start.Size = new Size(210, 50);
        start.Click += (_, _) => StartBot();
        card.Controls.Add(start);

        var stop = CreateButton("STOP BOT", Color.FromArgb(8, 31, 48), White);
        stop.Location = new Point(258, 225);
        stop.Size = new Size(210, 50);
        stop.Click += (_, _) => StopBot();
        card.Controls.Add(stop);

        // Right Guardian identity panel, based on the supplied reference concept.
        var brandPanel = new Panel
        {
            Location = new Point(544, 20),
            Size = new Size(278, 340),
            BackColor = Color.FromArgb(4, 22, 35),
            BorderStyle = BorderStyle.FixedSingle
        };
        card.Controls.Add(brandPanel);

        var brandLogo = new PictureBox
        {
            Location = new Point(69, 26),
            Size = new Size(140, 140),
            SizeMode = PictureBoxSizeMode.Zoom,
            BackColor = Color.Transparent
        };
        if (File.Exists(logoPath)) brandLogo.Image = Image.FromFile(logoPath);
        brandPanel.Controls.Add(brandLogo);

        var brandName = MakeLabel("P2P GUARDIAN", 16F, FontStyle.Regular, AccentBright);
        brandName.Location = new Point(20, 178);
        brandName.AutoSize = false;
        brandName.TextAlign = ContentAlignment.MiddleCenter;
        brandName.Size = new Size(238, 28);
        brandPanel.Controls.Add(brandName);

        var brandSub = MakeLabel("OSRS DISCORD MONITOR", 9.5F, FontStyle.Regular, Muted);
        brandSub.Location = new Point(20, 210);
        brandSub.AutoSize = false;
        brandSub.TextAlign = ContentAlignment.MiddleCenter;
        brandSub.Size = new Size(238, 22);
        brandPanel.Controls.Add(brandSub);

        var brandLine = new Panel
        {
            Location = new Point(52, 242),
            Size = new Size(174, 1),
            BackColor = AccentBright
        };
        brandPanel.Controls.Add(brandLine);

        var brandSlogan = MakeLabel("PLAY SMARTER  •  STAY SAFER", 8.5F, FontStyle.Bold, AccentBright);
        brandSlogan.Location = new Point(15, 254);
        brandSlogan.AutoSize = false;
        brandSlogan.TextAlign = ContentAlignment.MiddleCenter;
        brandSlogan.Size = new Size(248, 24);
        brandPanel.Controls.Add(brandSlogan);

        var footerLine = new Panel
        {
            Location = new Point(24, 532),
            Size = new Size(852, 1),
            BackColor = CardBorder
        };
        Controls.Add(footerLine);

        var footer = MakeLabel("P2P Guardian  |  OSRS Discord Monitor", 9F, FontStyle.Regular, Muted);
        footer.Location = new Point(24, 550);
        Controls.Add(footer);

        var creator = new Label
        {
            Text = "Developed by Bas | Razor",
            Font = new Font("Segoe UI", 9F, FontStyle.Regular),
            ForeColor = Muted,
            BackColor = Color.Transparent,
            AutoSize = false,
            TextAlign = ContentAlignment.MiddleRight,
            Location = new Point(650, 546),
            Size = new Size(226, 24),
            Anchor = AnchorStyles.Top | AnchorStyles.Right
        };
        Controls.Add(creator);
    }

    private Button CreateButton(string text, Color back, Color fore)
    {
        var button = new Button
        {
            Text = text,
            BackColor = back,
            ForeColor = fore,
            FlatStyle = FlatStyle.Flat,
            Font = new Font("Segoe UI", 10F, FontStyle.Bold),
            TabStop = false,
            Cursor = Cursors.Hand,
            UseVisualStyleBackColor = false
        };
        button.FlatAppearance.BorderSize = 1;
        button.FlatAppearance.BorderColor = back == Accent ? AccentBright : CardBorder;
        button.FlatAppearance.MouseOverBackColor = back == Accent ? Color.FromArgb(0, 174, 239) : Color.FromArgb(23, 56, 79);
        return button;
    }

    private bool IsBotRunning()
    {
        try
        {
            foreach (var p in Process.GetProcessesByName("python"))
            {
                try
                {
                    string cmd = GetCommandLine(p);
                    if (cmd.Contains("osrs_discord_bot.py", StringComparison.OrdinalIgnoreCase)) return true;
                }
                catch { }
                finally { p.Dispose(); }
            }
            foreach (var p in Process.GetProcessesByName("pythonw"))
            {
                try
                {
                    string cmd = GetCommandLine(p);
                    if (cmd.Contains("osrs_discord_bot.py", StringComparison.OrdinalIgnoreCase)) return true;
                }
                catch { }
                finally { p.Dispose(); }
            }
        }
        catch { }
        return false;
    }

    private static string GetCommandLine(Process process)
    {
        try
        {
            using var searcher = new ManagementObjectSearcher(
                $"SELECT CommandLine FROM Win32_Process WHERE ProcessId = {process.Id}");
            foreach (ManagementObject obj in searcher.Get())
                return obj["CommandLine"]?.ToString() ?? "";
        }
        catch { }
        return "";
    }

    private string? FindPython()
    {
        foreach (string candidate in new[] { "python.exe", "py.exe" })
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = candidate,
                    Arguments = candidate == "py.exe" ? "-3 --version" : "--version",
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                };
                using var p = Process.Start(psi);
                if (p == null) continue;
                p.WaitForExit(3000);
                if (p.ExitCode == 0) return candidate;
            }
            catch { }
        }
        return null;
    }

    private void StartBot()
    {
        if (IsBotRunning()) { UpdateStatus(); return; }
        if (!File.Exists(botPath))
        {
            MessageBox.Show($"P2P Guardian bot was not found.\n\nExpected:\n{botPath}", "P2P Guardian", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        string tokenPath = Path.Combine(appDir, "discord_token.txt");
        if (!File.Exists(tokenPath))
        {
            MessageBox.Show("Discord bot token is missing.\n\nPlease complete the P2P Guardian setup first.", "P2P Guardian", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        string? python = FindPython();
        if (python == null)
        {
            MessageBox.Show("Python 3.12/3.13 could not be found.", "P2P Guardian", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = python,
                Arguments = $"\"{botPath}\"",
                WorkingDirectory = appDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            };
            Process.Start(psi);
        }
        catch (Exception ex)
        {
            MessageBox.Show($"P2P Guardian could not start the bot.\n\n{ex.Message}", "P2P Guardian", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        UpdateStatus();
    }

    private void StopBot()
    {
        try
        {
            foreach (string name in new[] { "python", "pythonw" })
            {
                foreach (var p in Process.GetProcessesByName(name))
                {
                    try
                    {
                        string cmd = GetCommandLine(p);
                        if (cmd.Contains("osrs_discord_bot.py", StringComparison.OrdinalIgnoreCase))
                        {
                            p.Kill(true);
                            p.WaitForExit(3000);
                        }
                    }
                    catch { }
                    finally { p.Dispose(); }
                }
            }
        }
        catch { }
        UpdateStatus();
    }

    private async Task CheckForUpdateAsync()
    {
        try
        {
            using var client = new HttpClient();
            client.DefaultRequestHeaders.UserAgent.ParseAdd("P2P-Guardian/" + CurrentVersion);

            using var response = await client.GetAsync(ReleasesApi);
            if (!response.IsSuccessStatusCode) return;

            using var stream = await response.Content.ReadAsStreamAsync();
            using var json = await JsonDocument.ParseAsync(stream);
            var root = json.RootElement;

            string tag = root.TryGetProperty("tag_name", out var tagProp) ? tagProp.GetString() ?? "" : "";
            string latestVersion = NormalizeVersion(tag);
            if (!IsNewerVersion(latestVersion, CurrentVersion)) return;

            string notes = root.TryGetProperty("body", out var bodyProp) ? bodyProp.GetString() ?? "" : "";
            string htmlUrl = root.TryGetProperty("html_url", out var urlProp) ? urlProp.GetString() ?? "" : "";

            if (string.IsNullOrWhiteSpace(htmlUrl)) return;

            using var dialog = new UpdateDialog(latestVersion, notes, htmlUrl, appDir);
            if (dialog.ShowDialog(this) != DialogResult.OK) return;

            OpenReleasePage(htmlUrl);
        }
        catch
        {
            // Update checking is optional. Network/API errors never stop the controller.
        }
    }

    private static string NormalizeVersion(string value)
    {
        value = (value ?? "").Trim();
        while (value.StartsWith("v", StringComparison.OrdinalIgnoreCase))
            value = value[1..];
        int dash = value.IndexOf('-');
        if (dash >= 0) value = value[..dash];
        return value;
    }

    private static bool IsNewerVersion(string latest, string current)
    {
        if (!Version.TryParse(NormalizeVersion(latest), out var latestVersion)) return false;
        if (!Version.TryParse(NormalizeVersion(current), out var currentVersion)) return false;
        return latestVersion > currentVersion;
    }

    private async void OpenReleasePage(string releaseUrl)
    {
        using var confirm = new UpdateConfirmDialog(releaseUrl);
        if (confirm.ShowDialog(this) != DialogResult.OK) return;

        string? tempSetup = null;

        try
        {
            using var client = new HttpClient();
            client.DefaultRequestHeaders.UserAgent.ParseAdd("P2P-Guardian/" + CurrentVersion);

            using var response = await client.GetAsync(
                ReleasesApi,
                HttpCompletionOption.ResponseHeadersRead);

            if (!response.IsSuccessStatusCode)
                throw new InvalidOperationException("GitHub could not be reached.");

            using var jsonStream = await response.Content.ReadAsStreamAsync();
            using var json = await JsonDocument.ParseAsync(jsonStream);
            var root = json.RootElement;

            string latestVersion = root.TryGetProperty("tag_name", out var tagProp)
                ? NormalizeVersion(tagProp.GetString() ?? "")
                : "";

            if (!IsNewerVersion(latestVersion, CurrentVersion))
                throw new InvalidOperationException("The release is no longer newer than this installed version.");

            if (!root.TryGetProperty("assets", out var assets))
                throw new InvalidOperationException("The official installer asset was not found.");

            string? downloadUrl = null;
            foreach (var asset in assets.EnumerateArray())
            {
                string name = asset.TryGetProperty("name", out var nameProp)
                    ? nameProp.GetString() ?? ""
                    : "";

                if (string.Equals(name, SetupAssetName, StringComparison.Ordinal))
                {
                    downloadUrl = asset.TryGetProperty("browser_download_url", out var urlProp)
                        ? urlProp.GetString()
                        : null;
                    break;
                }
            }

            if (string.IsNullOrWhiteSpace(downloadUrl))
                throw new InvalidOperationException($"The official asset '{SetupAssetName}' was not found.");

            tempSetup = Path.Combine(
                Path.GetTempPath(),
                $"P2P_Guardian_Setup_{latestVersion}.exe");

            using (var progressDialog = new UpdateProgressDialog(latestVersion))
            {
                progressDialog.Show(this);
                progressDialog.SetProgress(0, "Connecting to GitHub...");

                using var downloadResponse = await client.GetAsync(
                    downloadUrl,
                    HttpCompletionOption.ResponseHeadersRead);

                downloadResponse.EnsureSuccessStatusCode();

                long? totalBytes = downloadResponse.Content.Headers.ContentLength;

                using var input = await downloadResponse.Content.ReadAsStreamAsync();
                using var output = new FileStream(
                    tempSetup,
                    FileMode.Create,
                    FileAccess.Write,
                    FileShare.None);

                var buffer = new byte[81920];
                long downloaded = 0;
                int read;

                while ((read = await input.ReadAsync(buffer.AsMemory(0, buffer.Length))) > 0)
                {
                    await output.WriteAsync(buffer.AsMemory(0, read));
                    downloaded += read;

                    int percent = totalBytes.HasValue && totalBytes.Value > 0
                        ? (int)Math.Clamp(downloaded * 100L / totalBytes.Value, 0, 100)
                        : 0;

                    progressDialog.SetProgress(
                        percent,
                        totalBytes.HasValue
                            ? $"Downloading... {FormatBytes(downloaded)} / {FormatBytes(totalBytes.Value)}"
                            : $"Downloading... {FormatBytes(downloaded)}");
                }

                await output.FlushAsync();
                progressDialog.SetProgress(100, "Download complete. Starting installer...");
                progressDialog.Close();
            } // IMPORTANT: all download file streams are disposed before Process.Start.

            Process.Start(new ProcessStartInfo
            {
                FileName = tempSetup,
                UseShellExecute = true
            });

            Close();
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                $"The update could not be downloaded or started.\n\n{ex.Message}",
                "P2P Guardian Update",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    private static string FormatBytes(long bytes)
    {
        if (bytes < 1024) return $"{bytes} B";
        if (bytes < 1024 * 1024) return $"{bytes / 1024.0:0.0} KB";
        return $"{bytes / 1024.0 / 1024.0:0.0} MB";
    }

    private void UpdateStatus()
    {
        bool running = IsBotRunning();
        statusValue.Text = running ? "BOT IS RUNNING" : "BOT IS STOPPED";
        statusDot.BackColor = running ? Success : Danger;
        statusHint.Text = running ? "P2P Guardian is active and monitoring." : "Start or stop monitoring from the controls below.";
        statusHint.ForeColor = running ? Success : Muted;
    }
}

internal sealed class UpdateDialog : Form
{
    private static readonly Color Background = Color.FromArgb(3, 19, 31);
    private static readonly Color Card = Color.FromArgb(6, 26, 41);
    private static readonly Color CardBorder = Color.FromArgb(23, 56, 79);
    private static readonly Color White = Color.FromArgb(242, 246, 250);
    private static readonly Color Muted = Color.FromArgb(184, 201, 216);
    private static readonly Color Accent = Color.FromArgb(0, 143, 217);
    private static readonly Color AccentBright = Color.FromArgb(0, 174, 239);

    public UpdateDialog(string version, string notes, string releaseUrl, string appDir)
    {
        Text = "P2P Guardian Update";
        ClientSize = new Size(660, 500);
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        BackColor = Background;
        ForeColor = White;
        Font = new Font("Segoe UI", 9.5F);
        AutoScaleMode = AutoScaleMode.Dpi;

        try
        {
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath) ?? SystemIcons.Application;
            ShowIcon = true;
        }
        catch
        {
            Icon = SystemIcons.Application;
            ShowIcon = true;
        }

        var header = new Panel
        {
            Location = new Point(20, 18),
            Size = new Size(620, 112),
            BackColor = Card,
            BorderStyle = BorderStyle.FixedSingle
        };
        Controls.Add(header);

        string logoPath = Path.Combine(appDir, "P2P_Guardian_Logo.png");
        var logo = new PictureBox
        {
            Location = new Point(16, 12),
            Size = new Size(82, 82),
            SizeMode = PictureBoxSizeMode.Zoom,
            BackColor = Color.Transparent
        };
        if (File.Exists(logoPath)) logo.Image = Image.FromFile(logoPath);
        header.Controls.Add(logo);

        var brand = new Label
        {
            Text = "P2P GUARDIAN",
            Font = new Font("Segoe UI", 20F, FontStyle.Bold),
            ForeColor = White,
            BackColor = Color.Transparent,
            Location = new Point(112, 20),
            AutoSize = true
        };
        header.Controls.Add(brand);

        var monitor = new Label
        {
            Text = "OSRS DISCORD MONITOR",
            Font = new Font("Segoe UI", 10F, FontStyle.Bold),
            ForeColor = AccentBright,
            BackColor = Color.Transparent,
            Location = new Point(114, 57),
            AutoSize = true
        };
        header.Controls.Add(monitor);

        var slogan = new Label
        {
            Text = "PLAY SMARTER  •  STAY SAFER",
            Font = new Font("Segoe UI", 8.5F, FontStyle.Bold),
            ForeColor = AccentBright,
            BackColor = Color.Transparent,
            Location = new Point(114, 81),
            AutoSize = true
        };
        header.Controls.Add(slogan);

        var available = new Label
        {
            Text = $"UPDATE AVAILABLE  •  VERSION {version}",
            Font = new Font("Segoe UI", 9F, FontStyle.Bold),
            ForeColor = AccentBright,
            Location = new Point(24, 146),
            AutoSize = true
        };
        Controls.Add(available);

        var title = new Label
        {
            Text = $"P2P Guardian {version} is available",
            Font = new Font("Segoe UI", 18F, FontStyle.Bold),
            ForeColor = White,
            Location = new Point(22, 170),
            AutoSize = true
        };
        Controls.Add(title);

        var subtitle = new Label
        {
            Text = "What's new in this release:",
            Font = new Font("Segoe UI", 10F, FontStyle.Bold),
            ForeColor = AccentBright,
            Location = new Point(24, 214),
            AutoSize = true
        };
        Controls.Add(subtitle);

        var notesBox = new TextBox
        {
            Multiline = true,
            ReadOnly = true,
            ScrollBars = ScrollBars.Vertical,
            BackColor = Color.FromArgb(6, 26, 41),
            ForeColor = White,
            BorderStyle = BorderStyle.FixedSingle,
            Location = new Point(22, 244),
            Size = new Size(616, 155),
            Font = new Font("Segoe UI", 9.5F),
            Text = string.IsNullOrWhiteSpace(notes) ? "This release does not contain release notes." : notes.Trim()
        };
        Controls.Add(notesBox);

        var info = new Label
        {
            Text = "UPDATE NOW opens the official GitHub release page. You choose the installer yourself.",
            Font = new Font("Segoe UI", 8.5F),
            ForeColor = Muted,
            Location = new Point(24, 410),
            AutoSize = true
        };
        Controls.Add(info);

        var later = new Button
        {
            Text = "LATER",
            DialogResult = DialogResult.Cancel,
            Location = new Point(398, 442),
            Size = new Size(105, 42),
            BackColor = Color.FromArgb(9, 34, 53),
            ForeColor = White,
            FlatStyle = FlatStyle.Flat,
            Font = new Font("Segoe UI", 9F, FontStyle.Bold)
        };
        later.FlatAppearance.BorderColor = CardBorder;
        Controls.Add(later);

        var update = new Button
        {
            Text = "UPDATE NOW",
            DialogResult = DialogResult.OK,
            Location = new Point(513, 442),
            Size = new Size(125, 42),
            BackColor = Accent,
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
            Font = new Font("Segoe UI", 9F, FontStyle.Bold)
        };
        update.FlatAppearance.BorderColor = AccentBright;
        Controls.Add(update);

        AcceptButton = update;
        CancelButton = later;
    }
}

internal sealed class UpdateConfirmDialog : Form
{
    private static readonly Color Background = Color.FromArgb(3, 19, 31);
    private static readonly Color Card = Color.FromArgb(6, 26, 41);
    private static readonly Color CardBorder = Color.FromArgb(23, 56, 79);
    private static readonly Color White = Color.FromArgb(242, 246, 250);
    private static readonly Color Muted = Color.FromArgb(184, 201, 216);
    private static readonly Color Accent = Color.FromArgb(0, 143, 217);
    private static readonly Color AccentBright = Color.FromArgb(0, 174, 239);

    public UpdateConfirmDialog(string releaseUrl)
    {
        Text = "P2P Guardian Update";
        ClientSize = new Size(660, 430);
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        BackColor = Background;
        ForeColor = White;
        Font = new Font("Segoe UI", 9.5F);
        AutoScaleMode = AutoScaleMode.Dpi;

        try
        {
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath) ?? SystemIcons.Application;
            ShowIcon = true;
        }
        catch { Icon = SystemIcons.Application; }

        var header = new Panel
        {
            Location = new Point(20, 18),
            Size = new Size(620, 82),
            BackColor = Card,
            BorderStyle = BorderStyle.FixedSingle
        };
        Controls.Add(header);

        var title = new Label
        {
            Text = "READY TO UPDATE?",
            Font = new Font("Segoe UI", 18F, FontStyle.Bold),
            ForeColor = White,
            Location = new Point(22, 16),
            AutoSize = true
        };
        header.Controls.Add(title);

        var sub = new Label
        {
            Text = "The official P2P Guardian Setup.exe will be downloaded from GitHub.",
            Font = new Font("Segoe UI", 9.5F),
            ForeColor = AccentBright,
            Location = new Point(24, 50),
            AutoSize = true
        };
        header.Controls.Add(sub);

        var instructions = new Label
        {
            Text = "1. Click CONTINUE below.\n\n2. P2P Guardian will download the official Setup.exe from the latest GitHub release.\n\n3. The installer will start automatically after the download completes.\n\n4. Follow the normal P2P Guardian installer steps.\n\n5. The Controller will close when the installer starts.",
            Font = new Font("Segoe UI", 10F),
            ForeColor = White,
            Location = new Point(28, 122),
            Size = new Size(604, 210),
            AutoSize = false
        };
        Controls.Add(instructions);

        var note = new Label
        {
            Text = "Only the official P2P_Guardian_Setup.exe release asset is downloaded. The Controller closes when the installer starts.",
            Font = new Font("Segoe UI", 8.5F),
            ForeColor = Muted,
            Location = new Point(28, 337),
            AutoSize = true
        };
        Controls.Add(note);

        var cancel = new Button
        {
            Text = "CANCEL",
            DialogResult = DialogResult.Cancel,
            Location = new Point(405, 370),
            Size = new Size(105, 42),
            BackColor = Color.FromArgb(9, 34, 53),
            ForeColor = White,
            FlatStyle = FlatStyle.Flat,
            Font = new Font("Segoe UI", 9F, FontStyle.Bold)
        };
        cancel.FlatAppearance.BorderColor = CardBorder;
        Controls.Add(cancel);

        var cont = new Button
        {
            Text = "CONTINUE",
            DialogResult = DialogResult.OK,
            Location = new Point(520, 370),
            Size = new Size(120, 42),
            BackColor = Accent,
            ForeColor = White,
            FlatStyle = FlatStyle.Flat,
            Font = new Font("Segoe UI", 9F, FontStyle.Bold)
        };
        cont.FlatAppearance.BorderColor = AccentBright;
        Controls.Add(cont);

        AcceptButton = cont;
        CancelButton = cancel;
    }
}

internal sealed class UpdateProgressDialog : Form
{
    private readonly ProgressBar progress;
    private readonly Label status;

    public UpdateProgressDialog(string version)
    {
        Text = "P2P Guardian Update";
        ClientSize = new Size(520, 180);
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        ControlBox = false;
        BackColor = Color.FromArgb(3, 19, 31);
        ForeColor = Color.FromArgb(242, 246, 250);
        Font = new Font("Segoe UI", 9.5F);

        var title = new Label
        {
            Text = $"Downloading P2P Guardian {version}...",
            Font = new Font("Segoe UI", 13F, FontStyle.Bold),
            Location = new Point(24, 22),
            AutoSize = true
        };
        Controls.Add(title);

        progress = new ProgressBar
        {
            Location = new Point(24, 70),
            Size = new Size(472, 24),
            Minimum = 0,
            Maximum = 100
        };
        Controls.Add(progress);

        status = new Label
        {
            Text = "Connecting to GitHub...",
            Location = new Point(24, 108),
            AutoSize = true,
            ForeColor = Color.FromArgb(184, 201, 216)
        };
        Controls.Add(status);
    }

    public void SetProgress(int value, string text)
    {
        if (IsDisposed) return;
        if (InvokeRequired)
        {
            BeginInvoke(new Action(() => SetProgress(value, text)));
            return;
        }
        progress.Value = Math.Clamp(value, 0, 100);
        status.Text = text;
    }
}

internal sealed class GuardianCard : Panel
{
    public Color BorderColor { get; set; }
    public Color AccentColor { get; set; }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using var border = new Pen(BorderColor, 1);
        e.Graphics.DrawRectangle(border, 0, 0, Width - 1, Height - 1);
        using var accent = new SolidBrush(AccentColor);
        e.Graphics.FillRectangle(accent, 0, 0, 4, Height);
    }
}
