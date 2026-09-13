# P2P Guardian

P2P Guardian is a Windows-based OSRS Discord Monitor designed to send monitoring alerts, screenshots, task notifications, and level-up notifications to Discord.

## V24.2.2

### What's New

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

## Features

- Discord notifications
- Startup screenshot check-in
- Periodic screenshot check-ins
- OSRS task monitoring
- Task notification channel support
- Level-up notification channel support
- P2P Guardian Control for starting and stopping the bot
- Automatic Windows startup
- Support and bug-reporting tools

## Requirements

- Windows
- OSRS running in an active Windows desktop session
- Tesseract OCR installed
- A Discord bot created through the Discord Developer Portal
- The Discord bot token
- The required Discord channel IDs and your Discord user ID

### Python dependencies

```text
discord.py
Pillow
psutil
pytesseract
opencv-python
numpy
```

## Discord Bot Setup

Create a Discord application and bot in the Discord Developer Portal.

The bot requires these OAuth2 scopes:

- bot
- applications.commands

The bot requires these permissions:

- View Channels
- Send Messages
- Embed Links
- Attach Files

Administrator permission is not required.

## Installation

For a first-time installation, the installer guides you through the Discord bot requirements and asks for your local bot token and Discord channel/user IDs.

For an existing installation, updates preserve the current local token and Discord settings.

## Security

The public repository does **not** contain:

- Discord bot tokens
- Personal Discord user IDs
- Private Discord channel IDs

Keep your bot token private. Do not commit `discord_token.txt` or `osrs_bot_config.json` to the public repository.

## Disclaimer

P2P Guardian is provided as-is.

You are responsible for how you use this software.

The developer is not responsible for OSRS or Discord bans, account restrictions, data loss, system damage, or other direct or indirect consequences resulting from its use.

**USE AT YOUR OWN RISK.**

## Source Code

The source code is publicly available in the `src` folder.

The installer source is available in the `installer` folder.

No Discord bot tokens or other private credentials are included in this repository.

## Support

Use the included support and bug-reporting tools when reporting problems. Please provide relevant logs and details about the issue without sharing your Discord bot token or other private credentials.

## License

See the repository for the applicable project terms.

The support package excludes the Discord bot token.

## Source Code

The source code is publicly available in the `src` folder.

The installer source is available in the `installer` folder.

No Discord bot tokens or other private credentials are included in this repository.

Developed by Bas | Razor
