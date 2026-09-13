Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# P2P Guardian Control
# Manages the P2P Guardian Discord bot running on this PC.
$AppDir = $PSScriptRoot
$Bot = Join-Path $AppDir "osrs_discord_bot.py"

# Match the dark P2P Guardian installer style.
$DarkBg = [Drawing.Color]::FromArgb(48, 50, 70)
$PanelBg = [Drawing.Color]::FromArgb(61, 43, 35)
$TextColor = [Drawing.Color]::WhiteSmoke
$MutedText = [Drawing.Color]::Gainsboro
$Accent = [Drawing.Color]::FromArgb(88, 99, 150)

function Get-BotProcess {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @("python.exe","pythonw.exe") -and
            $_.CommandLine -like "*osrs_discord_bot.py*"
        }
}

function Update-Status {
    $p = @(Get-BotProcess)
    if ($p.Count -gt 0) {
        $status.Text = "BOT IS RUNNING"
        $status.ForeColor = [Drawing.Color]::LimeGreen
    } else {
        $status.Text = "BOT IS STOPPED"
        $status.ForeColor = [Drawing.Color]::Tomato
    }
}

function Start-Bot {
    if (-not (Test-Path $Bot)) {
        [Windows.Forms.MessageBox]::Show(
            "Bot file not found:`n`n$Bot",
            "P2P Guardian",
            "OK", "Error"
        ) | Out-Null
        return
    }

    if (@(Get-BotProcess).Count -gt 0) {
        Update-Status
        [Windows.Forms.MessageBox]::Show(
            "The P2P Guardian bot is already running.",
            "P2P Guardian",
            "OK", "Information"
        ) | Out-Null
        return
    }

    $pythonw = $null
    $candidates = @(
        (Join-Path ${env:LocalAppData} "Programs\Python\Python313\pythonw.exe"),
        (Join-Path ${env:ProgramFiles} "Python313\pythonw.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { $pythonw = $candidate; break }
    }

    if (-not $pythonw) {
        $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
        if ($cmd) { $pythonw = $cmd.Source }
    }

    if (-not $pythonw) {
        [Windows.Forms.MessageBox]::Show(
            "pythonw.exe could not be found.",
            "P2P Guardian",
            "OK", "Error"
        ) | Out-Null
        return
    }

    Start-Process -FilePath $pythonw -ArgumentList "`"$Bot`"" -WorkingDirectory $AppDir -WindowStyle Hidden
    Start-Sleep -Milliseconds 700
    Update-Status
}

function Stop-Bot {
    $p = @(Get-BotProcess)
    foreach ($item in $p) {
        Stop-Process -Id $item.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
    Update-Status
}

$form = New-Object Windows.Forms.Form
$form.Text = "P2P Guardian Control"
$form.Size = New-Object Drawing.Size(430,300)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.BackColor = $DarkBg
$form.ForeColor = $TextColor

$title = New-Object Windows.Forms.Label
$title.Text = "P2P Guardian"
$title.Font = New-Object Drawing.Font("Segoe UI",20,[Drawing.FontStyle]::Bold)
$title.AutoSize = $true
$title.ForeColor = $TextColor
$title.BackColor = $DarkBg
$title.Location = New-Object Drawing.Point(122,25)
$form.Controls.Add($title)

$subtitle = New-Object Windows.Forms.Label
$subtitle.Text = "Manage your P2P Guardian Discord bot"
$subtitle.AutoSize = $true
$subtitle.ForeColor = $MutedText
$subtitle.BackColor = $DarkBg
$subtitle.Location = New-Object Drawing.Point(105,65)
$form.Controls.Add($subtitle)

$panel = New-Object Windows.Forms.Panel
$panel.Location = New-Object Drawing.Point(25,92)
$panel.Size = New-Object Drawing.Size(380,135)
$panel.BackColor = $PanelBg
$form.Controls.Add($panel)

$statusLabel = New-Object Windows.Forms.Label
$statusLabel.Text = "Discord bot status:"
$statusLabel.AutoSize = $true
$statusLabel.ForeColor = $MutedText
$statusLabel.BackColor = $PanelBg
$statusLabel.Location = New-Object Drawing.Point(25,18)
$panel.Controls.Add($statusLabel)

$status = New-Object Windows.Forms.Label
$status.Font = New-Object Drawing.Font("Segoe UI",13,[Drawing.FontStyle]::Bold)
$status.AutoSize = $true
$status.BackColor = $PanelBg
$status.Location = New-Object Drawing.Point(25,45)
$panel.Controls.Add($status)

$start = New-Object Windows.Forms.Button
$start.Text = "START BOT"
$start.Size = New-Object Drawing.Size(140,48)
$start.Location = New-Object Drawing.Point(25,78)
$start.BackColor = $Accent
$start.ForeColor = [Drawing.Color]::White
$start.FlatStyle = [Windows.Forms.FlatStyle]::Flat
$start.FlatAppearance.BorderSize = 0
$start.Add_Click({ Start-Bot })
$panel.Controls.Add($start)

$stop = New-Object Windows.Forms.Button
$stop.Text = "STOP BOT"
$stop.Size = New-Object Drawing.Size(140,48)
$stop.Location = New-Object Drawing.Point(215,78)
$stop.BackColor = $Accent
$stop.ForeColor = [Drawing.Color]::White
$stop.FlatStyle = [Windows.Forms.FlatStyle]::Flat
$stop.FlatAppearance.BorderSize = 0
$stop.Add_Click({ Stop-Bot })
$panel.Controls.Add($stop)

$note = New-Object Windows.Forms.Label
$note.Text = "Automatic Windows startup remains enabled."
$note.AutoSize = $true
$note.ForeColor = $MutedText
$note.BackColor = $DarkBg
$note.Location = New-Object Drawing.Point(105,245)
$form.Controls.Add($note)

$timer = New-Object Windows.Forms.Timer
$timer.Interval = 2000
$timer.Add_Tick({ Update-Status })
$timer.Start()

Update-Status
[void]$form.ShowDialog()
