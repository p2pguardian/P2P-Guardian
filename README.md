# P2P Guardian

P2P Guardian is a Windows-based OSRS Discord Monitor.

## Features

- OSRS Discord monitoring
- Discord alerts for important events
- Login and logout detection
- Client stop detection
- Task monitoring
- Level-up notifications
- Discord slash commands
- Monitoring and logging
- Automatic startup with Windows
- Built-in support and bug reporting

## Installation

**Windows only**

1. Download the latest `OSRS_Discord_Monitor_Setup_V24_1.exe` from the Releases page.
2. Run the installer.
3. Enter your Discord bot token during installation.
4. Enter the Discord channel IDs you want to use.
5. Use Auto-detect for Client Paths whenever possible.
6. Finish the installation.
7. Start P2P Guardian from the desktop shortcut or Start Menu.

## Discord Commands

- `/help` — Show all available commands.
- `/status` — Show the current OSRS client and monitor status.
- `/screenshot` — Take a screenshot of the monitored PC.
- `/resources` — Show CPU and RAM usage.
- `/bugreport` — Create a support ZIP for bot/monitor errors.
- `/clear` — Delete 1–50 messages from the current Discord channel.
- `/clienthealth` — Check OSRS clients and Windows responsiveness.
- `/clientmap` — Show current PID/client mappings.
- `/clientevents` — Show recent login/logout mappings.
- `/logincheck` — Manually check the login screen.
- `/logstatus` — Show log monitoring status.
- `/logscan` — Scan the Detuks logs.
- `/logdebug` — Show recent live log changes.
- `/launcherscan` — Inspect Jagex Launcher files.

## Important

**Never share your Discord bot token.**

All Discord commands are restricted to the Discord bot owner.

## Support

If the bot or monitor behaves incorrectly, use:

`/bugreport`

The support package excludes the Discord bot token.

## Source Code

The source code is publicly available in the `src` folder.

The installer source is available in the `installer` folder.

No Discord bot tokens or other private credentials are included in this repository.

Developed by Bas | Razor
