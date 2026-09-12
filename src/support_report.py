# OSRS Discord Monitor - Support Package Generator
# Developed by Bas | Razor

import json
import os
import platform
import socket
import time
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

APP_VERSION = "V24.1"
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "osrs_bot_config.json"
STATE_FILE = BASE_DIR / "client_state.json"

def configured_log_root():
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            value = data.get("log_root_directory") if isinstance(data, dict) else None
            if value:
                return Path(os.path.expandvars(os.path.expanduser(str(value))))
        except Exception:
            pass
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".detuksosrs"


LOG_ROOT = configured_log_root()
OUTPUT_DIR = Path.home() / "Desktop" / "OSRS Discord Monitor Support"
MAX_TOTAL_LOG_BYTES = 12 * 1024 * 1024
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_LOG_FILES = 8


def safe_config():
    if not CONFIG_FILE.exists():
        return {"status": "config file not found"}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"status": "config file is not a JSON object"}
        data.pop("token", None)
        data.pop("discord_token", None)
        return data
    except Exception as exc:
        return {"status": "could not read config", "error": str(exc)[:300]}


def add_text(zf, name, text):
    zf.writestr(name, text)


def collect_logs():
    if not LOG_ROOT.exists():
        return []
    files = []
    try:
        for p in LOG_ROOT.rglob("*.log*"):
            if p.is_file():
                try:
                    files.append((p.stat().st_mtime, p))
                except OSError:
                    pass
    except OSError:
        return []
    files.sort(reverse=True)
    selected = []
    total = 0
    for _, p in files[:50]:
        if len(selected) >= MAX_LOG_FILES or total >= MAX_TOTAL_LOG_BYTES:
            break
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size <= 0:
            continue
        take = min(size, MAX_FILE_BYTES, MAX_TOTAL_LOG_BYTES - total)
        if take <= 0:
            break
        selected.append((p, take))
        total += take
    return selected


def build_package(extra_text=None):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    zip_path = OUTPUT_DIR / f"OSRS_Discord_Monitor_Support_{stamp}.zip"

    info = [
        f"OSRS Discord Monitor support package",
        f"Version: {APP_VERSION}",
        f"Created: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Windows: {platform.platform()}",
        f"Python: {platform.python_version()}",
        f"Computer: {socket.gethostname()}",
        "",
        "This package is intended for troubleshooting.",
        "It does NOT include the Discord bot token.",
        "Review the included logs before sharing them; logs can contain account or client information.",
    ]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        add_text(zf, "support_info.txt", "\n".join(info) + "\n")
        add_text(zf, "osrs_bot_config_sanitized.json", json.dumps(safe_config(), indent=2, ensure_ascii=False))

        if STATE_FILE.exists():
            try:
                add_text(zf, "client_state.json", STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        if extra_text:
            add_text(zf, "bot_runtime_diagnostics.txt", extra_text)

        logs = collect_logs()
        for p, take in logs:
            try:
                data = p.read_bytes()
                if len(data) > take:
                    data = data[-take:]
                try:
                    rel = p.relative_to(LOG_ROOT)
                    name = Path("logs") / rel
                except ValueError:
                    name = Path("logs") / p.name
                zf.writestr(str(name).replace("\\", "/"), data)
            except OSError:
                pass

    return zip_path


def main():
    root = tk.Tk()
    root.withdraw()
    try:
        path = build_package()
        messagebox.showinfo(
            "OSRS Discord Monitor",
            "Support package created successfully.\n\n"
            f"Saved to:\n{path}\n\n"
            "Please review the ZIP before sending it to support.",
            parent=root,
        )
        try:
            os.startfile(str(OUTPUT_DIR))
        except OSError:
            pass
    except Exception as exc:
        messagebox.showerror(
            "Support package failed",
            "Could not create the support package.\n\n"
            + str(exc)[:1000],
            parent=root,
        )
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
