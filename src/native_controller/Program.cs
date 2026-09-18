using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Management;

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
        ClientSize = new Size(700, 600);
        MinimumSize = new Size(700, 600);
        MaximumSize = new Size(700, 600);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        BackColor = Background;
        ForeColor = White;
        Font = new Font("Segoe UI", 9.5F);
        AutoScaleMode = AutoScaleMode.Dpi;
        DoubleBuffered = true;

        string iconPath = Path.Combine(appDir, "P2P_Guardian_Desktop.ico");
        if (File.Exists(iconPath))
        {
            using var icon = new Icon(iconPath);
            Icon = new Icon(icon, new Size(32, 32));
        }

        BuildUi();
        UpdateStatus();

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
        var headerLogo = new PictureBox
        {
            Location = new Point(30, 8),
            Size = new Size(100, 100),
            SizeMode = PictureBoxSizeMode.Zoom,
            BackColor = Color.Transparent
        };
        string logoPath = Path.Combine(appDir, "P2P_Guardian_Logo.png");
        if (File.Exists(logoPath)) headerLogo.Image = Image.FromFile(logoPath);
        Controls.Add(headerLogo);

        var title = MakeLabel("P2P Guardian", 23F, FontStyle.Bold, White);
        title.Location = new Point(145, 22);
        Controls.Add(title);

        var appBadge = new Label
        {
            Text = "GUARDIAN",
            Font = new Font("Segoe UI", 8F, FontStyle.Bold),
            ForeColor = White,
            BackColor = Color.FromArgb(0, 136, 255),
            AutoSize = false,
            TextAlign = ContentAlignment.MiddleCenter,
            Location = new Point(145, 59),
            Size = new Size(76, 21)
        };
        Controls.Add(appBadge);

        var version = new Label
        {
            Text = "V24.2.4",
            Font = new Font("Segoe UI", 10F, FontStyle.Bold),
            ForeColor = AccentBright,
            BackColor = Color.Transparent,
            AutoSize = false,
            TextAlign = ContentAlignment.MiddleLeft,
            Location = new Point(233, 57),
            Size = new Size(72, 24)
        };
        Controls.Add(version);

        var subtitle = MakeLabel("OSRS DISCORD MONITOR", 9F, FontStyle.Bold, AccentBright);
        subtitle.Location = new Point(145, 88);
        Controls.Add(subtitle);

        var slogan = MakeLabel("PLAY SMARTER • STAY SAFER", 10F, FontStyle.Bold, AccentBright);
        slogan.Location = new Point(420, 56);
        slogan.AutoSize = false;
        slogan.TextAlign = ContentAlignment.MiddleRight;
        slogan.Size = new Size(244, 42);
        Controls.Add(slogan);

        var card = new GuardianCard
        {
            Location = new Point(24, 132),
            Size = new Size(652, 350),
            BackColor = Card,
            BorderColor = CardBorder,
            AccentColor = Accent
        };
        Controls.Add(card);

        var watermark = new PictureBox
        {
            Location = new Point(492, 46),
            Size = new Size(132, 132),
            SizeMode = PictureBoxSizeMode.Zoom,
            BackColor = Color.Transparent,
            Enabled = false
        };
        if (File.Exists(logoPath)) watermark.Image = Image.FromFile(logoPath);
        card.Controls.Add(watermark);

        var section = MakeLabel("BOT STATUS", 9F, FontStyle.Bold, AccentBright);
        section.Text = "BOT STATUS";
        section.Location = new Point(30, 25);
        card.Controls.Add(section);

        statusDot = new Label
        {
            Location = new Point(31, 62),
            Size = new Size(13, 13),
            BackColor = Danger
        };
        card.Controls.Add(statusDot);

        statusValue = MakeLabel("BOT IS STOPPED", 20F, FontStyle.Bold, White);
        statusValue.Location = new Point(58, 56);
        card.Controls.Add(statusValue);

        var detail = MakeLabel("P2P Guardian • OSRS Discord Monitor • V24.2.4", 9.5F, FontStyle.Regular, Muted);
        detail.Location = new Point(58, 94);
        card.Controls.Add(detail);

        var divider = new Panel
        {
            Location = new Point(30, 128),
            Size = new Size(430, 1),
            BackColor = CardBorder
        };
        card.Controls.Add(divider);

        statusHint = MakeLabel("Use the controls below to start or stop the monitor.", 9F, FontStyle.Regular, Muted);
        statusHint.Location = new Point(30, 148);
        card.Controls.Add(statusHint);

        var start = CreateButton("START BOT", Accent, White);
        start.Location = new Point(30, 205);
        start.Size = new Size(200, 48);
        start.Click += (_, _) => StartBot();
        card.Controls.Add(start);

        var stop = CreateButton("STOP BOT", Color.FromArgb(9, 34, 53), White);
        stop.Location = new Point(242, 205);
        stop.Size = new Size(200, 48);
        stop.Click += (_, _) => StopBot();
        card.Controls.Add(stop);

        var footerLine = new Panel
        {
            Location = new Point(24, 508),
            Size = new Size(652, 1),
            BackColor = CardBorder
        };
        Controls.Add(footerLine);

        var footer = MakeLabel("P2P Guardian  |  OSRS Discord Monitor", 9F, FontStyle.Regular, Muted);
        footer.Location = new Point(24, 528);
        Controls.Add(footer);

        var creator = new Label
        {
            Text = "Developed by Bas | Razor",
            Font = new Font("Segoe UI", 9F, FontStyle.Regular),
            ForeColor = Muted,
            BackColor = Color.Transparent,
            AutoSize = false,
            TextAlign = ContentAlignment.MiddleRight,
            Location = new Point(470, 524),
            Size = new Size(182, 24),
            Anchor = AnchorStyles.Top | AnchorStyles.Right
        };
        Controls.Add(creator);

        var note = MakeLabel("Windows startup is enabled.", 8.5F, FontStyle.Regular, Muted);
        note.Location = new Point(24, 561);
        Controls.Add(note);
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
                return obj["CommandLine"]?.ToString() ?? string.Empty;
        }
        catch { }
        return string.Empty;
    }

    private string? FindPython()
    {
        var candidates = new List<string>();
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        string programFilesX86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);
        candidates.AddRange(new[]
        {
            Path.Combine(local, "Programs", "Python", "Python313", "pythonw.exe"),
            Path.Combine(local, "Programs", "Python", "Python312", "pythonw.exe"),
            Path.Combine(programFiles, "Python313", "pythonw.exe"),
            Path.Combine(programFilesX86, "Python313", "pythonw.exe"),
            Path.Combine(programFiles, "Python312", "pythonw.exe"),
            Path.Combine(programFilesX86, "Python312", "pythonw.exe")
        });
        try
        {
            string path = Environment.GetEnvironmentVariable("PATH") ?? "";
            foreach (string part in path.Split(';', StringSplitOptions.RemoveEmptyEntries))
            {
                string candidate = Path.Combine(part.Trim(), "pythonw.exe");
                if (!candidates.Contains(candidate, StringComparer.OrdinalIgnoreCase)) candidates.Add(candidate);
            }
        }
        catch { }
        return candidates.FirstOrDefault(File.Exists);
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

    private void UpdateStatus()
    {
        bool running = IsBotRunning();
        statusValue.Text = running ? "BOT IS RUNNING" : "BOT IS STOPPED";
        statusDot.BackColor = running ? Success : Danger;
        statusHint.Text = running ? "P2P Guardian is active and monitoring." : "Start or stop monitoring from the controls below.";
        statusHint.ForeColor = running ? Color.FromArgb(77, 219, 131) : Muted;
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
