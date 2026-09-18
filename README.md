# P2P Guardian

P2P Guardian is a Windows-based OSRS Discord Monitor designed to send monitoring alerts, screenshots, task notifications, and level-up notifications to Discord.

## Current Release

**V24.2.2**

## Features

- Discord monitoring notifications
- Startup screenshot check-in
- Periodic screenshot check-ins
- OSRS task monitoring
- Task notification channel support
- Level-up notification channel support
- P2P Guardian Control for starting and stopping the bot
- Automatic Windows startup
- Guided first-time Discord bot setup
- Support and bug-reporting tools

## What's New in V24.2.2

- Improved installer update detection
- Existing Discord token and Discord settings are preserved during updates
- Guided first-time Discord bot setup
- Developer Portal instructions and required permissions
- Improved P2P Guardian Control interface
- Improved bot startup and management
- Startup and periodic Discord check-in screenshots
- Task monitoring and task alerts
- Level-up notifications
- Windows startup support

## Requirements

- Windows
- OSRS running in an active Windows desktop session
- Tesseract OCR installed
- A Discord bot created through the Discord Developer Portal
- Your Discord bot token
- The required Discord channel IDs
- Your Discord user ID

### Python Dependencies

```text
discord.py
Pillow
psutil
pytesseract
opencv-python
numpy
```

## Discord Bot Setup

Create a Discord application and bot through the Discord Developer Portal.

The bot requires these OAuth2 scopes:

- `bot`
- `applications.commands`

The bot requires these permissions:

- View Channels
- Send Messages
- Embed Links
- Attach Files

Administrator permission is **not required**.

## Installation

For a first-time installation, the P2P Guardian installer guides you through the required Discord bot configuration.

You will need to provide your own local:

- Discord bot token
- Discord channel IDs
- Discord user ID

For an existing installation, updates preserve the existing local Discord token and Discord settings.

## Source Code

The repository contains the public source code used by P2P Guardian.

- `src/` — OSRS Discord Monitor source files
- `installer/` — Inno Setup installer source and build information
- `README.md` — Project documentation

The repository does not contain private Discord credentials.

## Security

Never publish or commit your private Discord credentials.

The public repository does **not** contain:

- Discord bot tokens
- Personal Discord user IDs
- Private Discord channel IDs
- API keys
- Passwords
- Webhooks

Do not commit local configuration files such as:

```text
discord_token.txt
osrs_bot_config.json
```

Keep your Discord bot token private.

## Updates

Official P2P Guardian releases are published through the GitHub Releases page.

Updates are designed to preserve the existing local Discord configuration.

Always obtain release files from the official P2P Guardian repository.

## Support

Use the included support and bug-reporting tools when reporting problems.

When reporting an issue, provide relevant logs and details about the problem.

**Never include your Discord bot token or other private credentials in a support request.**

## Disclaimer

P2P Guardian is provided as-is.

You are responsible for how you use this software.

The developer is not responsible for OSRS or Discord bans, account restrictions, data loss, system damage, or other direct or indirect consequences resulting from its use.

**USE AT YOUR OWN RISK.**

## License

See the repository for the applicable project terms.

Support packages must not contain the Discord bot token or other private credentials.

---

Developed by **Bas | Razor**
