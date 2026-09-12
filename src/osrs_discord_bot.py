# OSRS Discord Monitor — STABLE V24.1
# Login/logout primary signals: action=Play / action=Logout / break-cycle relog confirmation.
# V24.1 makes login state authoritative from observed log transitions, persists per-client state across bot restarts, never infers login state from the window title, and never maps action coordinates to minimized windows. Ambiguous multi-client events are suppressed rather than assigned to the wrong client.

"""
OSRS Discord Monitor - log based task monitoring.

This version keeps the useful monitoring from the previous bot, but replaces
screen-based task-overlay detection with live monitoring of the OSRS/P2P log.

Requirements:
    pip install discord.py pillow psutil pytesseract opencv-python numpy

Windows requirements:
    - Tesseract OCR installed
    - OSRS client running in an active Windows desktop session

Security:
    Set the Discord bot token in the DISCORD_TOKEN environment variable.
    Do not hard-code the token into this file.
"""

import io
import os
import asyncio
import re
import time
import ctypes
import json
import subprocess
import threading
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import discord
import psutil
from discord import app_commands
from discord.ext import tasks
from PIL import ImageGrab

try:
    import support_report
except Exception:
    support_report = None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
TOKEN_FILE = Path(__file__).with_name("discord_token.txt")
if not TOKEN and TOKEN_FILE.exists():
    try:
        TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        TOKEN = ""

# Automatically populated from the Discord application owner.
BOT_OWNER_ID = None
_COMMANDS_SYNCED = False

# Normal Discord alerts are user-safe by default. Set OSRS_SHOW_TECHNICAL_DETAILS=1
# only on a private/test setup if detailed PID/window/log signal data is wanted.
SHOW_TECHNICAL_DETAILS_IN_ALERTS = os.environ.get("OSRS_SHOW_TECHNICAL_DETAILS", "0").strip().lower() in {"1", "true", "yes", "on"}

PROCESS_NAME = "osclient.exe"

# OSRS log locations. The Detuks client writes its own logs in the .detuksosrs
# root directory, while the bot/client logs are also kept in .detuksosrs\logs.
# Monitor both locations so login/logout and bot task/resource events are not missed.
LOG_ROOT_DIRECTORY = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".detuksosrs"
LOG_DIRECTORY = LOG_ROOT_DIRECTORY / "logs"
# Jagex Launcher installation path. We inspect it for useful logs/configuration
# during testing, but do not assume every installation contains the same files.
JAGEX_LAUNCHER_DIRECTORY = Path(os.environ.get("PROGRAMFILES_X86", r"C:\Program Files (x86)")) / "Jagex Launcher"
LOG_FILE_PATTERNS = (
    "*.log",
    "*.log.*",
    "*.log*",
)
LOG_SUBDIRECTORY_PATTERNS = (
    "client*.log",
)
LOG_CHECK_INTERVAL_SECONDS = 2
LOG_BOOTSTRAP_LOOKBACK_BYTES = 512 * 1024
LOG_STATE_STALE_MINUTES = 30
LOG_PENDING_LOGOUT_SECONDS = 30

# Channel for process-stop / logout alerts and periodic screenshots.
NOTIFY_CHANNEL_ID = None
PING_USER_ID = None

# Dedicated task channel. Task messages do NOT ping anyone.
TASK_NOTIFY_CHANNEL_ID = None

# Optional dedicated channel for level-up notifications. If left empty,
# level-ups use TASK_NOTIFY_CHANNEL_ID.
LEVEL_NOTIFY_CHANNEL_ID = None

# Optional installer-managed configuration. Values in osrs_bot_config.json override defaults above.
CONFIG_FILE = Path(__file__).with_name("osrs_bot_config.json")
try:
    if CONFIG_FILE.exists():
        _cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        NOTIFY_CHANNEL_ID = int(_cfg.get("notify_channel_id")) if _cfg.get("notify_channel_id") else None
        TASK_NOTIFY_CHANNEL_ID = int(_cfg.get("task_notify_channel_id")) if _cfg.get("task_notify_channel_id") else None
        LEVEL_NOTIFY_CHANNEL_ID = int(_cfg.get("level_notify_channel_id")) if _cfg.get("level_notify_channel_id") else None
        PING_USER_ID = int(_cfg.get("ping_user_id")) if _cfg.get("ping_user_id") else None
        if _cfg.get("log_root_directory"):
            LOG_ROOT_DIRECTORY = Path(os.path.expandvars(os.path.expanduser(_cfg["log_root_directory"])))
            LOG_DIRECTORY = LOG_ROOT_DIRECTORY / "logs"
        if _cfg.get("jagex_launcher_directory"):
            JAGEX_LAUNCHER_DIRECTORY = Path(os.path.expandvars(os.path.expanduser(_cfg["jagex_launcher_directory"])))
except (OSError, ValueError, TypeError, json.JSONDecodeError):
    pass

# Periodic screenshot in the existing notification channel.
PERIODIC_SCREENSHOT_INTERVAL_MINUTES = 30

# Process monitoring.
CHECK_INTERVAL_SECONDS = 60

# Full-screen OCR login/logout detection remains as a fallback/manual check.
LOGIN_SCREEN_CHECK_INTERVAL_SECONDS = 20

# Per-client Windows health checks. These work for minimized clients too.
CLIENT_HEALTH_CHECK_INTERVAL_SECONDS = 15
HUNG_CONSECUTIVE_FAILURES = 3
WINDOW_RESPONSE_TIMEOUT_MS = 2000

# Windows Application Event Log crash/error check.
WINDOWS_EVENT_CHECK_INTERVAL_SECONDS = 30
WINDOWS_EVENT_LOOKBACK_SECONDS = 90

# Debounce window for repeated logout/login log signals.
LOGOUT_CONFIRM_WINDOW_SECONDS = 45


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------

_osrs_state = "unknown"
_last_login_detection = None
_last_login_detection_at = None
_monitor_errors = {}

_process_was_running = None
_login_pixel_was_visible = None

# Per-client runtime state keyed by osclient.exe PID.
_client_health = {}
_client_closed_candidates = {}
_last_windows_event_keys = deque(maxlen=200)
_last_logout_log_event_at = {}
_last_logout_alert_at = {}
_last_login_log_event_at = {}
_last_login_alert_at = {}
_last_login_logout_signal = None
_login_logout_debug_recent = deque(maxlen=120)
_login_state_by_log = {}
_login_state_by_pid = {}
_login_signal_history_by_log = {}
_client_last_login_logout_signal = {}
# Recent per-PID client registry used by /status to show clear per-client states,
# including recently closed clients.
_known_clients = {}
KNOWN_CLIENT_RETENTION_SECONDS = 3600
CLIENT_STATE_FILE = Path(__file__).with_name("client_state.json")
CLIENT_STATE_VERSION = 1
CLIENT_STATE_MAX_AGE_SECONDS = 7 * 24 * 3600
# Short-lived action batches: multiple log lines emitted within one action burst
# are resolved against the client states that existed before the burst. This
# prevents the second line of one real logout from being reassigned to another
# client, while still allowing two genuinely simultaneous client actions.
ACTION_BATCH_WINDOW_SECONDS = 5.0
_action_event_batch = {"state": None, "started": 0.0, "candidates": [], "assigned": set()}
_action_event_queue = deque(maxlen=50)
_action_event_lock = threading.Lock()
# Exact duplicate log signals (the OSRS client can emit the same action twice).
# Keep them separate from the simultaneous-client mapping queue so a duplicate
# logout/login from one client is never reassigned to another PID.
_recent_signal_fingerprints = deque(maxlen=100)
DUPLICATE_SIGNAL_WINDOW_SECONDS = 2.0
_log_bootstrap_done = False
_log_scan_cache = {}

_current_task = None
_current_task_started = None
_current_task_duration_minutes = None
_current_task_activity = None
_current_task_location = None
_current_task_last_log_file = None
_current_task_last_update = None

_next_play_length_hours = None
_next_break_length_hours = None

_log_current_file = None
_log_current_position = 0
_log_partial_line = ""
# Every client*.log file is tailed independently. This is important when
# multiple OSRS clients are running and each client writes to its own log.
_log_file_positions = {}
_log_file_partials = {}
_log_file_identities = {}
_log_recent_lines = deque(maxlen=80)
_log_failure_reasons_by_log = {}
_log_pending_tasks = {}
_log_last_task_event_keys = {}
_log_last_failure_time = 0.0
_log_last_level_event_key = None


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------


def is_process_running(name: str) -> bool:
    name = name.lower()
    for p in psutil.process_iter(["name"]):
        try:
            if name in (p.info["name"] or "").lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _record_monitor_error(name, exc):
    _monitor_errors[name] = f"{type(exc).__name__}: {exc}"
    print(f"[{name}] monitor error: {exc}")


def _record_monitor_ok(name):
    _monitor_errors.pop(name, None)


def _format_duration_hours(hours):
    if hours is None:
        return "Unknown"
    total_seconds = max(0, int(round(hours * 3600)))
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s and not h:
        parts.append(f"{s}s")
    return " ".join(parts) or "0s"


def _format_minutes(minutes):
    if minutes is None:
        return "Unknown"
    total_seconds = max(0, int(round(minutes * 60)))
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m" if m else f"{h}h"
    if m:
        return f"{m}m" if not s else f"{m}m {s}s"
    return f"{s}s"


def _format_timestamp(dt):
    if not dt:
        return "Unknown"
    return dt.strftime("%d-%m-%Y %H:%M:%S")


def _parse_log_timestamp(line):
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})", line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return None


def _log_message(line):
    # Everything after the final " - " is the actual log message.
    parts = line.split(" - ", 1)
    return parts[1].strip() if len(parts) == 2 else line.strip()


def _shorten(text, limit=900):
    text = " ".join(text.split()).strip()
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


# ---------------------------------------------------------------------------
# Per-client Windows health / window helpers
# ---------------------------------------------------------------------------


def _get_osrs_clients():
    """Return one record per osclient.exe process, including its main window."""
    processes = []
    for p in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            if (p.info["name"] or "").lower() != PROCESS_NAME.lower():
                continue
            processes.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    windows_by_pid = {}

    try:
        import win32gui
        import win32process

        def callback(hwnd, _):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid not in {p.pid for p in processes}:
                    return
                title = win32gui.GetWindowText(hwnd).strip()
                if not title:
                    return
                visible = bool(win32gui.IsWindowVisible(hwnd))
                minimized = bool(win32gui.IsIconic(hwnd))
                try:
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    rect = (int(left), int(top), int(right), int(bottom))
                except Exception:
                    rect = None
                entry = {
                    "hwnd": hwnd,
                    "title": title,
                    "visible": visible,
                    "minimized": minimized,
                    "rect": rect,
                }
                windows_by_pid.setdefault(pid, []).append(entry)
            except Exception:
                pass

        win32gui.EnumWindows(callback, None)
    except Exception as exc:
        _record_monitor_error("client windows", exc)

    result = []
    for p in processes:
        pid = p.pid
        windows = windows_by_pid.get(pid, [])
        # Prefer the BotClient window over the console window.
        windows.sort(key=lambda w: ("botclient" not in w["title"].lower(), w["title"]))
        main = windows[0] if windows else None
        result.append({
            "pid": pid,
            "create_time": p.info.get("create_time"),
            "window": main,
            "windows": windows,
        })
    return result


def _window_responds(hwnd, timeout_ms=WINDOW_RESPONSE_TIMEOUT_MS):
    """Ask Windows whether a window responds to a harmless WM_NULL message."""
    if not hwnd:
        return None
    try:
        user32 = ctypes.windll.user32
        SMTO_ABORTIFHUNG = 0x0002
        result = ctypes.c_ulong()
        # WM_NULL = 0. SendMessageTimeoutW returns 0 on timeout/failure.
        ok = user32.SendMessageTimeoutW(
            ctypes.c_void_p(int(hwnd)),
            0,
            0,
            0,
            SMTO_ABORTIFHUNG,
            int(timeout_ms),
            ctypes.byref(result),
        )
        return bool(ok)
    except Exception:
        return None


def _client_display_name(client_info):
    """Return a user-friendly client/account name without technical identifiers."""
    window = client_info.get("window") or {}
    title = (window.get("title") or "OSRS client").strip()

    # BotClient titles normally look like:
    # BotClient - V1.2.426-STABLE - AccountName
    parts = [part.strip() for part in title.split(" - ") if part.strip()]
    if len(parts) >= 3 and parts[0].lower() == "botclient":
        account = " - ".join(parts[2:]).strip()
        if account:
            return account

    # If the title does not use the BotClient format, keep the readable title
    # but never add a PID or other technical identifier.
    return title or "OSRS client"


def _load_persistent_client_states():
    """Load the last confirmed per-account/client state from disk.

    Window titles are used only to identify the account/client label. They are
    never used as evidence that the client is currently logged in.
    """
    try:
        if not CLIENT_STATE_FILE.exists():
            return
        data = json.loads(CLIENT_STATE_FILE.read_text(encoding="utf-8"))
        if data.get("version") != CLIENT_STATE_VERSION:
            return
        now = time.time()
        for label, item in (data.get("clients") or {}).items():
            if not isinstance(item, dict):
                continue
            saved_at = float(item.get("saved_at", 0) or 0)
            if saved_at and now - saved_at > CLIENT_STATE_MAX_AGE_SECONDS:
                continue
            state = item.get("state")
            if state not in ("logged_in", "login_screen"):
                continue
            _known_clients.setdefault("saved:" + label, {}).update({
                "label": label,
                "persistent_state": state,
                "persistent_saved_at": saved_at,
            })
    except Exception as exc:
        _record_monitor_error("Client state persistence", f"load failed: {exc}")


def _save_persistent_client_states():
    """Persist confirmed states keyed by recognizable client/account label."""
    clients = {}
    now = time.time()
    for key, known in _known_clients.items():
        if str(key).startswith("saved:"):
            continue
        label = (known.get("label") or "").strip()
        state = known.get("persistent_state") or known.get("state")
        if not label or state not in ("logged_in", "login_screen"):
            continue
        clients[label] = {"state": state, "saved_at": now}
    try:
        payload = {"version": CLIENT_STATE_VERSION, "clients": clients}
        temp = CLIENT_STATE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(CLIENT_STATE_FILE)
    except Exception as exc:
        _record_monitor_error("Client state persistence", f"save failed: {exc}")


def _persistent_state_for_client(client_info):
    label = _client_display_name(client_info)
    if not label or label in {"OSRS client", "BotClient", "Old School RuneScape Console"}:
        return None
    saved = _known_clients.get("saved:" + label, {})
    state = saved.get("persistent_state")
    if state in ("logged_in", "login_screen"):
        return state
    return None


def _apply_persistent_state_to_live_clients():
    """Restore state by account/client label after a bot restart."""
    for info in _get_osrs_clients():
        pid = info.get("pid")
        if pid is None:
            continue
        saved = _persistent_state_for_client(info)
        if saved:
            _login_state_by_pid[pid] = saved
            known = _known_clients.setdefault(pid, {})
            known["label"] = _client_display_name(info)
            known["persistent_state"] = saved
            known["last_state_source"] = "persistent client state"


def _infer_login_state_from_window(client_info):
    """Return unknown: a window title identifies a client, not its login state."""
    return "unknown"


def _refresh_pid_login_states_from_client_health():
    """Refresh live client registry without guessing login state from titles."""
    clients = _get_osrs_clients()
    for info in clients:
        pid = info.get("pid")
        if pid is None:
            continue
        known = _known_clients.setdefault(pid, {})
        known["title"] = ((info.get("window") or {}).get("title") or "OSRS client").strip()
        known["label"] = _client_label(info)
        if _login_state_by_pid.get(pid) not in ("logged_in", "login_screen"):
            saved = _persistent_state_for_client(info)
            if saved:
                _login_state_by_pid[pid] = saved
                known["persistent_state"] = saved
                known["last_state_source"] = "persistent client state"


def _client_label(client_info):
    """Public-facing client label, preserving the last known account name."""
    label = _client_display_name(client_info)
    pid = client_info.get("pid") if client_info else None
    if pid is not None and label in {"OSRS client", "BotClient", "Old School RuneScape Console"}:
        known = _known_clients.get(pid, {})
        known_label = (known.get("label") or "").strip()
        if known_label:
            return known_label
    return label


def _client_window_state(client_info):
    window = client_info.get("window") or {}
    if not window:
        return "No main window found"
    if window.get("minimized"):
        return "Minimized"
    if window.get("visible"):
        return "Visible"
    return "Hidden"


def _get_foreground_osrs_pid():
    """Return the PID of the foreground OSRS client, if any."""
    try:
        import win32gui
        import win32process
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        pid = int(pid)
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if proc.info["pid"] == pid and (proc.info["name"] or "").lower() == PROCESS_NAME.lower():
                    return pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        return None
    return None


def _extract_action_coordinates(message):
    """Extract x/y from Detuks action lines when present."""
    match = re.search(r"\bx=(-?\d+)\s*,\s*y=(-?\d+)\b", message, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _point_in_rect(point, rect):
    if not point or not rect:
        return False
    x, y = point
    left, top, right, bottom = rect
    return left <= x < right and top <= y < bottom


def _resolve_signal_client(message):
    """Resolve a login/logout event to a live osclient.exe PID.

    Multiple-client strategy:
      1. Map the action x/y point to a live OSRS window rectangle.
      2. If several clients match, prefer a PID not already used by a very recent
         event of the same action.
      3. Otherwise use the foreground OSRS client, again preferring an unused PID.
      4. Fall back to a single running client.

    This keeps genuinely simultaneous client events separate while exact duplicate
    log lines from one client are handled before PID reassignment.
    """
    clients = _get_osrs_clients()
    if not clients:
        return None, "no OSRS client found"

    now = time.time()
    point = _extract_action_coordinates(message)
    action_state, _confidence = _classify_login_logout_signal(message)

    recent_pids = set()
    with _action_event_lock:
        for event_time, event_state, event_pid in list(_action_event_queue):
            if now - event_time <= 3.0 and event_state == action_state and event_pid is not None:
                recent_pids.add(event_pid)

    # IMPORTANT: when only one client is currently in the relevant state,
    # prefer that state before using window coordinates/foreground heuristics.
    # This prevents an already-logged-out client from stealing a real logout
    # event from the client that is still logged in (and vice versa for login).
    if action_state == "logout":
        logged_in_clients = [
            info for info in clients
            if _login_state_by_pid.get(info.get("pid"), "unknown") == "logged_in"
            and info.get("pid") not in recent_pids
        ]
        if len(logged_in_clients) == 1:
            return logged_in_clients[0], "current logged-in state -> logout"
    elif action_state == "login":
        non_logged_in_clients = [
            info for info in clients
            if _login_state_by_pid.get(info.get("pid"), "unknown") != "logged_in"
            and info.get("pid") not in recent_pids
        ]
        if len(non_logged_in_clients) == 1:
            return non_logged_in_clients[0], "current non-logged-in state -> login"

    if point:
        matches = []
        for info in clients:
            # Action coordinates come from the rendered client. A minimized
            # window cannot be the source of those screen coordinates, so never
            # use its stale/restored rectangle for event attribution.
            if (info.get("window") or {}).get("minimized"):
                continue
            for window in info.get("windows", []):
                if window.get("minimized"):
                    continue
                if _point_in_rect(point, window.get("rect")):
                    matches.append(info)
                    break

        if len(matches) == 1:
            return matches[0], "action x/y -> window"

        if matches:
            unused = [m for m in matches if m["pid"] not in recent_pids]
            if len(unused) == 1:
                return unused[0], "action x/y -> unused window"
            if unused:
                return unused[0], "action x/y -> first unused window"

    foreground_pid = _get_foreground_osrs_pid()
    if foreground_pid is not None:
        for info in clients:
            if info["pid"] == foreground_pid and foreground_pid not in recent_pids:
                return info, "foreground window -> unused PID"

    unused_clients = [info for info in clients if info["pid"] not in recent_pids]
    if len(unused_clients) == 1:
        return unused_clients[0], "unused client fallback"

    if len(clients) == 1:
        return clients[0], "single running client"

    return None, "ambiguous multiple clients"

def _format_signal_client(client_info, source):
    # Public alerts should identify the client, but avoid exposing internal
    # log details, coordinates, or PID-matching diagnostics. PID is intentionally
    # kept visible because it is useful for distinguishing multiple clients.
    if not client_info:
        return "**Client:** `unresolved`"
    pid = client_info.get("pid", "?")
    label = _client_label(client_info)
    return (
        f"**Client:** `{label}`\n"
        f"**PID:** `{pid}`"
    )


def _login_logout_alert_details(filename, timestamp, message, client_info=None, source=None):
    if not SHOW_TECHNICAL_DETAILS_IN_ALERTS:
        return "\n" + _format_signal_client(client_info, source or "unresolved")
    parts = [
        f"**Log file:** `{filename}`",
        f"**Log time:** `{_format_timestamp(timestamp)}`",
    ]
    signal_client = _format_signal_client(client_info, source or "unresolved")
    if signal_client:
        parts.append(signal_client)
    parts.append(f"**Signal:** `{_shorten(message, 500)}`")
    return "\n" + "\n".join(parts)


async def _send_client_alert(title, description, *, color=discord.Color.orange(), ping=False):
    if NOTIFY_CHANNEL_ID is None:
        _record_monitor_error("Discord alerts", "NOTIFY_CHANNEL_ID is not configured")
        return
    channel = client.get_channel(NOTIFY_CHANNEL_ID)
    if channel is None:
        _record_monitor_error("Discord alerts", f"Channel {NOTIFY_CHANNEL_ID} was not found in the bot cache")
        return
    content = f"<@{PING_USER_ID}>" if ping and PING_USER_ID is not None else None
    embed = discord.Embed(title=title, description=description, color=color)
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="OSRS Monitor • client health")
    try:
        await channel.send(content=content, embed=embed)
    except Exception as exc:
        _record_monitor_error("Discord alerts", exc)


@tasks.loop(seconds=CLIENT_HEALTH_CHECK_INTERVAL_SECONDS)
async def monitor_client_health():
    """Detect a non-responsive OSRS client per PID without screen capture."""
    clients = _get_osrs_clients()
    # Window-title state is available even when a client is minimized. Keep the
    # PID login registry synchronized independently of log events.
    for info in clients:
        pid = info.get("pid")
        if pid is None:
            continue
    seen = set()

    for info in clients:
        pid = info["pid"]
        seen.add(pid)
        # A PID that was seen again is definitely alive.
        _client_closed_candidates.pop(pid, None)
        state = _client_health.setdefault(pid, {
            "hung_count": 0,
            "alerted": False,
            "closed_alerted": False,
            "last_response": None,
            "label": _client_label(info),
            "create_time": info.get("create_time"),
        })
        state["label"] = _client_label(info)
        state["create_time"] = info.get("create_time")

        # Keep a short-lived registry so /status can show a meaningful per-PID
        # state even after a client closes.
        title = ((info.get("window") or {}).get("title") or "OSRS client").strip()
        known = _known_clients.setdefault(pid, {})
        known.update({
            "pid": pid,
            "label": _client_label(info),
            "title": title,
            "create_time": info.get("create_time"),
            "last_seen": time.time(),
            "closed_at": None,
        })

        hwnd = (info.get("window") or {}).get("hwnd")
        response = _window_responds(hwnd)
        state["last_response"] = response

        if response is False:
            state["hung_count"] += 1
        elif response is True:
            state["hung_count"] = 0
            if state["alerted"]:
                await _send_client_alert(
                    "🟢 OSRS Client Responding Again",
                    ("The OSRS client is responding again." if not SHOW_TECHNICAL_DETAILS_IN_ALERTS else
                     f"**{_client_label(info)}** is responding again.\nWindow: `{_client_window_state(info)}`"),
                    color=discord.Color.green(),
                    ping=False,
                )
            state["alerted"] = False

        if state["hung_count"] >= HUNG_CONSECUTIVE_FAILURES and not state["alerted"]:
            state["alerted"] = True
            await _send_client_alert(
                "🚨 OSRS Client May Be Frozen",
                ("An OSRS client stopped responding to Windows.\n"
                 "The client process is still running, so it may be frozen rather than closed."
                 if not SHOW_TECHNICAL_DETAILS_IN_ALERTS else
                 f"**{_client_label(info)}** stopped responding to Windows.\n"
                 f"Window: `{_client_window_state(info)}`\n"
                 f"Checks failed: `{state['hung_count']}`\n"
                 f"The client process is still running, so it may be frozen rather than closed."),
                color=discord.Color.red(),
                ping=True,
            )

    # Detect individual client exits. We intentionally wait for two consecutive
    # checks (~30 seconds) before alerting, so a transient enumeration glitch
    # does not look like a real client shutdown.
    for pid in list(_client_health):
        if pid in seen:
            continue

        state = _client_health[pid]
        candidate = _client_closed_candidates.setdefault(pid, {
            "misses": 0,
            "label": state.get("label", f"PID {pid}"),
        })
        candidate["misses"] += 1

        if candidate["misses"] >= 2 and not state.get("closed_alerted", False):
            state["closed_alerted"] = True
            known = _known_clients.setdefault(pid, {})
            known["pid"] = pid
            known["label"] = candidate["label"]
            known["closed_at"] = time.time()
            known["last_seen"] = known.get("last_seen", time.time())
            known["title"] = known.get("title", candidate["label"])
            await _send_client_alert(
                "⚠️ OSRS Client Closed",
                ("An OSRS client is no longer running.\n"
                 "The other OSRS clients (if any) are still monitored separately."
                 if not SHOW_TECHNICAL_DETAILS_IN_ALERTS else
                 f"**{candidate['label']}** is no longer running.\n"
                 f"The other OSRS clients (if any) are still monitored separately."),
                color=discord.Color.orange(),
                ping=True,
            )
            _client_health.pop(pid, None)
            _client_closed_candidates.pop(pid, None)

    _record_monitor_ok("client health")


@monitor_client_health.before_loop
async def before_monitor_client_health():
    await client.wait_until_ready()


@monitor_client_health.error
async def monitor_client_health_error(error):
    _record_monitor_error("client health", error)
    await asyncio.sleep(2)
    if not monitor_client_health.is_running():
        monitor_client_health.restart()


# ---------------------------------------------------------------------------
# Windows Application Event Log crash/error detection
# ---------------------------------------------------------------------------


def _query_recent_windows_osrs_errors():
    """Return recent Application Error / WER events mentioning the OSRS client."""
    if os.name != "nt":
        return []

    seconds = max(30, int(WINDOWS_EVENT_LOOKBACK_SECONDS))
    ps_script = (
        "$events = Get-WinEvent -FilterHashtable @{LogName='Application'; "
        f"StartTime=(Get-Date).AddSeconds(-{seconds})}} -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Id -in 1000,1001 -or $_.ProviderName -match 'Application Error|Windows Error Reporting' } | "
        "Select-Object TimeCreated, Id, ProviderName, Message; "
        "$events | ConvertTo-Json -Compress -Depth 3"
    )

    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return []
        data = json.loads(completed.stdout)
        if isinstance(data, dict):
            data = [data]
        return data if isinstance(data, list) else []
    except Exception as exc:
        _record_monitor_error("Windows Event Log", exc)
        return []


@tasks.loop(seconds=WINDOWS_EVENT_CHECK_INTERVAL_SECONDS)
async def monitor_windows_event_log():
    """Alert on Windows application crash/error events associated with OSRS."""
    events = _query_recent_windows_osrs_errors()
    osrs_process_names = {"osclient.exe", "java.exe", "javaw.exe"}

    for event in events:
        message = str(event.get("Message") or "")
        lower = message.lower()
        if not any(name in lower for name in osrs_process_names):
            continue

        event_key = (
            str(event.get("TimeCreated")),
            str(event.get("Id")),
            str(event.get("ProviderName")),
            message[:500],
        )
        if event_key in _last_windows_event_keys:
            continue
        _last_windows_event_keys.append(event_key)

        provider = str(event.get("ProviderName") or "Windows Application")
        event_id = str(event.get("Id") or "?")
        time_text = str(event.get("TimeCreated") or "Unknown")
        short_message = _shorten(message, 1200)

        await _send_client_alert(
            "🪟 Windows OSRS Error Detected",
            f"Windows reported an application error related to an OSRS client.\n\n"
            f"**Provider:** `{provider}`\n"
            f"**Event ID:** `{event_id}`\n"
            f"**Time:** `{time_text}`\n"
            f"**Details:** {short_message}",
            color=discord.Color.red(),
            ping=True,
        )

    _record_monitor_ok("Windows Event Log")


@monitor_windows_event_log.before_loop
async def before_monitor_windows_event_log():
    await client.wait_until_ready()


@monitor_windows_event_log.error
async def monitor_windows_event_log_error(error):
    _record_monitor_error("Windows Event Log", error)
    await asyncio.sleep(2)
    if not monitor_windows_event_log.is_running():
        monitor_windows_event_log.restart()


# ---------------------------------------------------------------------------
# Extra log-based login/logout confirmation
# ---------------------------------------------------------------------------


def _classify_login_logout_signal(message):
    """Classify login/logout evidence without treating startup as a logout."""
    lower = message.lower()

    # Explicit logout/action signal. The live tests confirmed that
    # action=Logout is emitted for a real logout (and may appear twice for
    # one action). This is the primary notification signal.
    if "action=logout" in lower or "action: logout" in lower:
        return "logout", "strong"

    # "Logging out" / "logged out" are supporting messages only. They can be
    # emitted around the same logout and do not identify the client reliably.
    # Never let them trigger a notification or get mapped to an unused PID,
    # otherwise one real logout can look like two clients logged out.
    if "logging out" in lower or "logged out" in lower:
        return "logout_pending", "secondary"

    # LOGIN_SCREEN is deliberately only a state signal. The same line can be
    # emitted while a client is starting, so the state machine decides whether
    # it represents an actual logout transition.
    if (
        "game reached login_screen" in lower
        or "game reached login screen" in lower
        or "login_screen (state" in lower
        or "relog state=login_screen" in lower
        or "attempting enter-key relog" in lower
        or "welcome play widget" in lower
    ):
        return "login_screen", "strong"

    # Primary login signal confirmed by the live test: action=Play appears
    # after the user actually presses Play, not during normal client startup.
    if "action=play" in lower or "action: play" in lower:
        return "login", "strong"

    # Detuks can also confirm a successful relog/break cycle with this
    # message. Treat it as strong login evidence, because it is emitted after
    # the client has returned to the game rather than merely showing Play Now.
    if "logged back in, break cycle complete" in lower:
        return "login", "strong"

    # Other strong login evidence remains supported as a fallback.
    if (
        "relogged on world" in lower
        or "logged in on world" in lower
        or "successfully logged in" in lower
        or "login successful" in lower
        or "logged into world" in lower
        or "login complete" in lower
        or "login completed" in lower
        or "game reached in_game" in lower
        or "game reached in-game" in lower
    ):
        return "login", "strong"

    # Secondary evidence can establish the logged-in state without causing a
    # notification by itself. "Now on w303" is seen immediately after relog.
    if re.search(r"\bnow on w\d+\b", lower):
        return "login", "secondary"

    return None, None

def _is_logout_log_message(message):
    state, confidence = _classify_login_logout_signal(message)
    return state == "logout" and confidence == "strong"


def _is_login_success_log_message(message):
    state, confidence = _classify_login_logout_signal(message)
    return state == "login" and confidence == "strong"


def _signal_fingerprint(message):
    """Return a stable fingerprint for an exact repeated login/logout signal.

    Keep x/y in the fingerprint: if two clients emit genuinely different
    action coordinates at the same time, they remain eligible for separate
    PID mapping.
    """
    return re.sub(r"\s+", " ", message.strip().lower())


async def _handle_login_logout_log_event(timestamp, message, log_path=None):
    """Track login/logout state and associate strong signals with a live OSRS PID."""
    global _last_login_logout_signal, _action_event_batch

    # Keep a normalized copy available for the break-cycle duplicate check.
    lower = message.lower()

    key = str(log_path.resolve()) if log_path else "unknown"
    now = time.time()

    # Refresh login state from live client metadata first. This is deliberately
    # independent of screen capture and still works for minimized clients.
    _refresh_pid_login_states_from_client_health()
    _apply_persistent_state_to_live_clients()
    filename = log_path.name if log_path else "unknown log"
    state, confidence = _classify_login_logout_signal(message)
    if state is None:
        return

    # Supporting logout text is recorded for diagnostics/state visibility,
    # but is never resolved to a PID and never sends an alert. Only the
    # explicit action=Logout signal is allowed to create a logout event.
    if state == "logout_pending":
        _login_logout_debug_recent.append(
            (log_path, timestamp, state, confidence, message)
        )
        return

    history = _login_signal_history_by_log.setdefault(key, deque(maxlen=30))
    history.append((now, timestamp, state, confidence, message))

    # The OSRS client can emit the same action=Logout/action=Play line twice
    # for one real action. Never reinterpret that exact duplicate as a second
    # client event. This is especially important with two clients running: the
    # old "prefer an unused PID" logic could otherwise send a false logout for
    # the client that was still logged in. Different action coordinates remain
    # different fingerprints, so genuinely simultaneous client actions can
    # still be mapped separately.
    fingerprint = _signal_fingerprint(message)
    duplicate_pid = None
    duplicate_time = None
    with _action_event_lock:
        for event_time, event_state, event_fingerprint, event_pid in reversed(_recent_signal_fingerprints):
            if event_state != state:
                continue
            if now - event_time > DUPLICATE_SIGNAL_WINDOW_SECONDS:
                break
            if event_fingerprint == fingerprint and event_pid is not None:
                duplicate_pid = event_pid
                duplicate_time = event_time
                break

    if duplicate_pid is not None:
        # The first identical signal already handled the real state transition
        # and alert. Ignore this duplicate instead of remapping it to another
        # live client.
        _login_logout_debug_recent.append(
            (log_path, timestamp, state, confidence,
             f"{message} | PID={duplicate_pid} | duplicate signal ignored")
        )
        return

    # Resolve the event against a snapshot of the relevant client states taken
    # at the beginning of this short action burst. This is deliberately done
    # BEFORE the generic window/foreground resolver. A single real logout can
    # emit more than one action=Logout line; after the first line we must not
    # use the newly changed state to make the second line look like another
    # client's logout. At the same time, if two clients really act together,
    # both were in the candidate snapshot and can receive one event each.
    client_info = None
    client_source = None
    batch_now = time.time()
    with _action_event_lock:
        if (
            _action_event_batch.get("state") != state
            or batch_now - _action_event_batch.get("started", 0.0) > ACTION_BATCH_WINDOW_SECONDS
        ):
            live_clients = _get_osrs_clients()
            if state == "logout":
                candidates = [
                    info for info in live_clients
                    if _login_state_by_pid.get(info.get("pid"), "unknown") == "logged_in"
                ]
            else:
                candidates = [
                    info for info in live_clients
                    if _login_state_by_pid.get(info.get("pid"), "unknown") != "logged_in"
                ]
            _action_event_batch = {
                "state": state,
                "started": batch_now,
                "candidates": [info.get("pid") for info in candidates if info.get("pid") is not None],
                "assigned": set(),
            }
        candidate_pids = [
            pid for pid in _action_event_batch.get("candidates", [])
            if pid not in _action_event_batch.get("assigned", set())
        ]

    if len(candidate_pids) == 1:
        target_pid = candidate_pids[0]
        for info in _get_osrs_clients():
            if info.get("pid") == target_pid:
                client_info = info
                client_source = "pre-event client state"
                break
    elif len(candidate_pids) > 1:
        # There are multiple clients that were in the relevant state before the
        # burst. Use the existing resolver only to choose among those candidates.
        resolved_info, resolved_source = _resolve_signal_client(message)
        if resolved_info and resolved_info.get("pid") in candidate_pids:
            client_info = resolved_info
            client_source = f"{resolved_source} within pre-event candidates"
        else:
            # Prefer the foreground client only if it is one of the candidates.
            foreground_pid = _get_foreground_osrs_pid()
            for info in _get_osrs_clients():
                if info.get("pid") == foreground_pid and foreground_pid in candidate_pids:
                    client_info = info
                    client_source = "foreground within pre-event candidates"
                    break
    if client_info is not None:
        with _action_event_lock:
            _action_event_batch.setdefault("assigned", set()).add(client_info.get("pid"))

    # A break-cycle relog can emit two login lines close together:
    #   1) "Logged back in, break cycle complete"
    #   2) action=Play
    # The second line is confirmation for the same client, not a second login.
    # If the first line was mapped to a PID, reuse that PID for the following
    # action=Play so the duplicate cannot generate a second Discord alert.
    if client_info is None and state == "login" and "action=play" in lower:
        recent_break_pid = None
        recent_break_time = None
        for event_time, event_state, event_pid in reversed(_action_event_queue):
            if event_state != "login" or event_pid is None:
                continue
            if now - event_time > 5.0:
                break
            recent_break_pid = event_pid
            recent_break_time = event_time
            break
        if recent_break_pid is not None:
            for info in _get_osrs_clients():
                if info.get("pid") == recent_break_pid:
                    client_info = info
                    client_source = "recent break-cycle login -> same PID"
                    break

    # If the pre-event state snapshot did not give us a candidate, use the
    # normal resolver as a SECONDARY path. This is important on a fresh install
    # where no persistent state file exists yet, and for the single-client case.
    # The resolver itself is still conservative: with multiple clients and no
    # reliable state/coordinate/foreground match it returns None rather than
    # guessing.
    if client_info is None:
        resolved_info, resolved_source = _resolve_signal_client(message)
        if resolved_info is not None:
            # For multiple clients, only accept a resolver result when it has
            # a concrete non-ambiguous source. Never use the generic "first
            # unused" fallback for a multi-client logout/login.
            if len(_get_osrs_clients()) == 1:
                client_info = resolved_info
                client_source = f"{resolved_source} (fallback)"
            elif resolved_source in {
                "action x/y -> window",
                "action x/y -> unused window",
                "foreground window -> unused PID",
                "current logged-in state -> logout",
                "current non-logged-in state -> login",
            }:
                client_info = resolved_info
                client_source = f"{resolved_source} (fallback)"

    client_pid = client_info.get("pid") if client_info else None

    # With multiple clients, an unresolved event is safer to ignore than to
    # attribute it to the wrong account. With one live client, the resolver
    # above can safely identify that client.
    if client_pid is None and len(_get_osrs_clients()) > 1:
        _login_logout_debug_recent.append(
            (log_path, timestamp, state, confidence,
             f"{message} | unresolved: no safe client mapping")
        )
        return
    if client_pid is None:
        _login_logout_debug_recent.append(
            (log_path, timestamp, state, confidence,
             f"{message} | unresolved: no live client")
        )
        return

    with _action_event_lock:
        _recent_signal_fingerprints.append((now, state, fingerprint, client_pid))

    # Remember very recent action->PID assignments so simultaneous events are
    # less likely to collapse onto the same foreground client.
    with _action_event_lock:
        _action_event_queue.append((now, state, client_pid))

    debug_message = message
    if client_info:
        debug_message = (
            f"{message} | PID={client_pid} | "
            f"Title={((client_info.get('window') or {}).get('title') or 'OSRS client')}"
        )
    _login_logout_debug_recent.append(
        (path if (path := log_path) else None, timestamp, state, confidence, debug_message)
    )

    previous_state = (
        _login_state_by_pid.get(client_pid, "unknown")
        if client_pid is not None
        else _login_state_by_log.get(key, "unknown")
    )

    # Strong login/logout signals get PID-based state whenever possible.
    # This prevents two clients sharing client.log from sharing one state.
    if state in ("login", "logout") and client_pid is not None:
        if state == "logout":
            _login_state_by_pid[client_pid] = "login_screen"
            known = _known_clients.setdefault(client_pid, {})
            known["label"] = _client_display_name(client_info)
            known["persistent_state"] = "login_screen"
            known["last_state_source"] = "confirmed logout signal"
            _save_persistent_client_states()
            _client_last_login_logout_signal[client_pid] = {
                "state": "logout",
                "timestamp": timestamp,
                "message": message,
                "source": client_source,
                "title": ((client_info.get("window") or {}).get("title") or "OSRS client"),
            }
            _last_login_logout_signal = ("logout", timestamp, filename, debug_message)

            # A strong explicit action=Logout is itself enough to alert.
            # After a bot restart the exact pre-start state of a PID may be
            # unknown, especially when multiple clients share client.log.
            # Do not suppress a real logout merely because the runtime state
            # has not been observed yet.
            if previous_state not in ("logged_in", "unknown", "login_screen"):
                return

            last_alert = _last_logout_alert_at.get(("pid", client_pid))
            if last_alert is not None and now - last_alert <= LOGOUT_CONFIRM_WINDOW_SECONDS:
                return

            _last_logout_alert_at[("pid", client_pid)] = now
            _last_logout_log_event_at[("pid", client_pid)] = now
            await _send_client_alert(
                "🔐 OSRS Logout Detected",
            f"The OSRS logs confirmed that the client logged out."
            f"{_login_logout_alert_details(filename, timestamp, message, client_info, client_source)}",
            color=discord.Color.orange(),
            ping=True,
            )
            return

        _login_state_by_pid[client_pid] = "logged_in"
        known = _known_clients.setdefault(client_pid, {})
        known["label"] = _client_display_name(client_info)
        known["persistent_state"] = "logged_in"
        known["last_state_source"] = "confirmed login signal"
        _save_persistent_client_states()
        _client_last_login_logout_signal[client_pid] = {
            "state": "login",
            "timestamp": timestamp,
            "message": message,
            "source": client_source,
            "title": ((client_info.get("window") or {}).get("title") or "OSRS client"),
        }
        _last_login_logout_signal = ("login", timestamp, filename, debug_message)
        _last_login_log_event_at[("pid", client_pid)] = now

        # Strong login evidence may be the first signal seen after a bot
        # restart, so an unknown runtime state must still be allowed to alert.
        if previous_state not in ("login_screen", "unknown"):
            return

        last_alert = _last_login_alert_at.get(("pid", client_pid))
        if last_alert is not None and now - last_alert <= LOGOUT_CONFIRM_WINDOW_SECONDS:
            return

        _last_login_alert_at[("pid", client_pid)] = now
        await _send_client_alert(
            "🟢 OSRS Login Confirmed",
            f"The OSRS logs confirmed that the client returned to the game."
            f"{_login_logout_alert_details(filename, timestamp, message, client_info, client_source)}",
            color=discord.Color.green(),
            ping=False,
            )
        return

    # Fallback for signals that cannot be associated with a live PID.
    previous_state = _login_state_by_log.get(key, "unknown")

    if state == "login_screen":
        _login_state_by_log[key] = "login_screen"
        _last_login_logout_signal = ("login_screen", timestamp, filename, message)
        if previous_state != "logged_in":
            return
        last_alert = _last_logout_alert_at.get(key)
        if last_alert is not None and now - last_alert <= LOGOUT_CONFIRM_WINDOW_SECONDS:
            return
        _last_logout_alert_at[key] = now
        _last_logout_log_event_at[key] = now
        await _send_client_alert(
            "🔐 OSRS Logout Detected",
            f"The OSRS logs confirmed that the client logged out."
            f"{_login_logout_alert_details(filename, timestamp, message)}",
            color=discord.Color.orange(),
            ping=True,
            )
        return

    if state == "logout":
        _login_state_by_log[key] = "login_screen"
        _last_login_logout_signal = ("logout", timestamp, filename, message)
        _last_logout_log_event_at[key] = now
        if previous_state != "logged_in":
            return
        last_alert = _last_logout_alert_at.get(key)
        if last_alert is not None and now - last_alert <= LOGOUT_CONFIRM_WINDOW_SECONDS:
            return
        _last_logout_alert_at[key] = now
        await _send_client_alert(
            "🔐 OSRS Logout Detected",
            f"The OSRS logs confirmed that the client logged out."
            f"{_login_logout_alert_details(filename, timestamp, message)}",
            color=discord.Color.orange(),
            ping=True,
            )
        return

    if state == "login":
        _login_state_by_log[key] = "logged_in"
        _last_login_logout_signal = ("login", timestamp, filename, message)
        _last_login_log_event_at[key] = now
        if previous_state not in ("login_screen", "unknown"):
            return
        last_alert = _last_login_alert_at.get(key)
        if last_alert is not None and now - last_alert <= LOGOUT_CONFIRM_WINDOW_SECONDS:
            return
        _last_login_alert_at[key] = now
        await _send_client_alert(
            "🟢 OSRS Login Confirmed",
            f"The OSRS logs confirmed that the client returned to the game."
            f"{_login_logout_alert_details(filename, timestamp, message)}",
            color=discord.Color.green(),
            ping=False,
            )



def _bootstrap_login_states():
    """Read recent tails once to determine each log's current state, no alerts."""
    global _log_bootstrap_done
    if _log_bootstrap_done:
        return

    now = datetime.now()
    for path in _candidate_log_files():
        key = str(path.resolve())
        try:
            stat = path.stat()
            age_minutes = max(0.0, (time.time() - stat.st_mtime) / 60.0)
            # Old rotated logs are still monitored for future writes, but they
            # must not decide the current login state of a newly started bot.
            if age_minutes > LOG_STATE_STALE_MINUTES:
                _login_state_by_log[key] = "unknown"
                continue

            with path.open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(max(0, size - LOG_BOOTSTRAP_LOOKBACK_BYTES))
                raw = handle.read()
            text = raw.decode("utf-8", errors="replace")
            last_state = "unknown"
            last_time = None
            last_message = None
            for line in text.splitlines():
                ts = _parse_log_timestamp(line)
                msg = _log_message(line)
                state, confidence = _classify_login_logout_signal(msg)
                if state == "logout_pending":
                    continue
                if state == "login_screen":
                    last_state = "login_screen"
                elif state == "logout":
                    last_state = "login_screen"
                elif state == "login":
                    last_state = "logged_in"
                if state in ("login_screen", "logout", "login"):
                    last_time = ts
                    last_message = msg

            _login_state_by_log[key] = last_state
            if last_message:
                display_state = "login" if last_state == "logged_in" else last_state
                _last_login_logout_signal = (display_state, last_time, path.name, last_message)
        except (OSError, UnicodeError) as exc:
            _record_monitor_error("log bootstrap", exc)

    _log_bootstrap_done = True


def _log_scan_summary():
    """Return a compact recursive inventory for the /logscan command."""
    results = []
    # Keep /logscan fast: inspect only the newest 20 likely log files and
    # only a small tail of each. The recursive inventory itself remains broad.
    for path in _candidate_log_files()[:20]:
        key = str(path.resolve())
        try:
            stat = path.stat()
            size = stat.st_size
            age_minutes = max(0.0, (time.time() - stat.st_mtime) / 60.0)
            counts = {
                "login_screen": 0, "login": 0, "logout": 0,
                "logout_pending": 0, "task": 0, "error": 0,
            }
            with path.open("rb") as handle:
                handle.seek(0, 2)
                total = handle.tell()
                handle.seek(max(0, total - min(total, 256 * 1024)))
                text = handle.read().decode("utf-8", errors="replace")
            for line in text.splitlines():
                msg = _log_message(line)
                state, _confidence = _classify_login_logout_signal(msg)
                if state:
                    counts[state] = counts.get(state, 0) + 1
                if "new task" in msg.lower() or "task is " in msg.lower():
                    counts["task"] += 1
                if any(word in msg.lower() for word in ("error", "exception", "failed", "crash", "timeout")):
                    counts["error"] += 1
            results.append({
                "path": path, "size": size, "age": age_minutes,
                "state": _login_state_by_log.get(key, "unknown"),
                "counts": counts,
            })
        except OSError:
            continue
    return results


# ---------------------------------------------------------------------------
# OCR login/logout detection
# ---------------------------------------------------------------------------


def is_login_screen_visible_by_pixel() -> bool:
    try:
        import pytesseract
    except ImportError:
        print("Login detection: install pytesseract first.")
        return False

    if not pytesseract.pytesseract.tesseract_cmd or pytesseract.pytesseract.tesseract_cmd == "tesseract":
        for candidate in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if os.path.exists(candidate):
                pytesseract.pytesseract.tesseract_cmd = candidate
                break

    try:
        screenshot = ImageGrab.grab().convert("RGB")
        frame = np.array(screenshot)
    except Exception:
        return False

    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    variants = []

    for scale in (1.5, 2.0):
        resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        variants.append(resized)
        variants.append(cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])

    for image in variants:
        try:
            text = pytesseract.image_to_string(image, config="--oem 3 --psm 11").lower()
        except Exception as exc:
            print(f"Login OCR error: {exc}")
            return False

        compact = text.replace(" ", "")
        has_play = (("play" in text and "now" in text) or "playnow" in compact or "play-now" in text)
        has_welcome = "welcome" in text or "welcom" in text
        has_osrs_title = (("old" in text and "school" in text) or "runescape" in compact)

        if has_play and has_welcome and has_osrs_title:
            return True

    return False


# ---------------------------------------------------------------------------
# Log file discovery / tailing
# ---------------------------------------------------------------------------


def _candidate_log_files():
    """Discover log files recursively anywhere under .detuksosrs."""
    found = {}
    try:
        if not LOG_ROOT_DIRECTORY.exists():
            return []

        # v14 deliberately scans the complete .detuksosrs tree. We do not
        # assume that every client/version stores its useful logs in the same
        # subdirectory or uses the same filename.
        # Only inspect likely log files. Avoid walking/reading every cache,
        # plugin, profile and data file in a large .detuksosrs installation.
        for path in LOG_ROOT_DIRECTORY.rglob("*.log*"):
            if path.is_file():
                found[str(path.resolve())] = path
        # A few Detuks files may not have a .log suffix but use a detuks/client
        # prefix; include those as well without scanning arbitrary filenames.
        for pattern in ("detuks*", "client*"):
            for path in LOG_ROOT_DIRECTORY.rglob(pattern):
                if path.is_file() and (".log" in path.name.lower() or path.name.lower().startswith(("detuks", "client"))):
                    found[str(path.resolve())] = path

        return sorted(found.values(), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception as exc:
        _record_monitor_error("logs", exc)
        return []

def _find_active_log():
    files = _candidate_log_files()
    if not files:
        return None
    return files[0]


def _switch_log_file(path: Path, start_at_end=True):
    global _log_current_file, _log_current_position, _log_partial_line

    _log_current_file = path
    _log_partial_line = ""

    try:
        _log_current_position = path.stat().st_size if start_at_end else 0
        _record_monitor_ok("logs")
    except Exception as exc:
        _log_current_position = 0
        _record_monitor_error("logs", exc)


def _read_one_log_file(path: Path):
    """Read only newly appended complete lines from one log file."""
    key = str(path.resolve())
    try:
        stat = path.stat()
        size = stat.st_size
        identity = (getattr(stat, "st_ino", 0), stat.st_mtime_ns, size)
    except OSError:
        return []

    if key not in _log_file_positions:
        # Start at EOF on first discovery so old events are never replayed.
        _log_file_positions[key] = size
        _log_file_partials[key] = ""
        _log_file_identities[key] = identity
        return []

    position = _log_file_positions[key]
    previous_identity = _log_file_identities.get(key)

    # Handle rotation/recreation even when the replacement file is larger.
    if previous_identity and previous_identity[0] and identity[0] and previous_identity[0] != identity[0]:
        position = 0
        _log_file_partials[key] = ""
    elif size < position:
        position = 0
        _log_file_partials[key] = ""

    _log_file_identities[key] = identity
    partial = _log_file_partials.get(key, "")

    if size < position:
        # Log was truncated/recreated.
        position = 0
        partial = ""

    if size == position:
        return []

    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(position)
            chunk = handle.read()
            _log_file_positions[key] = handle.tell()
    except (OSError, UnicodeError) as exc:
        _record_monitor_error("logs", exc)
        return []

    data = partial + chunk
    parts = data.splitlines(keepends=True)
    lines = []
    partial = ""

    for part in parts:
        if part.endswith(("\n", "\r")):
            lines.append(part.rstrip("\r\n"))
        else:
            partial = part

    _log_file_partials[key] = partial
    return [(path, line) for line in lines if line.strip()]


def _read_new_log_lines():
    """Tail ALL client*.log files, not only the newest one."""
    files = _candidate_log_files()
    if not files:
        return []

    results = []
    for path in files:
        results.extend(_read_one_log_file(path))

    # Preserve chronological processing as far as timestamps are available.
    results.sort(key=lambda item: _parse_log_timestamp(item[1]) or datetime.min)
    return results


# ---------------------------------------------------------------------------
# Task parsing
# ---------------------------------------------------------------------------


def _extract_failure_reason(message):
    lower = message.lower()

    if "can't do this slayer task" in lower:
        return "Slayer task cannot be done with the current requirements"

    if "failed for the reasons above" in lower:
        return _shorten(message)

    if "failed to traverse last mile" in lower:
        return "Could not reach the destination"

    if "i can't reach that" in lower:
        return "Could not reach the destination"

    if "resource check failed" in lower:
        return _shorten(message)

    if "something is missing - skipping withdraw" in lower:
        return "Required resources were missing"

    if "one or more requirements are missing" in lower:
        return _shorten(message)

    if "no combat styles available" in lower:
        return "No suitable combat style available"

    if "able to start: false" in lower:
        return "Task could not be started"

    return None


def _choose_failure_reason_for_log(log_key):
    failures = _log_failure_reasons_by_log.get(log_key, ())
    if not failures:
        return None
    priority_words = (
        "can't do this slayer task", "could not reach", "slayer task cannot",
        "requirements", "no suitable combat style", "resource check", "required resources",
    )
    for reason, _timestamp in reversed(failures):
        if any(word in reason.lower() for word in priority_words):
            return reason
    return failures[-1][0]


def _parse_selected_task(message):
    # Example:
    # Selected Slayer / Turael / Turael for about 12 minutes
    # Selected Exploring / Noobishly / Gielinor for about 7 minutes
    match = re.search(r"Selected\s+(.+?)\s+for about\s+([0-9]+(?:\.[0-9]+)?)\s+minutes", message, re.IGNORECASE)
    if not match:
        return None

    route = [part.strip() for part in match.group(1).split("/")]
    duration = float(match.group(2))
    task = route[0] if route else None
    activity = route[1] if len(route) >= 2 else None
    location = route[2] if len(route) >= 3 else None

    return {
        "task": task,
        "activity": activity,
        "location": location,
        "duration_minutes": duration,
    }


async def _send_task_embed(*, event_time, task, activity=None, location=None,
                     duration_minutes=None, previous_task=None,
                     previous_end_reason=None, skipped_reason=None,
                     break_length_hours=None, next_play_hours=None,
                     log_file=None):
    if TASK_NOTIFY_CHANNEL_ID is None:
        return None

    channel = client.get_channel(TASK_NOTIFY_CHANNEL_ID)
    if channel is None:
        return None

    embed = discord.Embed(
        title="📋 Task Update",
        color=discord.Color.blurple(),
    )

    embed.add_field(name="Account", value="—", inline=False)
    embed.add_field(name="Task", value=task or "Unknown", inline=False)

    if activity:
        embed.add_field(name="Activity", value=activity, inline=False)
    if location:
        embed.add_field(name="Location", value=location, inline=False)
    if duration_minutes is not None:
        embed.add_field(name="Duration", value=_format_minutes(duration_minutes), inline=True)
        if event_time:
            end_time = event_time + timedelta(minutes=duration_minutes)
            embed.add_field(name="Expected End", value=_format_timestamp(end_time), inline=True)

    if previous_task and previous_end_reason:
        embed.add_field(
            name="Previous Task",
            value=f"{previous_task}\nEnded: {previous_end_reason}",
            inline=False,
        )

    if skipped_reason:
        embed.add_field(name="Reason", value=_shorten(skipped_reason), inline=False)

    if next_play_hours is not None or break_length_hours is not None:
        schedule_lines = []
        if next_play_hours is not None:
            schedule_lines.append(f"Next play: {_format_duration_hours(next_play_hours)}")
        if break_length_hours is not None:
            schedule_lines.append(f"Next break: {_format_duration_hours(break_length_hours)}")
        embed.add_field(name="Session Schedule", value="\n".join(schedule_lines), inline=False)

    embed.set_footer(text="OSRS Monitor" if not SHOW_TECHNICAL_DETAILS_IN_ALERTS else f"OSRS Monitor • {log_file or 'log'}")
    if event_time:
        # Discord expects an aware datetime. Use UTC for the embed timestamp;
        # the visible task time above is taken directly from the log.
        embed.timestamp = discord.utils.utcnow()

    await channel.send(embed=embed)


async def _send_level_up_embed(*, event_time, skill=None, new_level=None, total_level=None, log_file=None):
    """Send a level-up event to the dedicated task channel."""
    target_channel_id = LEVEL_NOTIFY_CHANNEL_ID or TASK_NOTIFY_CHANNEL_ID
    if target_channel_id is None:
        return None

    channel = client.get_channel(target_channel_id)
    if channel is None:
        return None

    if total_level is not None:
        title = "🏆 Total Level Up"
        embed = discord.Embed(title=title, color=discord.Color.gold())
        embed.add_field(name="Total Level", value=str(total_level), inline=False)
    else:
        title = "🎉 Level Up"
        embed = discord.Embed(title=title, color=discord.Color.green())
        embed.add_field(name="Skill", value=skill or "Unknown", inline=True)
        embed.add_field(name="New Level", value=str(new_level) if new_level is not None else "Unknown", inline=True)

    if event_time:
        embed.add_field(name="Time", value=_format_timestamp(event_time), inline=False)

    embed.set_footer(text="OSRS Monitor" if not SHOW_TECHNICAL_DETAILS_IN_ALERTS else f"OSRS Monitor • {log_file or 'log'}")
    embed.timestamp = discord.utils.utcnow()
    await channel.send(embed=embed)


async def _handle_log_line(line, log_path=None):
    """Process one new line, keeping task state isolated per log file."""
    global _current_task, _current_task_started, _current_task_duration_minutes
    global _current_task_activity, _current_task_location, _current_task_last_log_file
    global _current_task_last_update, _next_play_length_hours, _next_break_length_hours

    timestamp = _parse_log_timestamp(line)
    message = _log_message(line)
    _log_recent_lines.append((timestamp, message))

    await _handle_login_logout_log_event(timestamp, message, log_path)

    # Task/resource parsing belongs to the bot/client logs under .detuksosrs\logs.
    # Detuks root logs are used primarily for client/login state and diagnostics.
    is_task_log = log_path is not None and str(log_path.resolve()).lower().startswith(str(LOG_DIRECTORY.resolve()).lower())

    # Identify which log owns this state. This prevents multiple clients/logs
    # from mixing their task descriptions and failure reasons.
    log_key = str(log_path.resolve()) if log_path else "unknown"
    log_name = log_path.name if log_path else "unknown log"
    pending = _log_pending_tasks.get(log_key)
    failures = _log_failure_reasons_by_log.setdefault(log_key, deque(maxlen=50))

    match = re.search(r"Next play length\s+([0-9]+(?:\.[0-9]+)?)h", message, re.IGNORECASE)
    if match:
        _next_play_length_hours = float(match.group(1))

    match = re.search(r"Next break length\s+([0-9]+(?:\.[0-9]+)?)h", message, re.IGNORECASE)
    if match:
        _next_break_length_hours = float(match.group(1))

    level_match = re.search(
        r"Congratulations, you(?:'|’)ve just advanced your (.+?) level\. You are now level (\d+)\.",
        message, re.IGNORECASE,
    )
    total_match = re.search(
        r"Congratulations, you(?:'|’)ve reached a total level of (\d+)\.",
        message, re.IGNORECASE,
    )

    if level_match or total_match:
        event_key = None
        if level_match:
            skill = level_match.group(1).strip()
            new_level = int(level_match.group(2))
            event_key = (timestamp, "skill", skill.lower(), new_level)
            if event_key != _log_last_level_event_key:
                _log_last_level_event_key = event_key
                await _send_level_up_embed(event_time=timestamp, skill=skill, new_level=new_level, log_file=log_name)
        else:
            total_level = int(total_match.group(1))
            event_key = (timestamp, "total", total_level)
            if event_key != _log_last_level_event_key:
                _log_last_level_event_key = event_key
                await _send_level_up_embed(event_time=timestamp, total_level=total_level, log_file=log_name)

    if not is_task_log:
        return

    failure = _extract_failure_reason(message)
    if failure:
        failures.append((failure, timestamp))

    if "Time up" in message and pending:
        pending["last_update"] = timestamp or datetime.now()

    if "NEW TASK" in message.upper():
        _log_pending_tasks[log_key] = {
            "timestamp": timestamp or datetime.now(),
            "task": None,
            "activity": None,
            "location": None,
            "duration_minutes": None,
            "failure_reason": _choose_failure_reason_for_log(log_key),
            "log_file": log_name,
        }
        failures.clear()
        return

    pending = _log_pending_tasks.get(log_key)
    if pending is None:
        return

    match = re.search(r"Task is\s+(.+)$", message, re.IGNORECASE)
    if match:
        pending["task"] = match.group(1).strip()

    match = re.search(r"Activity is\s+(.+)$", message, re.IGNORECASE)
    if match:
        pending["activity"] = match.group(1).strip()

    match = re.search(r"Location is\s+(.+)$", message, re.IGNORECASE)
    if match:
        pending["location"] = match.group(1).strip()

    selected = _parse_selected_task(message)
    if selected:
        pending.update(selected)

    enough = pending["task"] is not None and (
        pending["duration_minutes"] is not None or pending["activity"] is not None
    )
    if not enough:
        return

    event_key = (
        log_key, pending["timestamp"], pending["task"], pending["activity"],
        pending["location"], pending["duration_minutes"],
    )
    if event_key == _log_last_task_event_keys.get(log_key):
        return

    previous_task = _current_task if _current_task_last_log_file == log_name else None
    previous_end_reason = None
    if previous_task and "Time up" in " ".join(msg for _ts, msg in list(_log_recent_lines)[-8:]):
        previous_end_reason = "Time up"

    _current_task = pending["task"]
    _current_task_started = pending["timestamp"]
    _current_task_duration_minutes = pending["duration_minutes"]
    _current_task_activity = pending["activity"]
    _current_task_location = pending["location"]
    _current_task_last_log_file = log_name
    _current_task_last_update = timestamp or pending["timestamp"]
    _log_last_task_event_keys[log_key] = event_key

    skipped_reason = pending["failure_reason"]
    if skipped_reason and previous_task:
        previous_end_reason = skipped_reason

    await _send_task_embed(
        event_time=pending["timestamp"],
        task=pending["task"],
        activity=pending["activity"],
        location=pending["location"],
        duration_minutes=pending["duration_minutes"],
        previous_task=previous_task,
        previous_end_reason=previous_end_reason,
        skipped_reason=skipped_reason,
        next_play_hours=_next_play_length_hours,
        break_length_hours=_next_break_length_hours,
        log_file=log_name,
    )
    _log_pending_tasks.pop(log_key, None)


@tasks.loop(seconds=LOG_CHECK_INTERVAL_SECONDS)
async def monitor_log_file():
    try:
        lines = _read_new_log_lines()
        for log_path, line in lines:
            await _handle_log_line(line, log_path)
        _record_monitor_ok("logs")
    except Exception as exc:
        _record_monitor_error("logs", exc)


@monitor_log_file.before_loop
async def before_monitor_log_file():
    await client.wait_until_ready()


@monitor_log_file.error
async def monitor_log_file_error(error):
    _record_monitor_error("logs", error)
    await asyncio.sleep(2)
    if not monitor_log_file.is_running():
        monitor_log_file.restart()


# ---------------------------------------------------------------------------
# Process stop monitor
# ---------------------------------------------------------------------------


@tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
async def monitor_process():
    global _process_was_running, _osrs_state

    if NOTIFY_CHANNEL_ID is None:
        return

    running = is_process_running(PROCESS_NAME)

    if running:
        _osrs_state = "logged out" if _last_login_detection is True else "in-game"
    elif _osrs_state == "in-game":
        _osrs_state = "logged out"

    if _process_was_running is True and running is False:
        channel = client.get_channel(NOTIFY_CHANNEL_ID)
        if channel is not None:
            ping = f"<@{PING_USER_ID}> " if PING_USER_ID is not None else ""
            message = f"{ping}⚠️ **{PROCESS_NAME}** has stopped — you have been logged out of OSRS!"
            try:
                screenshot = ImageGrab.grab()
                buffer = io.BytesIO()
                screenshot.save(buffer, format="PNG")
                buffer.seek(0)
                await channel.send(
                    content=message,
                    file=discord.File(buffer, filename="logout_screenshot.png"),
                )
            except Exception as exc:
                await channel.send(f"{message}\n(Could not take a screenshot: {exc})")

    _process_was_running = running


@monitor_process.before_loop
async def before_monitor_process():
    await client.wait_until_ready()


@monitor_process.error
async def monitor_process_error(error):
    _record_monitor_error("process", error)
    await asyncio.sleep(2)
    if not monitor_process.is_running():
        monitor_process.restart()


# ---------------------------------------------------------------------------
# Login OCR monitor
# ---------------------------------------------------------------------------


@tasks.loop(seconds=LOGIN_SCREEN_CHECK_INTERVAL_SECONDS)
async def monitor_login_screen_pixel():
    global _login_pixel_was_visible, _last_login_detection, _last_login_detection_at, _osrs_state

    if NOTIFY_CHANNEL_ID is None:
        return

    visible = is_login_screen_visible_by_pixel()
    _last_login_detection = visible
    _last_login_detection_at = time.time()
    _osrs_state = "logged out" if visible else ("in-game" if is_process_running(PROCESS_NAME) else "unknown")

    if _login_pixel_was_visible is False and visible is True:
        channel = client.get_channel(NOTIFY_CHANNEL_ID)
        if channel is not None:
            ping = f"<@{PING_USER_ID}> " if PING_USER_ID is not None else ""
            message = f"{ping}🔑 Login screen detected — you have been logged out of OSRS!"
            try:
                screenshot = ImageGrab.grab()
                buffer = io.BytesIO()
                screenshot.save(buffer, format="PNG")
                buffer.seek(0)
                await channel.send(
                    content=message,
                    file=discord.File(buffer, filename="logout_screenshot.png"),
                )
            except Exception as exc:
                await channel.send(f"{message}\n(Could not take a screenshot: {exc})")

    _login_pixel_was_visible = visible


@monitor_login_screen_pixel.before_loop
async def before_monitor_login_screen_pixel():
    await client.wait_until_ready()


@monitor_login_screen_pixel.error
async def monitor_login_screen_pixel_error(error):
    _record_monitor_error("login OCR", error)
    await asyncio.sleep(2)
    if not monitor_login_screen_pixel.is_running():
        monitor_login_screen_pixel.restart()


# ---------------------------------------------------------------------------
# Periodic screenshot
# ---------------------------------------------------------------------------


@tasks.loop(minutes=PERIODIC_SCREENSHOT_INTERVAL_MINUTES or 30)
async def periodic_screenshot():
    if PERIODIC_SCREENSHOT_INTERVAL_MINUTES is None or NOTIFY_CHANNEL_ID is None:
        return

    channel = client.get_channel(NOTIFY_CHANNEL_ID)
    if channel is None:
        return

    try:
        screenshot = ImageGrab.grab()
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        buffer.seek(0)
        await channel.send(
            content="🖥️ Periodic Check-in:",
            file=discord.File(buffer, filename="periodic_screenshot.png"),
        )
    except Exception as exc:
        await channel.send(f"Could not take periodic screenshot: {exc}")


@periodic_screenshot.before_loop
async def before_periodic_screenshot():
    await client.wait_until_ready()


@periodic_screenshot.error
async def periodic_screenshot_error(error):
    _record_monitor_error("periodic screenshot", error)
    await asyncio.sleep(2)
    if not periodic_screenshot.is_running():
        periodic_screenshot.restart()


# ---------------------------------------------------------------------------
# Discord bot and slash commands
# ---------------------------------------------------------------------------


intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


async def owner_only(interaction: discord.Interaction) -> bool:
    if BOT_OWNER_ID is not None and interaction.user.id == BOT_OWNER_ID:
        return True

    if not interaction.response.is_done():
        await interaction.response.send_message(
            "⛔ Only the owner of this bot can use this command.",
            ephemeral=True,
        )
    return False


# Apply the owner-only check to every slash command below.


@client.event
async def on_ready():
    global BOT_OWNER_ID

    try:
        app_info = await client.application_info()
        if app_info.owner is not None:
            BOT_OWNER_ID = app_info.owner.id
            print(f"Bot owner loaded: {app_info.owner}")
    except Exception as exc:
        print(f"Could not get bot owner: {exc}")

    global _COMMANDS_SYNCED

    if not _COMMANDS_SYNCED:
        # Publish slash commands ONLY to connected guilds.
        # First remove any old global registrations. Discord can keep old
        # global commands around from previous builds, so the cleanup is
        # performed before the guild-only registrations are synchronized.
        # Keep a copy of the current command objects before clearing globals.
        commands_for_guilds = list(tree.get_commands())

        try:
            tree.clear_commands(guild=None)
            await tree.sync()
            print("Global slash commands removed.")
        except Exception as exc:
            print(f"Global slash-command cleanup failed: {exc}")

        for guild in client.guilds:
            try:
                # Remove any previous guild command set, then publish exactly
                # the current command list to this guild.
                tree.clear_commands(guild=guild)
                for command in commands_for_guilds:
                    tree.add_command(command, guild=guild, override=True)
                await tree.sync(guild=guild)
                print(f"Guild slash commands synchronized: {guild.name} ({guild.id})")
            except Exception as exc:
                print(f"Guild slash-command sync failed for {guild.name} ({guild.id}): {exc}")

        _COMMANDS_SYNCED = True

    print(f"Logged in as {client.user} — guild-only slash commands synchronized.")

    _load_persistent_client_states()
    _apply_persistent_state_to_live_clients()
    _bootstrap_login_states()

    if not monitor_process.is_running():
        monitor_process.start()
    if not monitor_client_health.is_running():
        monitor_client_health.start()
    if not monitor_windows_event_log.is_running():
        monitor_windows_event_log.start()
    # Automatic full-screen OCR is intentionally disabled.
    # /loginpixelstatus remains available as a manual fallback.
    if not periodic_screenshot.is_running():
        periodic_screenshot.start()
    if not monitor_log_file.is_running():
        monitor_log_file.start()


@tree.command(name="help", description="Show the available OSRS Monitor commands")
@app_commands.check(owner_only)
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="OSRS Discord Monitor — Commands",
        description="Commands for monitoring and troubleshooting. All commands are owner-only.",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Main commands",
        value=(
            "`/status` — overall bot and OSRS client status\n"
            "`/screenshot` — take a screenshot of the monitored PC\n"
            "`/resources` — show CPU and RAM usage\n"
            "`/bugreport` — create a support ZIP for bot/monitor errors\n"
            "`/clear` — delete 1–50 messages from the current channel"
        ),
        inline=False,
    )
    embed.add_field(
        name="Client & diagnostics",
        value=(
            "`/clienthealth` — check OSRS clients and Windows responsiveness\n"
            "`/clientmap` — show PID-to-client mappings\n"
            "`/clientevents` — show recent login/logout mappings\n"
            "`/logincheck` — manually check the login screen\n"
            "`/logstatus` — show log monitoring status\n"
            "`/logscan` — scan the Detuks logs\n"
            "`/logdebug` — show live log changes\n"
            "`/launcherscan` — inspect the Jagex Launcher files"
        ),
        inline=False,
    )
    embed.set_footer(text="Developed by Bas | Razor • V24.1")
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="bugreport", description="Create a support package for bot or monitoring errors")
@app_commands.check(owner_only)
async def bugreport(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if support_report is None:
        await interaction.followup.send(
            "❌ The support package module could not be loaded.",
            ephemeral=True,
        )
        return

    try:
        diagnostics = [
            "OSRS Discord Monitor runtime diagnostics",
            f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "Monitor errors:",
        ]
        if _monitor_errors:
            diagnostics.extend(f"- {name}: {error}" for name, error in _monitor_errors.items())
        else:
            diagnostics.append("- None currently recorded")

        diagnostics.extend([
            "",
            "Recent login/logout signal:",
            str(_last_login_logout_signal) if _last_login_logout_signal else "None",
            "",
            "Recent log lines:",
            *list(_log_recent_lines)[-40:],
        ])

        zip_path = await asyncio.to_thread(
            support_report.build_package,
            "\n".join(diagnostics),
        )

        size = zip_path.stat().st_size
        if size > 24 * 1024 * 1024:
            await interaction.followup.send(
                "⚠️ Support package was created, but it is too large to upload to Discord. "
                f"Saved locally at: `{zip_path}`",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "🛠️ **Support package created.**\n"
            "This ZIP is intended for diagnosing OSRS Discord Monitor / bot errors. "
            "It does not include the Discord bot token. Review the logs before sharing them.",
            file=discord.File(str(zip_path), filename=zip_path.name),
            ephemeral=True,
        )
    except Exception as exc:
        await interaction.followup.send(
            f"❌ Could not create the support package: `{str(exc)[:500]}`",
            ephemeral=True,
        )


@tree.command(name="screenshot", description="Take a screenshot of the monitored PC")
@app_commands.check(owner_only)
async def ss(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        screenshot = ImageGrab.grab()
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        buffer.seek(0)
        embed = discord.Embed(
            title="📸 Screenshot",
            description="Live screenshot of the monitored PC.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="OSRS Monitor • /screenshot")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(
            embed=embed,
            file=discord.File(buffer, filename="screenshot.png"),
        )
    except Exception as exc:
        await interaction.followup.send(
            embed=discord.Embed(
                title="❌ Screenshot Failed",
                description=f"`{str(exc)[:500]}`",
                color=discord.Color.red(),
            )
        )


@tree.command(name="status", description="View the status of OSRS and all monitors")
@app_commands.check(owner_only)
async def status(interaction: discord.Interaction):
    await interaction.response.defer()

    running = is_process_running(PROCESS_NAME)
    clients = _get_osrs_clients()

    # Do not equate "osclient.exe is running" with "the game is in-game".
    # The client also runs while sitting on the Play Now/login screen.
    pid_states = [_login_state_by_pid.get(info["pid"], "unknown") for info in clients]
    if not clients:
        osrs_status = "⚪ Not Active"
    elif any(state == "logged_in" for state in pid_states):
        osrs_status = "🟢 In-game (at least one client)"
    elif all(state == "login_screen" for state in pid_states):
        osrs_status = "🔴 Login / Play Now screen"
    elif any(state == "login_screen" for state in pid_states):
        osrs_status = "🟠 Mixed client states"
    else:
        osrs_status = "⚪ Client state unknown"

    if _last_login_logout_signal and _last_login_logout_signal[0] == "logout":
        login_status = "🔴 Logout / Login Screen Signal"
    elif _last_login_logout_signal and _last_login_logout_signal[0] == "login":
        login_status = "🟢 Login Confirmed"
    else:
        login_status = "⚪ No Log Signal Yet"

    task_text = _current_task or "Not read yet"
    task_started = _format_timestamp(_current_task_started)
    task_duration = _format_minutes(_current_task_duration_minutes)

    if _monitor_errors:
        monitor_status = "🟠 Problems Detected"
        error_text = "\n".join(
            f"• **{name}:** `{error[:140]}`" for name, error in _monitor_errors.items()
        )
        embed_color = discord.Color.orange()
    else:
        monitor_status = "🟢 All monitors operational"
        error_text = "No monitor errors found."
        embed_color = discord.Color.green()

    log_name = _log_current_file.name if _log_current_file else "No log found"

    # Build a per-client status list. Current clients come first; recently
    # closed clients remain visible for a short period so the status page can
    # tell exactly which PID disappeared.
    now = time.time()
    current_pids = set()
    client_lines = []
    for info in clients:
        pid = info["pid"]
        current_pids.add(pid)
        health = _client_health.get(pid, {})
        response = health.get("last_response")
        response_text = "responsive" if response is True else "not responding" if response is False else "not checked"
        state = _login_state_by_pid.get(pid, "unknown")
        if response is False and health.get("hung_count", 0) >= HUNG_CONSECUTIVE_FAILURES:
            state_text = "🚨 Frozen / not responding"
        elif state == "logged_in":
            state_text = "🟢 Logged in"
        elif state == "login_screen":
            state_text = "🔴 Play Now / Login"
        else:
            state_text = "⚪ Unknown"
        title = ((info.get("window") or {}).get("title") or "OSRS client").strip()
        if len(title) > 45:
            title = title[:42] + "..."
        client_lines.append(
            f"• PID `{pid}` — **{state_text}** — {_client_window_state(info)} — {response_text}\n"
            f"  `{title}`"
        )

    # Keep recently closed clients visible for up to one hour.
    for pid, known in list(_known_clients.items()):
        if pid in current_pids:
            continue
        closed_at = known.get("closed_at")
        if closed_at is None or now - closed_at > KNOWN_CLIENT_RETENTION_SECONDS:
            if closed_at is not None:
                _known_clients.pop(pid, None)
            continue
        label = (known.get("label") or "OSRS client").strip()
        title = (known.get("title") or "OSRS client").strip()
        if len(title) > 45:
            title = title[:42] + "..."
        closed_when = _format_timestamp(datetime.fromtimestamp(closed_at))
        client_lines.append(
            f"• PID `{pid}` — **⚫ Closed** — closed `{closed_when}`\n"
            f"  `{title}` — `{label}`"
        )

    client_status = "\n".join(client_lines) if client_lines else "No `osclient.exe` clients found."

    embed = discord.Embed(
        title="🎮 OSRS Monitor",
        description="Current monitoring status.",
        color=embed_color,
    )
    embed.add_field(name="🖥️ OSRS", value=f"**Status:** {osrs_status}\n**Client:** `{PROCESS_NAME}`", inline=True)
    embed.add_field(name="🔐 Login", value=login_status, inline=True)
    embed.add_field(name="📋 Current Task", value=f"`{task_text}`", inline=False)
    embed.add_field(name="🎯 Activity", value=f"`{_current_task_activity or '—'}`", inline=True)
    embed.add_field(name="📍 Location", value=f"`{_current_task_location or '—'}`", inline=True)
    embed.add_field(name="⏱️ Task Start", value=f"`{task_started}`", inline=True)
    embed.add_field(name="⌛ Task Duration", value=f"`{task_duration}`", inline=True)
    embed.add_field(name="📄 Active log", value=f"`{log_name}`", inline=False)
    embed.add_field(name="🧩 OSRS Clients", value=client_status, inline=False)
    embed.add_field(
        name="🕒 Session Schedule",
        value=(
            f"Next play: `{_format_duration_hours(_next_play_length_hours)}`\n"
            f"Next break: `{_format_duration_hours(_next_break_length_hours)}`"
        ),
        inline=False,
    )
    embed.add_field(name="🛡️ Monitors", value=monitor_status, inline=True)
    embed.add_field(name="🔎 Errors", value=error_text, inline=False)
    embed.set_footer(text=f"OSRS Monitor • /status • {_format_timestamp(datetime.now())}")

    await interaction.followup.send(embed=embed)


@tree.command(name="resources", description="View CPU and RAM usage of this PC")
@app_commands.check(owner_only)
async def resources(interaction: discord.Interaction):
    await interaction.response.defer()
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    embed = discord.Embed(title="🖥️ System Resources", color=discord.Color.blurple())
    embed.add_field(name="⚙️ CPU", value=f"**{cpu:.0f}%** used", inline=True)
    embed.add_field(name="🧠 RAM", value=f"**{ram.percent:.0f}%** used", inline=True)
    embed.add_field(name="💾 Memory", value=f"{ram.used // (1024**2):,} MB / {ram.total // (1024**2):,} MB", inline=False)
    embed.set_footer(text="OSRS Monitor • /resources")
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)


@tree.command(name="logincheck", description="Manually check the OSRS login screen using OCR")
@app_commands.check(owner_only)
async def loginpixelstatus(interaction: discord.Interaction):
    await interaction.response.defer()
    visible = is_login_screen_visible_by_pixel()
    embed = discord.Embed(
        title="🔎 OSRS Login Check",
        description=(
            "🔴 **Login screen detected.**" if visible
            else "🟢 **No OSRS login screen detected.**"
        ),
        color=discord.Color.red() if visible else discord.Color.green(),
    )
    embed.add_field(name="Method", value="OCR • full screen", inline=True)
    embed.set_footer(text="OSRS Monitor • /logincheck")
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)


@tree.command(name="clienthealth", description="Check all OSRS client processes and Windows responsiveness")
@app_commands.check(owner_only)
async def clienthealth(interaction: discord.Interaction):
    await interaction.response.defer()
    clients = _get_osrs_clients()
    if not clients:
        await interaction.followup.send(
            embed=discord.Embed(
                title="🧩 OSRS Client Health",
                description="No `osclient.exe` processes are currently running.",
                color=discord.Color.orange(),
            )
        )
        return

    embed = discord.Embed(title="🧩 OSRS Client Health", color=discord.Color.blurple())
    for info in clients:
        pid = info["pid"]
        health = _client_health.get(pid, {})
        response = health.get("last_response")
        response_text = "🟢 Responding" if response is True else "🔴 Not responding" if response is False else "⚪ Not checked"
        embed.add_field(
            name=f"PID {pid}",
            value=(
                f"**Window:** `{_client_window_state(info)}`\n"
                f"**Response:** {response_text}\n"
                f"**Title:** `{(info.get('window') or {}).get('title', 'No main window')}`"
            ),
            inline=False,
        )
    embed.set_footer(text="OSRS Monitor • /clienthealth")
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)


@tree.command(name="clientevents", description="Show recent login/logout event-to-PID mappings")
@app_commands.check(owner_only)
async def clientevents(interaction: discord.Interaction):
    await interaction.response.defer()
    with _action_event_lock:
        events = list(_action_event_queue)[-12:]

    embed = discord.Embed(
        title="🧭 Recent Client Event Mapping",
        description="Most recent action events mapped to live OSRS PIDs.",
        color=discord.Color.blurple(),
    )
    if not events:
        embed.add_field(name="Events", value="No recent events.", inline=False)
    else:
        lines = []
        for event_time, event_state, event_pid in reversed(events):
            age = max(0, time.time() - event_time)
            lines.append(
                f"`{event_state.upper()}` • PID `{event_pid or 'unresolved'}` • {age:.1f}s ago"
            )
        embed.add_field(name="Recent mappings", value="\n".join(lines)[:1024], inline=False)

    embed.set_footer(text="OSRS Monitor • /clientevents")
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)


@tree.command(name="clientmap", description="Show live PID-to-client login/logout mappings")
@app_commands.check(owner_only)
async def clientmap(interaction: discord.Interaction):
    await interaction.response.defer()
    clients = _get_osrs_clients()
    if not clients:
        await interaction.followup.send(
            embed=discord.Embed(
                title="🧩 OSRS Client PID Map",
                description="No `osclient.exe` clients are currently running.",
                color=discord.Color.orange(),
            )
        )
        return

    embed = discord.Embed(title="🧩 OSRS Client PID Map", color=discord.Color.blurple())
    for info in clients:
        pid = info["pid"]
        health = _client_health.get(pid, {})
        response = health.get("last_response")
        response_text = "🟢 Responding" if response is True else "🔴 Not responding" if response is False else "⚪ Not checked"
        last = _client_last_login_logout_signal.get(pid)
        if last:
            last_text = (
                f"{last['state'].upper()} • {_format_timestamp(last['timestamp'])}\n"
                f"Match: `{last['source']}`\n"
                f"Signal: `{_shorten(last['message'], 260)}`"
            )
        else:
            last_text = "No login/logout signal mapped to this PID yet."
        embed.add_field(
            name=f"PID {pid}",
            value=(
                f"**Title:** `{((info.get('window') or {}).get('title') or 'No main window')}`\n"
                f"**Window:** `{_client_window_state(info)}`\n"
                f"**Response:** {response_text}\n"
                f"**State:** `{_login_state_by_pid.get(pid, 'unknown')}`\n"
                f"**State source:** `{_known_clients.get(pid, {}).get('last_state_source', 'not confirmed')}`\n"
                f"**Last mapped signal:** {last_text}"
            ),
            inline=False,
        )
    embed.set_footer(text="OSRS Monitor • /clientmap")
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)


@tree.command(name="logstatus", description="Show log monitoring and login/logout detection status")
@app_commands.check(owner_only)
async def logstatus(interaction: discord.Interaction):
    await interaction.response.defer()
    files = _candidate_log_files()
    last_signal = _last_login_logout_signal
    if last_signal:
        signal_type, signal_time, signal_file, signal_message = last_signal
        signal_text = (
            f"**Type:** `{signal_type.upper()}`\n"
            f"**File:** `{signal_file}`\n"
            f"**Time:** `{_format_timestamp(signal_time)}`\n"
            f"**Line:** `{_shorten(signal_message, 700)}`"
        )
    else:
        signal_text = "No login/logout signal has been detected since this bot started."

    file_lines = []
    for path in files:
        key = str(path.resolve())
        position = _log_file_positions.get(key)
        login_state = _login_state_by_log.get(key, "unknown")
        try:
            size = path.stat().st_size
            read_state = f"reading {position:,}/{size:,} bytes" if position is not None else "not initialized"
        except OSError:
            read_state = "file unavailable"
        rel = str(path).replace(str(LOG_ROOT_DIRECTORY), ".detuksosrs")
        file_lines.append(f"• `{rel}` — **{login_state}** — {read_state}")

    embed = discord.Embed(
        title="📄 Log Monitor Status",
        description="The bot recursively monitors the entire `.detuksosrs` tree for relevant logs. Login/logout state is tracked separately per log file; `/logscan` shows what was found.",
        color=discord.Color.blurple(),
    )
    log_file_text = "\n".join(file_lines) if file_lines else "No client log files found."
    # Discord limits an embed field value to 1024 characters.
    for index in range(0, len(log_file_text), 1000):
        embed.add_field(
            name="Log Files" if index == 0 else "Log Files (cont.)",
            value=log_file_text[index:index + 1000],
            inline=False,
        )
    embed.add_field(name="Last Login/Logout Signal", value=signal_text, inline=False)
    embed.add_field(name="Automatic OCR", value="🔴 Disabled — OCR is manual only via `/logincheck`.", inline=False)
    embed.set_footer(text="OSRS Monitor • /logstatus")
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)



def _log_debug_lines(max_files=10, max_lines=40, tail_bytes=64 * 1024):
    """Show only recent diagnostic lines from currently relevant log files.

    Prefer files modified recently. This avoids showing old historical lines
    from rotated logs that can make login/logout tests look identical.
    """
    keywords = (
        "login", "logout", "relog", "logged", "world", "in_game",
        "in-game", "game reached", "game state", "session", "state 10",
        "play widget", "welcome play", "action=login", "action=logout",
        "loading", "starting", "stopping", "shutdown",
    )
    results = []
    now = time.time()
    files = _candidate_log_files()
    # Prefer files changed in the last 15 minutes, then the newest remaining.
    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    recent = [p for p in files if p.exists() and (now - p.stat().st_mtime) <= 900]
    selected = recent[:max_files]
    if len(selected) < max_files:
        selected += [p for p in files if p not in selected][:max_files-len(selected)]

    for path in selected:
        try:
            with path.open("rb") as handle:
                handle.seek(0, 2)
                total = handle.tell()
                handle.seek(max(0, total - tail_bytes))
                text = handle.read().decode("utf-8", errors="replace")
        except (OSError, UnicodeError):
            continue

        for raw_line in text.splitlines():
            msg = _log_message(raw_line)
            lower = msg.lower()
            if any(word in lower for word in keywords):
                ts = _parse_log_timestamp(raw_line)
                state, confidence = _classify_login_logout_signal(msg)
                label = state or "other"
                if confidence:
                    label = f"{label}/{confidence}"
                results.append((path, ts, label, msg))

    results.sort(key=lambda item: (item[1] or datetime.min), reverse=True)
    return results[:max_lines]


def _log_debug_delta_lines(max_lines=60):
    """Return login/logout-related lines already consumed by the live monitor.

    The diagnostic command must never advance the shared log-file cursors;
    otherwise /logdebug could steal lines from the automatic login/logout
    monitor. The live monitor stores classified rows in a small ring buffer. V17 also maps strong action signals to live OSRS PIDs.
    """
    rows = list(_login_logout_debug_recent)
    return rows[-max_lines:]


def _launcher_inventory(max_items=80):
    """Return a lightweight inventory of the Jagex Launcher install tree."""
    root = JAGEX_LAUNCHER_DIRECTORY
    if not root.exists():
        return {"exists": False, "items": [], "files": 0, "dirs": 0}
    items = []
    files = 0
    dirs = 0
    try:
        for path in root.rglob("*"):
            try:
                if path.is_dir():
                    dirs += 1
                    continue
                files += 1
                st = path.stat()
                rel = str(path.relative_to(root))
                name_lower = path.name.lower()
                interesting = (
                    path.suffix.lower() in {".log", ".txt", ".json", ".ini", ".cfg", ".config", ".xml"}
                    or "log" in name_lower
                    or "config" in name_lower
                    or "crash" in name_lower
                    or "error" in name_lower
                )
                if interesting:
                    items.append((st.st_mtime, rel, st.st_size))
            except OSError:
                continue
    except OSError as exc:
        _record_monitor_error("jagex_launcher", exc)
        return {"exists": True, "items": [], "files": files, "dirs": dirs}
    items.sort(reverse=True)
    return {"exists": True, "items": items[:max_items], "files": files, "dirs": dirs}


@tree.command(name="logdebug", description="Show live login/logout log changes for diagnosis")
@app_commands.check(owner_only)
async def logdebug(interaction: discord.Interaction):
    await interaction.response.defer()
    # Use the monitor's cached diagnostic rows first. This command never
    # advances the shared log cursors.
    rows = _log_debug_delta_lines()
    mode = "Recent login/logout lines already seen by the live monitor"
    if not rows:
        rows = _log_debug_lines(max_files=6, max_lines=24)
        mode = "Recent diagnostic lines (no new matching lines since the last read)"

    base_description = (
        "Diagnostic only — no login/logout alert is generated by this command.\n"
        f"**{mode}**. Detuks root: `{LOG_ROOT_DIRECTORY}`\n"
        f"Jagex Launcher: `{JAGEX_LAUNCHER_DIRECTORY}`"
    )
    if not rows:
        embed = discord.Embed(title="🔎 Detuks Login/Logout Debug", description=base_description, color=discord.Color.blurple())
        embed.add_field(name="No matching lines", value="No recent login/logout diagnostic lines were found.", inline=False)
        embed.set_footer(text="OSRS Monitor • /logdebug • diagnostic only")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)
        return

    row_lines = []
    for row in rows:
        # Live diagnostic rows contain either the legacy 4 fields
        # (path, timestamp, label, message) or the newer 5 fields
        # (path, timestamp, label, confidence, message). Accept both so
        # /logdebug itself can never fail just because the classifier grew.
        if len(row) == 5:
            path, ts, label, confidence, msg = row
            if confidence and label and "/" not in str(label):
                label = f"{label}/{confidence}"
        else:
            path, ts, label, msg = row[:4]
        rel = str(path).replace(str(LOG_ROOT_DIRECTORY), ".detuksosrs")
        if str(path).startswith(str(JAGEX_LAUNCHER_DIRECTORY)):
            rel = str(path).replace(str(JAGEX_LAUNCHER_DIRECTORY), ".jagex-launcher")
        row_lines.append(f"`{rel}` • `{label}` • `{_format_timestamp(ts)}`\n{_shorten(msg, 450)}")

    chunks = []
    current = []
    current_len = 0
    for line in row_lines:
        if current and current_len + len(line) + 1 > 850:
            chunks.append("\n".join(current)); current=[]; current_len=0
        current.append(line); current_len += len(line)+1
    if current: chunks.append("\n".join(current))

    embeds=[]
    for field_start in range(0, len(chunks), 5):
        embed=discord.Embed(title="🔎 Detuks Login/Logout Debug", description=base_description if not embeds else "Diagnostic results (continued).", color=discord.Color.blurple())
        for offset, chunk in enumerate(chunks[field_start:field_start+5]):
            n=field_start+offset+1
            embed.add_field(name="Recent matching log lines" if n==1 else f"Recent matching log lines ({n})", value=chunk[:1000], inline=False)
        embed.set_footer(text="OSRS Monitor • /logdebug • diagnostic only")
        embed.timestamp=discord.utils.utcnow()
        embeds.append(embed)
    await interaction.followup.send(embed=embeds[0])
    for embed in embeds[1:]:
        await interaction.followup.send(embed=embed)


@tree.command(name="launcherscan", description="Inspect the installed Jagex Launcher files")
@app_commands.check(owner_only)
async def launcherscan(interaction: discord.Interaction):
    await interaction.response.defer()
    info = await asyncio.to_thread(_launcher_inventory)
    if not info["exists"]:
        await interaction.followup.send(embed=discord.Embed(title="🎮 Jagex Launcher Scan", description=f"Path not found: `{JAGEX_LAUNCHER_DIRECTORY}`", color=discord.Color.orange()))
        return
    lines=[f"Path: `{JAGEX_LAUNCHER_DIRECTORY}`", f"Files: **{info['files']:,}** • Directories: **{info['dirs']:,}**", "", "Interesting files (logs/config/errors):"]
    if info["items"]:
        for _, rel, size in info["items"][:45]:
            lines.append(f"• `{rel}` — {size:,} bytes")
    else:
        lines.append("No obvious log/config/error files found in the installation directory.")
    text="\n".join(lines)
    # Keep command response under Discord limits.
    embed=discord.Embed(title="🎮 Jagex Launcher Scan", description=text[:5800], color=discord.Color.blurple())
    embed.set_footer(text="OSRS Monitor • /launcherscan")
    embed.timestamp=discord.utils.utcnow()
    await interaction.followup.send(embed=embed)


@tree.command(name="logscan", description="Scan .detuksosrs and summarize relevant log files")
@app_commands.check(owner_only)
async def logscan(interaction: discord.Interaction):
    await interaction.response.defer()
    results = _log_scan_summary()
    if not results:
        await interaction.followup.send(
            embed=discord.Embed(
                title="📂 Detuks Log Scan",
                description=f"No relevant log files were found under `{LOG_ROOT_DIRECTORY}`.",
                color=discord.Color.orange(),
            )
        )
        return

    results.sort(key=lambda item: item["age"])
    active = [r for r in results if r["age"] <= 10]
    lines = []
    for item in results[:18]:
        rel = str(item["path"]).replace(str(LOG_ROOT_DIRECTORY), ".detuksosrs")
        c = item["counts"]
        lines.append(
            f"• `{rel}`\n"
            f"  `{item['state']}` • {item['size']:,} bytes • {item['age']:.0f}m old • "
            f"login-screen {c['login_screen']} / login {c['login']} / logout {c['logout']} / "
            f"task {c['task']} / errors {c['error']}"
        )

    embed = discord.Embed(
        title="📂 Detuks Log Scan",
        description=(
            f"Recursive scan of `{LOG_ROOT_DIRECTORY}`. "
            f"Found **{len(results)}** relevant log files; **{len(active)}** changed within the last 10 minutes.\n\n"
            "Login/logout detection uses per-log state; `LOGIN_SCREEN` during startup is not treated as a logout."
        ),
        color=discord.Color.blurple(),
    )
    chunk = "\n".join(lines) or "No relevant log details found."
    field_chunks = []
    current = []
    current_len = 0
    for line in chunk.splitlines():
        if current and current_len + len(line) + 1 > 900:
            field_chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        field_chunks.append("\n".join(current))

    # Only add up to 4 fields here; enough room remains for the current-state field.
    for index, field_chunk in enumerate(field_chunks[:4]):
        embed.add_field(
            name="Relevant logs" if index == 0 else "Relevant logs (cont.)",
            value=field_chunk,
            inline=False,
        )

    current_state = "\n".join(
        f"`{str(r['path']).replace(str(LOG_ROOT_DIRECTORY), '.detuksosrs')}` → **{r['state']}**"
        for r in active[:12]
    ) or "No recently active logs."
    if len(current_state) > 900:
        current_state = current_state[:897] + "..."
    embed.add_field(name="Current state", value=current_state, inline=False)
    embed.set_footer(text="OSRS Monitor • /logscan")
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)


@tree.command(name="clear", description="Delete 1 to 50 messages from this Discord channel")
@app_commands.describe(amount="Number of messages to delete (1 to 50)")
@app_commands.check(owner_only)
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 50]):
    await interaction.response.defer(ephemeral=True)

    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.followup.send(
            embed=discord.Embed(
                title="❌ Not Available",
                description="This command can only be used in a standard text channel.",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
        return

    permissions = interaction.channel.permissions_for(interaction.guild.me)
    if not permissions.manage_messages:
        await interaction.followup.send(
            embed=discord.Embed(
                title="❌ Permission Denied",
                description="The bot needs **Manage Messages** permission in this channel.",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
        return

    try:
        deleted = await interaction.channel.purge(limit=int(amount))
        embed = discord.Embed(
            title="🧹 Messages deleted",
            description=f"**{len(deleted)}** messages were deleted.",
            color=discord.Color.green(),
        )
        embed.add_field(name="Requested", value=str(int(amount)), inline=True)
        embed.set_footer(text="OSRS Monitor • /clear")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed, ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(
            embed=discord.Embed(
                title="❌ Permission Denied",
                description="Discord denied the deletion. Make sure the bot has **Manage Messages** permission.",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
    except Exception as exc:
        await interaction.followup.send(
            embed=discord.Embed(
                title="❌ Clear Failed",
                description=f"`{str(exc)[:500]}`",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "Discord bot token is missing. Put the token in discord_token.txt next to this bot "
            "or set the DISCORD_TOKEN environment variable."
        )
    client.run(TOKEN)
