# P2P Guardian

<p align="center">
  <img src="./assets/p2p-guardian-demo-polished.gif" alt="P2P Guardian installation and Discord monitoring demo" width="850">
</p>

P2P Guardian is a Windows-based OSRS Discord Monitor designed to send monitoring alerts, screenshots, task notifications, and level-up notifications to Discord.

## Current Release

**V24.2.5**

[Download the latest release](../../releases/latest)

## Features

- Discord monitoring notifications
- Account and client/PID status monitoring
- OSRS task monitoring
- Task notification channel support
- Level-up notification channel support
- Startup screenshot check-ins
- Periodic screenshot check-ins
- Manual screenshots through Discord
- Windows Graphics Capture (WGC) screenshot support
- Screenshot support when the OSRS client is minimized
- P2P Guardian Control for starting and stopping the bot
- Automatic Windows startup
- Guided first-time Discord bot setup
- Automatic Python dependency checking
- Automatic update notifications
- Existing installation update support
- Support and bug-reporting tools

## What's New in V24.2.5

- Updated P2P Guardian to V24.2.5
- Improved Windows Graphics Capture (WGC) screenshot support
- Screenshot capture works with minimized OSRS clients
- Added `windows-capture==2.0.1`
- Improved Python dependency checking
- Dependencies are checked before installation
- Only missing or incorrect dependencies need to be installed
- Improved installer version detection
- Improved new-installation and update handling
- Existing Discord configuration is preserved during updates
- Updated P2P Guardian Control version handling
- Improved GitHub release update checking
- Updated installer and public release structure
- Updated support and diagnostic tools

## Requirements

> **Note:** When using the P2P Guardian `.exe`, the required Python dependencies are checked automatically. Missing or incorrect dependencies are installed when required.

- Windows
- OSRS running on the Windows desktop
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
windows-capture==2.0.1