# OSRS Discord Monitor — P2P Guardian V24.2.5
# Login/logout primary signals: action=Play / action=Logout / break-cycle relog confirmation.
# Monitoring behavior: login state is authoritative from observed log transitions, persists per-client state across bot restarts, never infers login state from the window title, and never maps action coordinates to minimized windows. Ambiguous multi-client events are suppressed rather than assigned to the wrong client.

"""
OSRS Discord Monitor - log based task monitoring.

This version keeps the useful monitoring from the previous bot, but replaces
screen-based task-overlay detection with live monitoring of the OSRS/P2P log.

Requirements:
    pip install discord.py pillow psutil pytesseract opencv-python numpy windows-capture==2.0.1

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
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageGrab

try:
    import support_report
except Exception:
    support_report = None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

# Central Discord branding. The public GitHub-hosted logo is used so every
# embed can carry the same P2P Guardian identity without uploading the logo
# file on every message.
GUARDIAN_LOGO_URL = (
    "https://raw.githubusercontent.com/p2pguardian/P2P-Guardian/main/"
    "assets/P2P_Guardian_Logo.png"
)
GUARDIAN_FOOTER = "P2P Guardian • OSRS Discord Monitor • V24.2.5"
PRODUCT_VERSION = "24.2.5"
GITHUB_LATEST_RELEASE_API = "https://api.github.com/repos/p2pguardian/P2P-Guardian/releases/latest"
UPDATE_CHECK_INTERVAL_MINUTES = 30
UPDATE_NOTICE_FILE = Path(__file__).with_name(".guardian_last_update_notice")

# P2P Guardian visual system — shared by the controller, installer artwork,
# and rendered Discord cards. RGB values match the Windows UI palette.
GUARDIAN_BG = (3, 19, 31)
GUARDIAN_PANEL = (6, 26, 41)
GUARDIAN_INNER = (9, 34, 53)
GUARDIAN_BORDER = (23, 56, 79)
GUARDIAN_ACCENT = (0, 143, 217)
GUARDIAN_PRIMARY = (0, 174, 239)
GUARDIAN_BLUE = (0, 136, 255)
GUARDIAN_NEXT = (0, 102, 217)
GUARDIAN_WHITE = (242, 246, 250)
GUARDIAN_MUTED = (184, 201, 216)
GUARDIAN_SUCCESS = (77, 219, 131)
GUARDIAN_DANGER = (255, 76, 76)
GUARDIAN_DISCORD_COLOR = discord.Color.from_rgb(*GUARDIAN_PRIMARY)
GUARDIAN_SUCCESS_COLOR = discord.Color.from_rgb(*GUARDIAN_SUCCESS)


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
_startup_screenshot_sent = False

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
_login_visual_checked_at_by_pid = {}
_login_visual_bootstrap_pending = set()
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
_current_task_target = None
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
_last_task_by_log = {}
_log_last_task_event_keys = {}
_log_last_failure_time = 0.0
_log_last_level_event_key = None
_task_client_pid_by_log = {}
TASK_FAILURE_CONTEXT_SECONDS = 300


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
                try:
                    class_name = win32gui.GetClassName(hwnd).strip()
                except Exception:
                    class_name = ""
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
                    "class_name": class_name,
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
        # Prefer the actual BotClient/game window. If several titled windows
        # belong to the same PID, prefer the largest non-console window so the
        # manual /screenshot command captures the OSRS client itself rather than
        # a helper/overlay window.
        def _window_rank(w):
            title_l = (w.get("title") or "").lower()
            class_l = (w.get("class_name") or "").lower()
            rect = w.get("rect") or (0, 0, 0, 0)
            area = max(0, int(rect[2] - rect[0])) * max(0, int(rect[3] - rect[1]))
            return (
                1 if "botclient" in title_l else 0,
                0 if "consolewindowclass" in class_l else 1,
                area,
            )
        windows.sort(key=_window_rank, reverse=True)
        main = windows[0] if windows else None
        result.append({
            "pid": pid,
            "create_time": p.info.get("create_time"),
            "window": main,
            "windows": windows,
        })
    return result




# Windows Graphics Capture (WGC) sessions are kept alive per HWND instead of
# starting/stopping a native capture for every /screenshot request.  This is
# important because the windows-capture native backend can be sensitive to
# repeated start/stop cycles in the same Python process.  A persistent session
# also lets WGC keep producing compositor frames for a background/occluded
# client, which is exactly what BitBlt/PrintWindow cannot do for GPU-rendered
# OSRS content.
_wgc_sessions = {}
_wgc_sessions_lock = threading.Lock()


def _capture_window_wgc(hwnd, timeout=1.25):
    """Capture one exact HWND through Windows Graphics Capture.

    Returns a PIL RGB image or None when the WGC dependency is unavailable or
    the selected window cannot be captured.  WGC is deliberately attempted
    before the older BitBlt/PrintWindow path because the OSRS game surface is
    GPU/compositor rendered and those GDI APIs can expose only a black client
    rectangle.

    The capture session is persistent per HWND.  Each callback copies the
    native frame immediately so no native mapped-frame memory escapes the
    callback.  This avoids the dangling-frame problem of keeping Frame objects
    after the native callback returns.
    """
    if os.name != "nt":
        return None
    try:
        from windows_capture import WindowsCapture
    except Exception:
        return None

    hwnd = int(hwnd)
    if not hwnd:
        return None

    session = None
    try:
        with _wgc_sessions_lock:
            session = _wgc_sessions.get(hwnd)
            if session is None or session.get("closed"):
                event = threading.Event()
                state = {
                    "capture": None,
                    "control": None,
                    "frame": None,
                    "event": event,
                    "closed": False,
                    "error": None,
                    "width": 0,
                    "height": 0,
                    "sequence": 0,
                }
                capture = WindowsCapture(
                    cursor_capture=False,
                    draw_border=False,
                    secondary_window=False,
                    minimum_update_interval=None,
                    dirty_region=None,
                    monitor_index=None,
                    window_name=None,
                    window_hwnd=hwnd,
                )
                state["capture"] = capture

                @capture.event
                def on_frame_arrived(frame, capture_control):
                    try:
                        # Copy immediately while the native mapped frame is
                        # owned by the callback. Never retain frame.frame_buffer.
                        copied = np.array(frame.frame_buffer, copy=True)
                        if copied.ndim != 3 or copied.shape[2] < 3:
                            raise RuntimeError("WGC returned an invalid frame buffer.")
                        with _wgc_sessions_lock:
                            current = _wgc_sessions.get(hwnd)
                            if current is not None:
                                current["frame"] = copied
                                current["width"] = int(getattr(frame, "width", copied.shape[1]))
                                current["height"] = int(getattr(frame, "height", copied.shape[0]))
                                current["sequence"] = int(current.get("sequence", 0)) + 1
                                current["event"].set()
                    except Exception as exc:
                        with _wgc_sessions_lock:
                            current = _wgc_sessions.get(hwnd)
                            if current is not None:
                                current["error"] = str(exc)
                                current["event"].set()

                @capture.event
                def on_closed():
                    with _wgc_sessions_lock:
                        current = _wgc_sessions.get(hwnd)
                        if current is not None:
                            current["closed"] = True
                            current["event"].set()

                _wgc_sessions[hwnd] = state
                session = state
                try:
                    state["control"] = capture.start_free_threaded()
                except Exception:
                    _wgc_sessions.pop(hwnd, None)
                    raise

        # Fast path: once a persistent WGC session has produced a frame,
        # return the latest compositor frame immediately. Starting a brand-new
        # WGC session is the only case where we need to wait for the first frame.
        # This removes the noticeable delay on repeated /screenshot commands.
        with _wgc_sessions_lock:
            frame = session.get("frame")
            closed = bool(session.get("closed"))
            error = session.get("error")
            before_sequence = int(session.get("sequence", 0))
            if frame is not None:
                image = frame.copy()
            else:
                image = None
                session["event"].clear()

        if image is None:
            # Initial WGC startup normally delivers a frame quickly. Keep this
            # bounded so a transient WGC startup issue cannot make Discord wait
            # several seconds before receiving the screenshot.
            deadline = time.monotonic() + min(max(0.35, float(timeout)), 1.25)
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if not session["event"].wait(min(0.10, remaining)):
                    continue
                with _wgc_sessions_lock:
                    if int(session.get("sequence", 0)) > before_sequence:
                        image = session.get("frame")
                        if image is not None:
                            image = image.copy()
                        break
                    if session.get("closed") or session.get("error"):
                        break
                session["event"].clear()

        if image is None:
            with _wgc_sessions_lock:
                frame = session.get("frame")
                closed = bool(session.get("closed"))
                error = session.get("error")
                if frame is not None:
                    image = frame.copy()
            if image is None:
                if closed and error:
                    raise RuntimeError(f"WGC capture closed: {error}")
                return None

        # windows-capture exposes BGRA for its normal 8-bit capture format.
        # Normalize conservatively if a backend returns RGBA instead.
        if image.shape[2] >= 4:
            rgb = cv2.cvtColor(image[:, :, :4], cv2.COLOR_BGRA2RGB)
        else:
            rgb = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb, "RGB")
    except Exception as exc:
        _record_monitor_error("WGC window capture", exc)
        return None


def _stop_wgc_session(hwnd):
    """Best-effort cleanup for a persistent WGC session."""
    try:
        with _wgc_sessions_lock:
            state = _wgc_sessions.pop(int(hwnd), None)
        if state is not None:
            control = state.get("control")
            if control is not None:
                control.stop()
    except Exception:
        pass


def _capture_window_printwindow(hwnd, render_wait=0.35):
    """Capture only the selected OSRS window, including minimized clients.

    GPU-rendered OSRS clients can return a black frame from PrintWindow. The
    reliable path is therefore: restore the selected client, temporarily put
    that exact window on top, let it render briefly, and capture its client
    rectangle with BitBlt. PrintWindow remains a fallback. No full desktop
    capture is used.
    """
    if os.name != "nt":
        raise RuntimeError("Window capture is only available on Windows.")

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hwnd = int(hwnd)
    if not hwnd or not user32.IsWindow(hwnd):
        raise RuntimeError("Invalid window handle.")

    # First try Windows Graphics Capture. Unlike BitBlt/PrintWindow, WGC
    # captures the compositor/application surface for the exact HWND and can
    # work when the window is covered or running in the background.
    wgc_image = _capture_window_wgc(hwnd, timeout=2.5)
    if wgc_image is not None:
        # Reject a genuinely blank WGC frame as well; the GDI fallback is kept
        # only for systems where WGC is unavailable or fails to produce pixels.
        try:
            sample = np.asarray(wgc_image.resize((96, 96))).astype(np.uint8)
            gray = cv2.cvtColor(sample, cv2.COLOR_RGB2GRAY)
            if float((gray < 12).mean()) <= 0.90:
                return wgc_image
        except Exception:
            return wgc_image

    try:
        import win32gui
    except Exception as exc:
        raise RuntimeError(f"Windows window API unavailable: {exc}")

    was_minimized = bool(user32.IsIconic(hwnd))
    original_placement = None
    original_rect = None
    original_foreground = None
    try:
        original_foreground = int(user32.GetForegroundWindow() or 0)
    except Exception:
        original_foreground = None
    if was_minimized:
        try:
            original_placement = win32gui.GetWindowPlacement(hwnd)
        except Exception:
            pass
        try:
            original_rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            pass
        # A minimized GPU client has to be restored before it can render a
        # fresh frame. Keep its original restored position whenever possible.
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE

    # GPU-rendered OSRS clients may keep their swap-chain black until the
    # window actually owns the foreground. For an explicit /screenshot request,
    # activate only this selected client. It is restored afterwards.
    try:
        user32.ShowWindow(hwnd, 9)
        foreground = int(user32.GetForegroundWindow() or 0)
        current_tid = int(user32.GetCurrentThreadId())
        target_tid = int(user32.GetWindowThreadProcessId(hwnd, None))
        fg_tid = int(user32.GetWindowThreadProcessId(foreground, None)) if foreground else 0
        attached = False
        if fg_tid and fg_tid != target_tid:
            attached = bool(user32.AttachThreadInput(current_tid, target_tid, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        if attached:
            user32.AttachThreadInput(current_tid, target_tid, False)
    except Exception:
        pass

    # Temporarily make this exact client topmost so another window cannot cover
    # the pixels used by BitBlt. If its restored position is off-screen, move it.
    original_ex_style = 0
    made_topmost = False
    try:
        GWL_EXSTYLE = -20
        WS_EX_TOPMOST = 0x00000008
        original_ex_style = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
        rect = win32gui.GetWindowRect(hwnd)
        rw, rh = max(1, rect[2]-rect[0]), max(1, rect[3]-rect[1])
        sw = int(user32.GetSystemMetrics(0))
        sh = int(user32.GetSystemMetrics(1))
        px, py = int(rect[0]), int(rect[1])
        if px + rw < 0 or py + rh < 0 or px > sw - 10 or py > sh - 10:
            px, py = 20, 20
        HWND_TOPMOST = -1
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040
        user32.SetWindowPos(hwnd, HWND_TOPMOST, px, py, rw, rh, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        made_topmost = True
    except Exception:
        pass
    time.sleep(max(0.35, float(render_wait)))

    def _client_size_and_screen_origin():
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        width = int(right - left)
        height = int(bottom - top)
        if width <= 0 or height <= 0:
            raise RuntimeError("Window has no capturable client area.")
        origin = win32gui.ClientToScreen(hwnd, (0, 0))
        return width, height, int(origin[0]), int(origin[1])

    def _printwindow_capture(width, height):
        screen_dc = user32.GetDC(hwnd)
        if not screen_dc:
            raise RuntimeError("GetDC failed.")
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        if not mem_dc or not bitmap:
            if mem_dc:
                gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, screen_dc)
            raise RuntimeError("Could not create capture bitmap.")
        old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
        try:
            ok = user32.PrintWindow(hwnd, mem_dc, 2)
            if not ok:
                ok = user32.PrintWindow(hwnd, mem_dc, 0)
            if not ok:
                raise RuntimeError("PrintWindow could not render the OSRS window.")

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]
            class BITMAPINFO(ctypes.Structure):
                _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                            ("bmiColors", ctypes.c_uint32 * 1)]
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0
            pixels = (ctypes.c_ubyte * (width * height * 4))()
            copied = gdi32.GetDIBits(mem_dc, bitmap, 0, height, ctypes.byref(pixels), ctypes.byref(bmi), 0)
            if copied != height:
                raise RuntimeError("Could not read rendered OSRS window pixels.")
            return Image.frombuffer("RGBA", (width, height), bytes(pixels), "raw", "BGRA", 0, 1).convert("RGB")
        finally:
            gdi32.SelectObject(mem_dc, old_bitmap)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, screen_dc)

    def _screen_capture(width, height, x, y):
        # Capture only the selected HWND's client rectangle from the display.
        # This is intentionally NOT ImageGrab.grab() of the whole desktop.
        screen_dc = user32.GetDC(0)
        if not screen_dc:
            raise RuntimeError("Screen DC unavailable.")
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        if not mem_dc or not bitmap:
            if mem_dc:
                gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(0, screen_dc)
            raise RuntimeError("Could not create screen capture bitmap.")
        old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
        try:
            SRCCOPY = 0x00CC0020
            if not gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, x, y, SRCCOPY):
                raise RuntimeError("BitBlt could not capture the OSRS client.")
            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]
            class BITMAPINFO(ctypes.Structure):
                _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 1)]
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0
            pixels = (ctypes.c_ubyte * (width * height * 4))()
            copied = gdi32.GetDIBits(mem_dc, bitmap, 0, height, ctypes.byref(pixels), ctypes.byref(bmi), 0)
            if copied != height:
                raise RuntimeError("Could not read screen-captured OSRS pixels.")
            return Image.frombuffer("RGBA", (width, height), bytes(pixels), "raw", "BGRA", 0, 1).convert("RGB")
        finally:
            gdi32.SelectObject(mem_dc, old_bitmap)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(0, screen_dc)

    try:
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
            time.sleep(0.18)
        except Exception:
            pass
        width, height, x, y = _client_size_and_screen_origin()

        # Prefer the real rendered pixels on screen. This is much more reliable
        # for GPU/compositor clients than PrintWindow.
        def _is_blank_game_frame(candidate):
            sample = np.asarray(candidate.resize((96, 96))).astype(np.uint8)
            gray_sample = cv2.cvtColor(sample, cv2.COLOR_RGB2GRAY)
            dark_ratio = float((gray_sample < 12).mean())
            margin_x = max(1, int(candidate.width * 0.08))
            margin_y = max(1, int(candidate.height * 0.12))
            central = np.asarray(candidate.crop((margin_x, margin_y,
                max(margin_x+1, candidate.width-margin_x),
                max(margin_y+1, candidate.height-margin_y))).resize((96,96))).astype(np.uint8)
            central_gray = cv2.cvtColor(central, cv2.COLOR_RGB2GRAY)
            central_dark_ratio = float((central_gray < 12).mean())
            return dark_ratio > 0.90 or central_dark_ratio > 0.88

        image = _screen_capture(width, height, x, y)
        # GPU clients can need an extra presentation interval after activation.
        # Retry the selected window only; never capture the desktop globally.
        if _is_blank_game_frame(image):
            for wait in (0.35, 0.55):
                time.sleep(wait)
                try:
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.SetActiveWindow(hwnd)
                except Exception:
                    pass
                image = _screen_capture(width, height, x, y)
                if not _is_blank_game_frame(image):
                    break

        # PrintWindow is now a last fallback, not the primary renderer. Some
        # clients expose a usable composited frame there after activation.
        if _is_blank_game_frame(image):
            try:
                pw = _printwindow_capture(width, height)
                if not _is_blank_game_frame(pw):
                    image = pw
            except Exception:
                pass

        if _is_blank_game_frame(image):
            raise RuntimeError("OSRS client rendered a blank frame after activation and capture retries.")
        return image
    except Exception as first_exc:
        try:
            width, height, x, y = _client_size_and_screen_origin()
            return _screen_capture(width, height, x, y)
        except Exception as second_exc:
            raise RuntimeError(f"OSRS window capture failed: {first_exc}; screen-window capture failed: {second_exc}")
    finally:
        if made_topmost:
            try:
                HWND_NOTOPMOST = -2
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
                # Restore the original topmost flag if the client had it.
                if original_ex_style & 0x00000008:
                    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            except Exception:
                pass
        if was_minimized:
            try:
                if original_placement is not None:
                    win32gui.SetWindowPlacement(hwnd, original_placement)
                else:
                    user32.ShowWindow(hwnd, 6)
            except Exception:
                try:
                    user32.ShowWindow(hwnd, 6)
                except Exception:
                    pass
        if original_foreground and user32.IsWindow(original_foreground):
            try:
                user32.SetForegroundWindow(original_foreground)
            except Exception:
                pass

def _detect_login_screen_from_window(client_info):
    """Detect the actual login/Play Now screen for one specific OSRS window.

    This is intentionally per-PID. It does not inspect the whole desktop and it
    does not trust a previous persisted login state. A detected Play Now/login
    screen is stronger evidence than an old log or cached state.
    """
    window = (client_info or {}).get("window") or {}
    hwnd = window.get("hwnd")
    if not hwnd:
        return None

    try:
        import pytesseract
    except ImportError:
        return None

    # Resolve a normal Windows Tesseract installation when the PATH is not set.
    if not pytesseract.pytesseract.tesseract_cmd or pytesseract.pytesseract.tesseract_cmd == "tesseract":
        for candidate in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if os.path.exists(candidate):
                pytesseract.pytesseract.tesseract_cmd = candidate
                break

    try:
        image = _capture_window_printwindow(int(hwnd), render_wait=0.12).convert("RGB")
    except Exception as exc:
        _record_monitor_error("per-client login detection", exc)
        return None

    sample = np.asarray(image.resize((96, 96))).astype(np.int16)
    if float(sample.std()) < 2.0 or float(sample.mean()) < 1.0:
        return None

    frame = np.array(image)
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    variants = [resized, cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]]

    detected_text = []
    try:
        for variant in variants:
            text = pytesseract.image_to_string(variant, config="--oem 3 --psm 11")
            detected_text.append(text.lower())
    except Exception as exc:
        _record_monitor_error("per-client login OCR", exc)
        return None

    text = "\n".join(detected_text)
    compact = re.sub(r"[^a-z0-9]+", "", text)

    # Play Now is the strongest visual marker for the OSRS login screen.
    if re.search(r"\bplay\s*now\b", text) or "playnow" in compact:
        return True
    if "click here to play" in text or "clickheretoplay" in compact:
        return True

    # Secondary login-screen markers. Require more than a generic occurrence of
    # the word 'login' to avoid false positives from in-game UI/help text.
    login_markers = sum([
        "welcome" in text or "welcom" in text,
        "existing user" in text or "existinguser" in compact,
        "new user" in text or "newuser" in compact,
        "login" in text or "log in" in text or "signin" in compact,
    ])
    if login_markers >= 2:
        return True

    return False


def _refresh_pid_login_states_from_window_ocr(clients=None):
    """Refresh login state from the rendered OSRS window for every live PID."""
    clients = clients if clients is not None else _get_osrs_clients()
    for info in clients:
        pid = info.get("pid")
        if pid is None:
            continue
        visual_login = _detect_login_screen_from_window(info)
        if visual_login is True:
            _login_state_by_pid[pid] = "login_screen"
            known = _known_clients.setdefault(pid, {})
            known["persistent_state"] = "login_screen"
            known["last_state_source"] = "window OCR / Play Now"
        elif visual_login is False:
            # A clean visual negative is enough to remove a stale persisted
            # login-screen state, but it does not manufacture a login state.
            if _login_state_by_pid.get(pid) == "login_screen":
                _login_state_by_pid[pid] = "unknown"
            known = _known_clients.setdefault(pid, {})
            known["last_state_source"] = "window OCR / no login screen"


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


def _resolve_task_client(log_path):
    """Resolve a task log to an OSRS client without guessing between clients."""
    if log_path is None:
        return None
    key = str(Path(log_path).resolve())
    cached_pid = _task_client_pid_by_log.get(key)
    live_clients = _get_osrs_clients()

    if cached_pid is not None:
        for info in live_clients:
            if info.get("pid") == cached_pid:
                return info

    # Some installations include the client PID in the log filename. Prefer
    # that explicit relationship when present.
    name = Path(log_path).name
    pid_candidates = []
    for raw in re.findall(r"(?<!\d)(\d{3,8})(?!\d)", name):
        try:
            pid_candidates.append(int(raw))
        except ValueError:
            pass
    for info in live_clients:
        if info.get("pid") in pid_candidates:
            _task_client_pid_by_log[key] = info.get("pid")
            return info

    # A single live client is unambiguous. With multiple clients we do not
    # invent an account-to-log mapping.
    if len(live_clients) == 1:
        pid = live_clients[0].get("pid")
        if pid is not None:
            _task_client_pid_by_log[key] = pid
        return live_clients[0]

    return None


def _task_account_label(log_path):
    info = _resolve_task_client(log_path)
    if not info:
        return "Unknown client"
    return _client_label(info)


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



def _guardian_font(size, bold=False):
    """Load a clean Windows UI font with a safe fallback."""
    candidates = [
        r"C:\\Windows\\Fonts\\segoeuib.ttf" if bold else r"C:\\Windows\\Fonts\\segoeui.ttf",
        r"C:\\Windows\\Fonts\\arialbd.ttf" if bold else r"C:\\Windows\\Fonts\\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


_GUARDIAN_LOGO_CACHE = None


def _guardian_status_card(*, osrs_status, login_status, task_text, activity, location,
                          log_name, client_status, client_health, monitor_status, error_text):
    """Render a spacious, high-contrast P2P Guardian dashboard for Discord."""
    global _GUARDIAN_LOGO_CACHE

    # Designed around Discord's displayed image width: fewer panels, more vertical room,
    # and large dynamic values that remain readable when real data is longer than the demo.
    # The client panel grows with the number of detected clients instead of silently
    # dropping clients when several OSRS instances are running.
    _raw_client_lines = [str(x) for x in str(client_status or "").splitlines() if str(x).strip()]
    _client_line_count = max(1, len(_raw_client_lines))
    width = 1200
    height = max(860, 860 + max(0, _client_line_count - 3) * 46)
    img = Image.new("RGB", (width, height), GUARDIAN_BG)
    draw = ImageDraw.Draw(img, "RGBA")

    # Fast background.
    for y in range(height):
        t = y / max(1, height - 1)
        draw.line((0, y, width, y), fill=(3 + int(2*t), 10 + int(8*t), 22 + int(17*t), 255))
    for offset in range(-420, 1300, 150):
        draw.line((offset, 0, offset - 300, height), fill=(0, 143, 217, 17), width=2)

    draw.rounded_rectangle((12, 12, width-12, height-12), radius=24,
                           fill=(6, 26, 41, 250), outline=(0, 174, 239, 245), width=3)
    draw.rounded_rectangle((28, 28, width-28, height-28), radius=18,
                           outline=(23, 56, 79, 125), width=1)

    if _GUARDIAN_LOGO_CACHE is None:
        logo_path = Path(__file__).with_name("P2P_Guardian_Logo.png")
        if logo_path.exists():
            try:
                _GUARDIAN_LOGO_CACHE = Image.open(logo_path).convert("RGBA")
            except Exception:
                _GUARDIAN_LOGO_CACHE = False
    logo = _GUARDIAN_LOGO_CACHE if _GUARDIAN_LOGO_CACHE is not False else None

    title_font = _guardian_font(30, True)
    sub_font = _guardian_font(17, False)
    label_font = _guardian_font(20, True)
    value_font = _guardian_font(28, True)
    small_value_font = _guardian_font(23, True)
    footer_font = _guardian_font(15, False)
    slogan_font = _guardian_font(21, True)

    def icon(x, y, kind, scale=1.0):
        c=(80, 205, 255, 255); c2=(242,246,250,255)
        w=max(2,int(2.5*scale))
        if kind == 'monitor':
            draw.rounded_rectangle((x,y,x+30*scale,y+22*scale), radius=int(4*scale), outline=c, width=w)
            draw.line((x+15*scale,y+22*scale,x+15*scale,y+30*scale), fill=c2, width=w)
            draw.line((x+7*scale,y+31*scale,x+23*scale,y+31*scale), fill=c2, width=w)
        elif kind == 'lock':
            draw.rounded_rectangle((x+3*scale,y+11*scale,x+28*scale,y+31*scale), radius=int(4*scale), fill=(9,34,53,235), outline=c, width=w)
            draw.arc((x+7*scale,y-5*scale,x+24*scale,y+15*scale), 180, 360, fill=c2, width=w)
        elif kind == 'clipboard':
            draw.rounded_rectangle((x+2*scale,y+5*scale,x+28*scale,y+31*scale), radius=int(4*scale), fill=(9,34,53,235), outline=c, width=w)
            draw.rounded_rectangle((x+8*scale,y,x+22*scale,y+8*scale), radius=int(2*scale), fill=c, outline=c2, width=1)
        elif kind == 'target':
            draw.ellipse((x,y,x+30*scale,y+30*scale), outline=(255,90,90,255), width=w)
            draw.ellipse((x+8*scale,y+8*scale,x+22*scale,y+22*scale), outline=c2, width=w)
            draw.ellipse((x+13*scale,y+13*scale,x+17*scale,y+17*scale), fill=(255,90,90,255))
        elif kind == 'clock':
            draw.ellipse((x,y,x+30*scale,y+30*scale), outline=c2, width=w)
            draw.line((x+15*scale,y+15*scale,x+15*scale,y+7*scale), fill=c, width=w)
            draw.line((x+15*scale,y+15*scale,x+23*scale,y+19*scale), fill=c, width=w)
        elif kind == 'file':
            draw.polygon([(x+4*scale,y),(x+21*scale,y),(x+29*scale,y+8*scale),(x+29*scale,y+31*scale),(x+4*scale,y+31*scale)], outline=c, fill=(9,34,53,235))
        elif kind == 'users':
            draw.ellipse((x+10*scale,y,x+21*scale,y+11*scale), fill=c2)
            draw.ellipse((x,y+5*scale,x+10*scale,y+15*scale), fill=(0,143,217,255))
            draw.ellipse((x+21*scale,y+5*scale,x+31*scale,y+15*scale), fill=(0,143,217,255))
            draw.rounded_rectangle((x+6*scale,y+14*scale,x+25*scale,y+31*scale), radius=int(5*scale), fill=(70,175,240,255))
        elif kind == 'shield':
            pts=[(x+15*scale,y),(x+28*scale,y+5*scale),(x+25*scale,y+24*scale),(x+15*scale,y+31*scale),(x+5*scale,y+24*scale),(x+2*scale,y+5*scale)]
            draw.polygon(pts, fill=(15,75,135,230), outline=c)
        elif kind == 'search':
            draw.ellipse((x+2*scale,y+2*scale,x+21*scale,y+21*scale), outline=c2, width=w)
            draw.line((x+19*scale,y+19*scale,x+30*scale,y+30*scale), fill=c, width=max(2,int(3*scale)))
        elif kind == 'calendar':
            draw.rounded_rectangle((x,y+4*scale,x+30*scale,y+31*scale), radius=int(4*scale), fill=(8,38,64,235), outline=c, width=w)
            draw.line((x,y+12*scale,x+30*scale,y+12*scale), fill=c2, width=1)

    def clean(text):
        text = str(text or "—")
        text = re.sub(r'[🟢🔴🟠⚪⚫🚨🖥️🔐📋🎯📍⏱️📄🧩🛡️🔎📅]', '', text)
        text = text.replace('**','').replace('`','').replace('• ','')
        return re.sub(r'\s+', ' ', text).strip() or '—'

    def fit_px(text, font, max_width):
        text = clean(text)
        if draw.textbbox((0,0), text, font=font)[2] <= max_width:
            return text
        suffix = '...'
        candidate = text
        while len(candidate) > 1 and draw.textbbox((0,0), candidate + suffix, font=font)[2] > max_width:
            candidate = candidate[:-1]
        return candidate.rstrip() + suffix

    def fit_value(text, max_width, base_size=28, min_size=16, bold=True):
        """Scale a value font to the available panel width before truncating."""
        text = clean(text)
        for size in range(base_size, min_size - 1, -1):
            font = _guardian_font(size, bold)
            if draw.textbbox((0,0), text, font=font)[2] <= max_width:
                return font, text
        font = _guardian_font(min_size, bold)
        return font, fit_px(text, font, max_width)

    def panel(box, fill=(3,24,43,240), outline=(36,120,180,210)):
        draw.rounded_rectangle(box, radius=11, fill=fill, outline=outline, width=2)

    def card(x, y, w, h, label, value, kind, secondary=None):
        panel((x,y,x+w,y+h))
        icon(x+14,y+12,kind,0.78)
        draw.text((x+52,y+7), label, font=label_font, fill=(242,246,250,255))
        value_font_dynamic, value_text = fit_value(value, w-32, 28, 17, True)
        draw.text((x+16,y+43), value_text, font=value_font_dynamic, fill=(242,246,250,255))
        if secondary:
            secondary_font, secondary_text = fit_value(secondary, w-32, 23, 15, True)
            draw.text((x+16,y+h-31), secondary_text, font=secondary_font, fill=(225,239,252,255))

    # Header.
    if logo is not None:
        try:
            sm=logo.copy(); sm.thumbnail((48,48), Image.Resampling.LANCZOS)
            img.paste(sm,(45,43),sm)
        except Exception: pass
    brand_x = 105
    brand_y = 43
    brand = "P2P GUARDIAN"
    draw.text((brand_x,brand_y), brand, font=title_font, fill=(0,174,239,255), anchor="lt")
    brand_w = draw.textbbox((0,0), brand, font=title_font)[2]
    draw.text((brand_x + brand_w + 14,brand_y), "| OSRS MONITOR", font=title_font, fill=(242,246,250,255), anchor="lt")
    draw.text((45,82), "Real-time monitoring for your OSRS journey.", font=sub_font, fill=(184,201,216,255))

    # LEFT COLUMN — spacious, readable information.
    lx, rx = 45, 405
    card(lx,112,330,104,"OSRS",osrs_status,'monitor',f"Client: {PROCESS_NAME}")
    card(rx,112,330,104,"Login",login_status,'lock')
    card(lx,230,690,92,"Current Task",task_text,'clipboard')
    card(lx,336,220,116,"Activity",activity,'target',f"Location: {location}")
    card(lx+235,336,220,116,"Active Log",log_name,'file')

    clients_bottom = max(710, height - 150)
    panel((lx,466,735,clients_bottom))
    icon(lx+16,484,'users',0.8)
    draw.text((lx+55,480), "OSRS Clients", font=label_font, fill=(242,246,250,255))
    client_lines=[clean(x) for x in str(client_status or 'No osclient.exe clients found.').splitlines() if clean(x)]
    yy=522
    for line in client_lines:
        if yy + 34 > clients_bottom - 18:
            break
        line_font, line_text = fit_value(line, 650, 28, 17, True)
        draw.text((lx+18,yy), line_text, font=line_font, fill=(242,246,250,255))
        yy += 45

    # RIGHT COLUMN — logo + clearly separated status blocks.
    panel((755,112,1155,710), fill=(2,18,34,180), outline=(32,101,158,185))
    if logo is not None:
        try:
            big=logo.copy(); big.thumbnail((310,310), Image.Resampling.LANCZOS)
            a=big.getchannel('A').point(lambda v:int(v*0.42)); big.putalpha(a)
            glow=Image.new('RGBA',big.size,(0,135,255,0)); glow.putalpha(a.filter(ImageFilter.GaussianBlur(16)))
            gx=800+(310-big.width)//2; gy=126
            img.paste(glow,(gx,gy),glow); img.paste(big,(gx,gy),big)
        except Exception: pass
    draw.text((865,315), "PLAY SMARTER", font=slogan_font, fill=(0,174,239,245))
    draw.text((890,344), "STAY SAFER", font=slogan_font, fill=(0,174,239,245))
    draw.line((875,378,1045,360), fill=(0,174,255,230), width=3)

    # Monitor status.
    panel((777,400,1133,478))
    icon(792,414,'shield',0.65)
    draw.text((830,408), "MONITORS", font=label_font, fill=(242,246,250,255))
    mon_color=(90,240,155,255) if 'operational' in str(monitor_status).lower() else (255,185,90,255)
    draw.text((830,439), fit_px(monitor_status, small_value_font, 285), font=small_value_font, fill=mon_color)

    # Client health. Do not show the old session schedule because it was not
    # a reliable representation of the actual OSRS session state.
    panel((777,492,1133,584))
    icon(792,505,'monitor',0.62)
    draw.text((830,499), "CLIENT HEALTH", font=label_font, fill=(242,246,250,255))
    health_lines=[clean(x) for x in str(client_health or '').splitlines() if clean(x)]
    if not health_lines: health_lines=['State: Unknown']
    for i,line in enumerate(health_lines[:2]):
        health_font, health_text = fit_value(line, 285, 23, 14, True)
        draw.text((830,530+i*25), health_text, font=health_font, fill=(242,246,250,255))

    # Errors.
    panel((777,598,1133,690))
    icon(792,611,'search',0.62)
    draw.text((830,605), "ERRORS", font=label_font, fill=(242,246,250,255))
    error_font, error_text_fit = fit_value(error_text, 285, 23, 13, True)
    draw.text((830,638), error_text_fit, font=error_font, fill=(242,246,250,255))

    # Footer.
    footer_y = height - 132
    draw.line((45,footer_y,width-45,footer_y), fill=(23,56,79,190), width=2)
    if logo is not None:
        try:
            foot=logo.copy(); foot.thumbnail((28,28), Image.Resampling.LANCZOS)
            img.paste(foot,(48,footer_y+16),foot)
        except Exception: pass
    draw.text((85,footer_y+19), "P2P Guardian", font=footer_font, fill=(0,174,239,255))
    draw.text((185,footer_y+19), "|  OSRS Discord Monitor  |  /status  |  V24.2.5", font=footer_font, fill=(184,201,216,255))
    stamp=datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    draw.text((1010,footer_y+19), stamp, font=footer_font, fill=(184,201,216,255))
    return img



def _guardian_event_card(*, title, subtitle=None, fields=None, accent=(0, 170, 255, 255), badge=None):
    """Render a high-contrast P2P Guardian event card for Discord."""
    global _GUARDIAN_LOGO_CACHE
    width, height = 1400, 800
    img = Image.new("RGB", (width, height), GUARDIAN_BG)
    draw = ImageDraw.Draw(img, "RGBA")
    # Fast background: smooth bands + subtle diagonal light.
    for y in range(height):
        t = y / max(1, height - 1)
        draw.line((0, y, width, y), fill=(3 + int(2*t), 10 + int(8*t), 22 + int(17*t), 255))
    for offset in range(-500, 1500, 170):
        draw.line((offset, 0, offset - 320, height), fill=(0, 150, 255, 18), width=2)
    draw.rounded_rectangle((16,16,width-16,height-16), radius=26, fill=(2,14,29,248), outline=accent, width=3)
    draw.rounded_rectangle((32,32,width-32,height-32), radius=20, outline=(23,56,79,130), width=1)

    if _GUARDIAN_LOGO_CACHE is None:
        logo_path = Path(__file__).with_name("P2P_Guardian_Logo.png")
        if logo_path.exists():
            try:
                _GUARDIAN_LOGO_CACHE = Image.open(logo_path).convert("RGBA")
            except Exception:
                _GUARDIAN_LOGO_CACHE = False
    logo = _GUARDIAN_LOGO_CACHE if _GUARDIAN_LOGO_CACHE is not False else None

    title_font = _guardian_font(42, True)
    sub_font = _guardian_font(21, False)
    label_font = _guardian_font(22, True)
    value_font = _guardian_font(32, True)
    small_font = _guardian_font(24, False)
    footer_font = _guardian_font(16, False)

    def clean(text):
        text = str(text or "—")
        text = re.sub(r'[🟢🔴🟠⚪⚫🚨🖥️🔐📋🎯📍⏱️📄🧩🛡️🔎📅🏆🎉🔑🪟⚠️]', '', text)
        text = text.replace('**','').replace('`','')
        return re.sub(r'\s+', ' ', text).strip() or '—'

    def fit(text, font, max_width):
        text = clean(text)
        if draw.textbbox((0,0), text, font=font)[2] <= max_width:
            return text
        suffix='...'
        while len(text)>1 and draw.textbbox((0,0), text+suffix, font=font)[2] > max_width:
            text=text[:-1]
        return text.rstrip()+suffix

    def fit_font(text, max_width, base=32, minimum=16, bold=True):
        text=clean(text)
        for size in range(base, minimum-1, -1):
            f=_guardian_font(size,bold)
            if draw.textbbox((0,0),text,font=f)[2] <= max_width:
                return f,text
        f=_guardian_font(minimum,bold)
        return f,fit(text,f,max_width)

    def panel(x,y,w,h, fill=(9,34,53,235), outline=(23,56,79,215)):
        draw.rounded_rectangle((x,y,x+w,y+h), radius=14, fill=fill, outline=outline, width=2)

    # Header.
    if logo is not None:
        sm=logo.copy(); sm.thumbnail((58,58), Image.Resampling.LANCZOS); img.paste(sm,(54,52),sm)
    brand_x = 130
    brand_y = 52
    brand = "P2P GUARDIAN"
    draw.text((brand_x,brand_y), brand, font=title_font, fill=(0,174,239,255), anchor="lt")
    brand_w = draw.textbbox((0,0), brand, font=title_font)[2]
    draw.text((brand_x + brand_w + 14,brand_y), "| OSRS MONITOR", font=title_font, fill=(242,246,250,255), anchor="lt")
    if badge:
        draw.rounded_rectangle((1050,57,1285,105), radius=18, fill=accent, outline=(210,240,255,220), width=1)
        tw=draw.textbbox((0,0), clean(badge), font=label_font)[2]
        draw.text((1167-tw/2,65), clean(badge), font=label_font, fill=(242,246,250,255))
    if subtitle:
        draw.text((55,116), fit(subtitle, sub_font, 1240), font=sub_font, fill=(184,201,216,255))

    # Main content: large, uncluttered fields.
    usable=[f for f in (fields or []) if f and len(f)>=2]
    left_x=55; top=160; left_w=790; right_x=875; right_w=470
    y=top
    for i,(label,value,*_) in enumerate(usable[:4]):
        if i<2:
            x=left_x + i*405
            panel(x,top,385,112)
            draw.text((x+22,top+18), clean(label).upper(), font=label_font, fill=(242,246,250,255))
            vf, vt = fit_font(value, 340, 32, 16, True)
            draw.text((x+22,top+57), vt, font=vf, fill=(242,246,250,255))
        else:
            yy=top+130+(i-2)*130
            panel(left_x,yy,left_w,112)
            draw.text((left_x+22,yy+16), clean(label).upper(), font=label_font, fill=(242,246,250,255))
            vf, vt = fit_font(value, left_w-44, 32, 16, True)
            draw.text((left_x+22,yy+53), vt, font=vf, fill=(242,246,250,255))

    yy=top
    for label,value,*_ in usable[4:]:
        if yy+105>height-90: break
        panel(right_x,yy,right_w,105)
        draw.text((right_x+20,yy+14), clean(label).upper(), font=label_font, fill=(242,246,250,255))
        vf, vt = fit_font(value, right_w-40, 32, 16, True)
        draw.text((right_x+20,yy+50), vt, font=vf, fill=(242,246,250,255))
        yy+=122

    # Prominent watermark, kept above the lower edge so it never crowds the footer.
    if logo is not None:
        try:
            big=logo.copy(); big.thumbnail((390,390), Image.Resampling.LANCZOS)
            a=big.getchannel('A').point(lambda v:int(v*0.30)); big.putalpha(a)
            glow=Image.new('RGBA',big.size,(0,135,255,0)); glow.putalpha(a.filter(ImageFilter.GaussianBlur(18)))
            gx=1010+(390-big.width)//2; gy=215
            img.paste(glow,(gx,gy),glow); img.paste(big,(gx,gy),big)
        except Exception: pass

    draw.line((55,height-78,width-55,height-78), fill=(23,56,79,190), width=2)
    draw.text((55,height-58), "P2P Guardian", font=footer_font, fill=(0,174,239,255))
    draw.text((165,height-58), "|  OSRS Discord Monitor  |  V24.2.5", font=footer_font, fill=(184,201,216,255))
    return img


def _guardian_alert_card(*, title, subtitle, description, accent=(0,174,239,255), badge="ALERT", border=None):
    """Render operational alerts using the same readable P2P Guardian visual language."""
    global _GUARDIAN_LOGO_CACHE
    width, height = 1400, 800
    img=Image.new("RGB",(width,height),GUARDIAN_BG); draw=ImageDraw.Draw(img,"RGBA")
    for y in range(height):
        t=y/max(1,height-1)
        draw.line((0,y,width,y),fill=(3+int(2*t),10+int(8*t),22+int(17*t),255))
    for offset in range(-500,1500,170):
        draw.line((offset,0,offset-320,height),fill=(0,143,217,18),width=2)
    draw.rounded_rectangle((16,16,width-16,height-16),radius=26,fill=(2,14,29,248),outline=(border or accent),width=3)
    draw.rounded_rectangle((32,32,width-32,height-32),radius=20,outline=(23,56,79,130),width=1)

    if _GUARDIAN_LOGO_CACHE is None:
        logo_path=Path(__file__).with_name("P2P_Guardian_Logo.png")
        if logo_path.exists():
            try: _GUARDIAN_LOGO_CACHE=Image.open(logo_path).convert("RGBA")
            except Exception: _GUARDIAN_LOGO_CACHE=False
    logo=_GUARDIAN_LOGO_CACHE if _GUARDIAN_LOGO_CACHE is not False else None

    title_font=_guardian_font(44,True); sub_font=_guardian_font(23,False)
    label_font=_guardian_font(22,True); value_font=_guardian_font(31,True)
    footer_font=_guardian_font(16,False); slogan_font=_guardian_font(22,True)

    def clean(text):
        text=str(text or "—")
        text=re.sub(r'[🟢🔴🟠⚪⚫🚨🖥️🔐📋🎯📍⏱️📄🧩🛡️🔎📅🏆🎉🔑🪟⚠️]', '', text)
        text=text.replace('**','').replace('`','')
        return re.sub(r'\s+',' ',text).strip() or '—'
    def wrap(text,font,max_width):
        words=clean(text).split(); lines=[]; cur=""
        for word in words:
            test=(cur+" "+word).strip()
            if draw.textbbox((0,0),test,font=font)[2] <= max_width: cur=test
            else:
                if cur: lines.append(cur)
                cur=word
        if cur: lines.append(cur)
        return lines or ["—"]

    def fit_font_alert(text, max_width, base=31, minimum=15, bold=True):
        text=clean(text)
        for size in range(base, minimum-1, -1):
            f=_guardian_font(size,bold)
            if draw.textbbox((0,0),text,font=f)[2] <= max_width:
                return f,text
        f=_guardian_font(minimum,bold)
        return f,clean(text)

    if logo is not None:
        sm=logo.copy(); sm.thumbnail((58,58),Image.Resampling.LANCZOS); img.paste(sm,(54,52),sm)
    brand_x = 130
    brand_y = 52
    brand = "P2P GUARDIAN"
    draw.text((brand_x,brand_y),brand,font=title_font,fill=(0,174,239,255),anchor="lt")
    brand_w = draw.textbbox((0,0), brand, font=title_font)[2]
    draw.text((brand_x + brand_w + 14,brand_y),"| OSRS MONITOR",font=title_font,fill=(242,246,250,255),anchor="lt")
    draw.rounded_rectangle((1050,57,1285,105),radius=18,fill=accent,outline=(210,240,255,220),width=1)
    badge_text=clean(badge)
    badge_font=label_font
    for sz in range(22,12,-1):
        candidate=_guardian_font(sz,True)
        if draw.textbbox((0,0),badge_text,font=candidate)[2] <= 215:
            badge_font=candidate; break
    tw=draw.textbbox((0,0),badge_text,font=badge_font)[2]
    draw.text((1167-tw/2,65),badge_text,font=badge_font,fill=(242,246,250,255))
    sub_font2, sub_text = fit_font_alert(subtitle, 1240, 23, 14, False)
    draw.text((55,116),sub_text,font=sub_font2,fill=(184,201,216,255))

    # Large title/detail panel. Details are intentionally white and spacious.
    draw.rounded_rectangle((55,165,825,650),radius=18,fill=(9,34,53,238),outline=(23,56,79,215),width=2)
    title_f, title_t = fit_font_alert(clean(title).upper(), 710, 44, 20, True)
    draw.text((82,195),title_t,font=title_f,fill=(242,246,250,255))
    draw.line((82,265,795,265),fill=(0,143,217,180),width=2)
    yy=292
    for raw in str(description or "—").splitlines():
        raw=raw.strip()
        if not raw: yy+=12; continue
        # Preserve useful label/value structure while removing markdown.
        m=re.match(r'\*\*([^*]+):\*\*\s*(.*)',raw)
        if m:
            label=clean(m.group(1))+":"; value=clean(m.group(2))
            draw.text((82,yy),label,font=label_font,fill=(205,228,247,255))
            lw=draw.textbbox((0,0),label,font=label_font)[2]
            vf, _ = fit_font_alert(value, 710-lw, 31, 15, True)
            lines=wrap(value,vf,710-lw)
            draw.text((95+lw,yy+1),lines[0],font=vf,fill=(242,246,250,255)); yy+=42
            for line in lines[1:]: draw.text((95,yy),line,font=vf,fill=(242,246,250,255)); yy+=40
        else:
            vf, _ = fit_font_alert(raw, 710, 31, 15, True)
            for line in wrap(raw,vf,710):
                draw.text((82,yy),line,font=vf,fill=(242,246,250,255)); yy+=40
        if yy>600: break

    if logo is not None:
        try:
            big=logo.copy(); big.thumbnail((430,430),Image.Resampling.LANCZOS)
            a=big.getchannel('A').point(lambda v:int(v*0.34)); big.putalpha(a)
            glow=Image.new('RGBA',big.size,(0,135,255,0)); glow.putalpha(a.filter(ImageFilter.GaussianBlur(20)))
            gx=900+(430-big.width)//2; gy=170
            img.paste(glow,(gx,gy),glow); img.paste(big,(gx,gy),big)
        except Exception: pass
    draw.text((970,555),"PLAY SMARTER",font=slogan_font,fill=(0,174,239,245))
    draw.text((992,587),"STAY SAFER",font=slogan_font,fill=(0,174,239,245))
    draw.line((965,625,1135,606),fill=(0,174,255,230),width=3)
    draw.line((55,height-78,width-55,height-78),fill=(23,56,79,190),width=2)
    draw.text((55,height-58),"P2P Guardian",font=footer_font,fill=(0,174,239,255))
    draw.text((165,height-58),"|  OSRS Discord Monitor  |  V24.2.5",font=footer_font,fill=(184,201,216,255))
    return img


async def _send_guardian_card(channel, card, filename="guardian_event.png"):
    buffer=io.BytesIO()
    card.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    await channel.send(file=discord.File(buffer, filename=filename))


def _guardian_embed_card(embed, width=1200, height=760):
    """Render command responses as adaptive, high-contrast Guardian cards.

    The card grows vertically when real data is longer than the demo. Nothing is
    silently squeezed into a tiny font or clipped just because a PID, client title,
    log line, or diagnostic message is unusually long.
    """
    global _GUARDIAN_LOGO_CACHE

    def clean_line(text):
        text = str(text or "—")
        text = re.sub(r'[🟢🔴🟠⚪⚫🚨🖥️🔐📋🎯📍⏱️📄🧩🛡️🔎📅🏆🎉🔑🪟⚠️❌🧹🎮🧭📂🔧]', '', text)
        text = text.replace('**', '').replace('`', '')
        return re.sub(r'[ \t]+', ' ', text).strip() or '—'

    def clean_multiline(text):
        raw = str(text or "—").replace('\r\n', '\n').replace('\r', '\n')
        lines = [clean_line(line) for line in raw.split('\n')]
        return [line for line in lines if line] or ['—']

    # Fonts are deliberately kept large. Discord scales the final image to the
    # channel width, so increasing the canvas height is preferable to shrinking text.
    title_font = _guardian_font(31, True)
    subtitle_font = _guardian_font(17, False)
    label_font = _guardian_font(19, True)
    value_font = _guardian_font(27, True)
    body_font = _guardian_font(22, False)
    footer_font = _guardian_font(14, False)
    badge_font = _guardian_font(17, True)

    # We calculate content height before drawing so long values can expand the card.
    left = 52
    right = 820
    usable_w = right - left
    fields = list(getattr(embed, 'fields', []) or [])
    raw_title = clean_line(embed.title or "P2P Guardian")
    description_lines = clean_multiline(embed.description or "") if embed.description else []

    def wrap_line(text, font, max_width):
        text = clean_line(text)
        words = text.split()
        if not words:
            return ['—']
        lines, cur = [], ''
        for word in words:
            # Break an individual overlong token instead of letting it disappear.
            if not cur and draw_for_measure(text='', font=font, sample=word, max_width=max_width) is False:
                piece = ''
                for ch in word:
                    test = piece + ch
                    if draw_for_measure(text='', font=font, sample=test, max_width=max_width):
                        piece = test
                    else:
                        if piece:
                            lines.append(piece)
                        piece = ch
                cur = piece
                continue
            test = (cur + ' ' + word).strip()
            if draw_for_measure(text='', font=font, sample=test, max_width=max_width):
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines or ['—']

    # PIL measurement helper is local so the wrapping code stays readable.
    measure_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    def draw_for_measure(text, font, sample, max_width):
        return measure_draw.textbbox((0, 0), sample, font=font)[2] <= max_width

    # Header/description height.
    y = 112
    if description_lines:
        for line in description_lines:
            y += min(3, len(wrap_line(line, subtitle_font, width - 110))) * 24
        y += 10
    else:
        y = 112

    field_layout = []
    if "COMMANDS" in raw_title.upper():
        # Help is a catalogue. Use three columns and enough rows to show every command.
        items = []
        for field in fields:
            group = clean_line(getattr(field, 'name', ''))
            for raw in str(getattr(field, 'value', '') or '').splitlines():
                line = clean_line(raw)
                if line:
                    items.append((group, line))
        col_gap = 14
        col_w = (usable_w - 2 * col_gap) // 3
        card_h = 70
        rows = max(1, (len(items) + 2) // 3)
        y_end = y + rows * (card_h + 9)
        height = max(height, y_end + 105)
    else:
        # Every field gets enough height for all wrapped lines. No two-line truncation.
        for field in fields:
            label = clean_line(getattr(field, 'name', 'Field'))
            value_lines = []
            for raw in str(getattr(field, 'value', '—') or '—').replace('\r\n','\n').replace('\r','\n').split('\n'):
                value_lines.extend(wrap_line(raw, value_font, usable_w - 40))
            value_lines = value_lines or ['—']
            # Keep an individual card readable; fields are already limited by Discord.
            visible_lines = value_lines[:16]
            h = 62 + len(visible_lines) * 30
            if len(value_lines) > len(visible_lines):
                visible_lines[-1] = visible_lines[-1].rstrip('.') + '...'
            field_layout.append((label, visible_lines, h))
            y += h + 12
        height = max(height, y + 95)

    # Keep images reasonably sized while allowing genuinely large diagnostic output.
    height = min(max(height, 760), 1800)

    img = Image.new('RGBA', (width, height), (3, 10, 22, 255))
    draw = ImageDraw.Draw(img, 'RGBA')
    for yy in range(height):
        t = yy / max(1, height - 1)
        draw.line((0, yy, width, yy), fill=(3 + int(2*t), 11 + int(8*t), 23 + int(17*t), 255))
    for offset in range(-420, width + 500, 150):
        draw.line((offset, 0, offset - 260, height), fill=(0, 150, 255, 18), width=2)

    accent = (0, 174, 255, 255)
    try:
        rgb = embed.color.to_rgb() if embed.color and embed.color.value else (0, 174, 255)
        accent = tuple(rgb) + (255,)
    except Exception:
        pass
    draw.rounded_rectangle((12, 12, width-12, height-12), radius=24,
                           fill=(6, 26, 41, 250), outline=accent, width=3)
    draw.rounded_rectangle((28, 28, width-28, height-28), radius=18,
                           outline=(42, 105, 160, 130), width=1)

    if _GUARDIAN_LOGO_CACHE is None:
        logo_path = Path(__file__).with_name('P2P_Guardian_Logo.png')
        if logo_path.exists():
            try:
                _GUARDIAN_LOGO_CACHE = Image.open(logo_path).convert('RGBA')
            except Exception:
                _GUARDIAN_LOGO_CACHE = False
    logo = _GUARDIAN_LOGO_CACHE if _GUARDIAN_LOGO_CACHE is not False else None

    # Header.
    if logo is not None:
        try:
            sm = logo.copy(); sm.thumbnail((46, 46), Image.Resampling.LANCZOS)
            img.paste(sm, (45, 42), sm)
        except Exception:
            pass
    brand_x = 104
    brand_y = 43
    brand = 'P2P GUARDIAN'
    draw.text((brand_x, brand_y), brand, font=title_font, fill=(55, 195, 255, 255), anchor="lt")
    brand_w = draw.textbbox((0,0), brand, font=title_font)[2]
    draw.text((brand_x + brand_w + 14, brand_y), '| OSRS MONITOR', font=title_font, fill=(242, 247, 255, 255), anchor="lt")

    # Adaptive badge: never let the command name run outside the badge.
    badge = raw_title.upper()
    bx, by, bw, bh = width - 262, 45, 210, 43
    size = 17
    while size > 10 and ImageDraw.Draw(Image.new('RGB',(1,1))).textbbox((0,0), badge, font=_guardian_font(size, True))[2] > bw - 20:
        size -= 1
    badge_f = _guardian_font(size, True)
    badge_display = badge
    if ImageDraw.Draw(Image.new('RGB',(1,1))).textbbox((0,0), badge_display, font=badge_f)[2] > bw - 20:
        badge_display = badge_display[:28].rstrip() + '...'
    draw.rounded_rectangle((bx, by, bx+bw, by+bh), radius=15, fill=accent,
                           outline=(210, 240, 255, 220), width=1)
    tw = draw.textbbox((0,0), badge_display, font=badge_f)[2]
    draw.text((bx + (bw-tw)/2, 55), badge_display, font=badge_f, fill=(242,246,250,255))

    # Description.
    yy = 94
    for line in description_lines:
        for wrapped in wrap_line(line, subtitle_font, width - 110)[:3]:
            draw.text((55, yy), wrapped, font=subtitle_font, fill=(220, 238, 255, 255))
            yy += 24
    y = yy + 12 if description_lines else 112

    # Right-side watermark zone.
    if logo is not None:
        try:
            big = logo.copy(); big.thumbnail((390, 390), Image.Resampling.LANCZOS)
            a = big.getchannel('A').point(lambda v: int(v * 0.34)); big.putalpha(a)
            glow = Image.new('RGBA', big.size, (0, 135, 255, 0)); glow.putalpha(a.filter(ImageFilter.GaussianBlur(18)))
            gx = 875 + (390-big.width)//2
            gy = 145 if height <= 900 else 155
            img.paste(glow, (gx, gy), glow); img.paste(big, (gx, gy), big)
        except Exception:
            pass
    slogan_y = min(max(535, height - 300), height - 160)
    draw.text((900, slogan_y), 'PLAY SMARTER', font=_guardian_font(18, True), fill=(120, 220, 255, 245))
    draw.text((920, slogan_y + 27), 'STAY SAFER', font=_guardian_font(18, True), fill=(120, 220, 255, 245))
    draw.line((895, slogan_y + 57, 1070, slogan_y + 38), fill=(0, 174, 255, 230), width=3)

    if "COMMANDS" in raw_title.upper():
        compact_font = _guardian_font(18, True)
        small_font = _guardian_font(15, False)
        col_gap = 14
        col_w = (usable_w - 2 * col_gap) // 3
        items = []
        for field in fields:
            group = clean_line(getattr(field, 'name', ''))
            for raw in str(getattr(field, 'value', '') or '').splitlines():
                line = clean_line(raw)
                if line:
                    items.append((group, line))
        rows = max(1, (len(items) + 2) // 3)
        for i, (group, line) in enumerate(items):
            col = i % 3
            row = i // 3
            x = left + col * (col_w + col_gap)
            box_y = y + row * 79
            draw.rounded_rectangle((x, box_y, x+col_w, box_y+70), radius=10,
                                   fill=(9,34,53,238), outline=(23,56,79,215), width=2)
            draw.text((x+12, box_y+7), group.upper(), font=small_font, fill=(0,143,217,255))
            m = re.match(r'/?([^ ]+)\s*[—-]\s*(.*)', line)
            if m:
                command = '/' + m.group(1).lstrip('/')
                desc = m.group(2)
                draw.text((x+12, box_y+27), command, font=compact_font, fill=(242,246,250,255))
                desc_lines = wrap_line(desc, small_font, col_w-24)
                if desc_lines:
                    draw.text((x+12, box_y+49), desc_lines[0], font=small_font, fill=(184,201,216,255))
            else:
                for j, txt in enumerate(wrap_line(line, small_font, col_w-24)[:2]):
                    draw.text((x+12, box_y+27+j*20), txt, font=small_font, fill=(242,246,250,255))
    elif not fields:
        panel_h = min(max(180, height - y - 105), 600)
        draw.rounded_rectangle((left, y, right, y+panel_h), radius=16,
                               fill=(9,34,53,238), outline=(23,56,79,215), width=2)
        draw.text((left+22, y+18), raw_title.upper(), font=label_font, fill=(242,246,250,255))
        yy2 = y + 58
        for raw in description_lines or ['No additional information.']:
            for line in wrap_line(raw, body_font, usable_w-44):
                draw.text((left+22, yy2), line, font=body_font, fill=(242,246,250,255)); yy2 += 34
    else:
        for label, lines, h in field_layout:
            draw.rounded_rectangle((left, y, right, y+h), radius=12,
                                   fill=(9,34,53,238), outline=(23,56,79,215), width=2)
            draw.text((left+18, y+11), label.upper(), font=label_font, fill=(184,201,216,255))
            yy2 = y + 42
            for line in lines:
                draw.text((left+18, yy2), line, font=value_font, fill=(242,246,250,255)); yy2 += 30
            y += h + 12

    footer_y = height - 58
    draw.line((50, footer_y-18, width-50, footer_y-18), fill=(23,56,79,190), width=2)
    draw.text((52, footer_y), 'P2P Guardian', font=footer_font, fill=(0,174,239,255))
    draw.text((155, footer_y), '|  OSRS Discord Monitor  |  V24.2.5', font=footer_font, fill=(184,201,216,255))
    stamp = datetime.now().strftime('%d-%m-%Y %H:%M')
    sw = draw.textbbox((0,0), stamp, font=footer_font)[2]
    draw.text((width-52-sw, footer_y), stamp, font=footer_font, fill=(184,201,216,255))
    return img

def _guardian_screenshot_card(label, screenshot):
    """Render Startup/Periodic screenshots in the same P2P Guardian visual system."""
    global _GUARDIAN_LOGO_CACHE
    width, height = 1200, 760
    img=Image.new('RGBA',(width,height),(3,10,22,255)); draw=ImageDraw.Draw(img,'RGBA')
    for y in range(height):
        t=y/max(1,height-1)
        draw.line((0,y,width,y),fill=(3+int(2*t),11+int(8*t),23+int(17*t),255))
    for offset in range(-420,width+500,150):
        draw.line((offset,0,offset-260,height),fill=(0,143,217,18),width=2)
    draw.rounded_rectangle((12,12,width-12,height-12),radius=24,fill=(6,26,41,250),outline=(0, 174, 239, 255),width=3)
    draw.rounded_rectangle((28,28,width-28,height-28),radius=18,outline=(23,56,79,130),width=1)

    if _GUARDIAN_LOGO_CACHE is None:
        logo_path=Path(__file__).with_name('P2P_Guardian_Logo.png')
        if logo_path.exists():
            try: _GUARDIAN_LOGO_CACHE=Image.open(logo_path).convert('RGBA')
            except Exception: _GUARDIAN_LOGO_CACHE=False
    logo=_GUARDIAN_LOGO_CACHE if _GUARDIAN_LOGO_CACHE is not False else None

    title_font=_guardian_font(30,True); sub_font=_guardian_font(17,False)
    label_font=_guardian_font(20,True); footer_font=_guardian_font(14,False)
    if logo is not None:
        sm=logo.copy(); sm.thumbnail((46,46),Image.Resampling.LANCZOS); img.paste(sm,(45,42),sm)
    brand_x = 104
    brand_y = 43
    brand = 'P2P GUARDIAN'
    draw.text((brand_x,brand_y),brand,font=title_font,fill=(0,174,239,255),anchor="lt")
    brand_w = draw.textbbox((0,0), brand, font=title_font)[2]
    draw.text((brand_x + brand_w + 14,brand_y),'| OSRS MONITOR',font=title_font,fill=(242,246,250,255),anchor="lt")
    draw.rounded_rectangle((920,45,1148,88),radius=15,fill=(0, 174, 239, 255))
    label_upper = label.upper()
    if 'STARTUP' in label_upper:
        badge = 'STARTUP'
    elif 'MANUAL' in label_upper:
        badge = 'MANUAL'
    else:
        badge = 'AUTOMATIC'
    badge_font=_guardian_font(17,True)
    for sz in range(17,10,-1):
        candidate=_guardian_font(sz,True)
        if draw.textbbox((0,0),badge,font=candidate)[2] <= 208:
            badge_font=candidate; break
    tw=draw.textbbox((0,0),badge,font=badge_font)[2]
    draw.text((1034-tw/2,55),badge,font=badge_font,fill=(242,246,250,255))
    clean_text=re.sub(r'\s+',' ',str(label)).strip()
    sub_font_dynamic=sub_font
    for sz in range(17,11,-1):
        candidate=_guardian_font(sz,False)
        if draw.textbbox((0,0),clean_text,font=candidate)[2] <= 840:
            sub_font_dynamic=candidate; break
    if draw.textbbox((0,0),clean_text,font=sub_font_dynamic)[2] > 840:
        suffix='...'; tmp=clean_text
        while len(tmp)>1 and draw.textbbox((0,0),tmp+suffix,font=sub_font_dynamic)[2] > 840:
            tmp=tmp[:-1]
        clean_text=tmp.rstrip()+suffix
    draw.text((55,96),clean_text,font=sub_font_dynamic,fill=(184,201,216,255))

    # Screenshot is deliberately large and left-aligned; the right side is branding only.
    max_w,max_h=760,500
    shot=screenshot.convert('RGB')
    shot.thumbnail((max_w,max_h),Image.Resampling.LANCZOS)
    sx,sy=55,135
    draw.rounded_rectangle((sx-5,sy-5,sx+shot.width+5,sy+shot.height+5),radius=10,fill=(0,0,0,255),outline=(23,56,79,220),width=2)
    img.paste(shot,(sx,sy))

    if logo is not None:
        try:
            big=logo.copy(); big.thumbnail((320,320),Image.Resampling.LANCZOS)
            a=big.getchannel('A').point(lambda v:int(v*0.40)); big.putalpha(a)
            glow=Image.new('RGBA',big.size,(0,135,255,0)); glow.putalpha(a.filter(ImageFilter.GaussianBlur(16)))
            gx=825+(320-big.width)//2; gy=170
            img.paste(glow,(gx,gy),glow); img.paste(big,(gx,gy),big)
        except Exception: pass
    draw.text((875,500),'P2P Guardian',font=_guardian_font(22,True),fill=(0,174,239,255))
    draw.text((875,532),'OSRS DISCORD MONITOR',font=_guardian_font(17,False),fill=(184,201,216,255))
    draw.text((875,575),'PLAY SMARTER',font=_guardian_font(18,True),fill=(0,174,239,245))
    draw.text((900,603),'STAY SAFER',font=_guardian_font(18,True),fill=(0,174,239,245))

    footer_y=height-58
    draw.line((50,footer_y-18,width-50,footer_y-18),fill=(23,56,79,190),width=2)
    draw.text((52,footer_y),'P2P Guardian',font=footer_font,fill=(0,174,239,255))
    draw.text((155,footer_y),'|  OSRS Discord Monitor  |  V24.2.5',font=footer_font,fill=(184,201,216,255))
    draw.text((width-225,footer_y),datetime.now().strftime('%d-%m-%Y %H:%M'),font=footer_font,fill=(184,201,216,255))
    return img

async def _send_guardian_embed_response(interaction, embed, **kwargs):
    """Send a command card and optionally one or more extra attachments."""
    card = _guardian_embed_card(embed)
    buffer = io.BytesIO(); card.save(buffer, format="PNG", optimize=True); buffer.seek(0)
    kwargs.pop("embed", None)
    extra_files = []
    if "file" in kwargs:
        extra_files.append(kwargs.pop("file"))
    extra_files.extend(kwargs.pop("files", []) or [])
    files = [discord.File(buffer, filename="guardian_command.png")] + extra_files
    await interaction.followup.send(files=files, **kwargs)

async def _send_guardian_response_embed(interaction, embed, **kwargs):
    card = _guardian_embed_card(embed)
    buffer = io.BytesIO(); card.save(buffer, format="PNG", optimize=True); buffer.seek(0)
    kwargs.pop("embed", None)
    extra_files = []
    if "file" in kwargs:
        extra_files.append(kwargs.pop("file"))
    extra_files.extend(kwargs.pop("files", []) or [])
    files = [discord.File(buffer, filename="guardian_command.png")] + extra_files
    await interaction.response.send_message(files=files, **kwargs)

def guardian_embed(title=None, description=None, color=GUARDIAN_DISCORD_COLOR):
    """Create the standard P2P Guardian Discord embed style."""
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_author(
        name="P2P GUARDIAN | OSRS MONITOR",
        icon_url=GUARDIAN_LOGO_URL,
    )
    embed.set_thumbnail(url=GUARDIAN_LOGO_URL)
    embed.set_footer(text=GUARDIAN_FOOTER)
    embed.timestamp = discord.utils.utcnow()
    return embed


def _recent_logout_alert_exists(pid=None):
    """Return True when any logout monitor already alerted very recently."""
    now = time.time()
    keys = []
    if pid is not None:
        keys.append(("pid", pid))
    keys.extend(_last_logout_alert_at.keys())
    seen = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        value = _last_logout_alert_at.get(key)
        if value is not None and now - value <= LOGOUT_CONFIRM_WINDOW_SECONDS:
            return True
    return False


async def _send_client_alert(title, description, *, color=GUARDIAN_DISCORD_COLOR, ping=False):
    """Send all operational client/login alerts as branded Guardian image cards."""
    if NOTIFY_CHANNEL_ID is None:
        _record_monitor_error("Discord alerts", "NOTIFY_CHANNEL_ID is not configured")
        return
    channel = client.get_channel(NOTIFY_CHANNEL_ID)
    if channel is None:
        _record_monitor_error("Discord alerts", f"Channel {NOTIFY_CHANNEL_ID} was not found in the bot cache")
        return

    try:
        accent = color.to_rgb() + (255,) if hasattr(color, "to_rgb") else (0,174,239,255)
        lower=clean_title= re.sub(r'[^A-Za-z0-9 ]+',' ',str(title or '')).strip().upper()
        if 'LOGIN' in lower and 'LOGOUT' not in lower:
            badge='LOGIN'; subtitle='P2P Guardian confirmed the OSRS client returned to the game.'
        elif 'LOGOUT' in lower or 'STOPPED' in lower:
            badge='LOGOUT'; subtitle='P2P Guardian detected that the OSRS client left the game.'
        elif 'FROZEN' in lower:
            badge='WARNING'; subtitle='P2P Guardian detected a possible OSRS client freeze.'
        elif 'RESPONDING' in lower:
            badge='RECOVERED'; subtitle='P2P Guardian detected that the OSRS client is responding again.'
        elif 'CLOSED' in lower:
            badge='CLOSED'; subtitle='P2P Guardian detected that an OSRS client closed.'
        elif 'ERROR' in lower:
            badge='ERROR'; subtitle='P2P Guardian detected an OSRS-related Windows error.'
        else:
            badge='ALERT'; subtitle='P2P Guardian detected an OSRS monitoring event.'
        if badge == "LOGIN":
            accent = (77,219,131,255)
        elif badge == "LOGOUT":
            accent = (255,76,76,255)
        alert_border = (0,174,239,255) if badge in {"LOGIN", "LOGOUT"} else None
        card=_guardian_alert_card(title=title, subtitle=subtitle, description=description, accent=accent, badge=badge, border=alert_border)
        buffer=io.BytesIO(); card.save(buffer,format='PNG',optimize=True); buffer.seek(0)
        content=f"<@{PING_USER_ID}>" if ping and PING_USER_ID is not None else None
        await channel.send(content=content, file=discord.File(buffer, filename="guardian_alert.png"))
    except Exception as exc:
        _record_monitor_error("Discord alerts", exc)


@tasks.loop(seconds=2.0)
async def monitor_login_screen_per_client():
    """Warm up visual login state one client at a time, never from /status.

    This is deliberately serialized. A machine running many OSRS clients must
    never restore/capture all windows at once. Log-based login events remain the
    normal source after the initial visual bootstrap check.
    """
    clients = _get_osrs_clients()
    if not clients:
        _login_visual_bootstrap_pending.clear()
        return

    live_pids = {int(info["pid"]) for info in clients if info.get("pid") is not None}
    _login_visual_bootstrap_pending.intersection_update(live_pids)

    # New/restarted clients get one visual check so a client that was already
    # open on the Play Now screen when Guardian started is corrected. Never run
    # more than one capture/OCR operation per loop tick.
    for info in sorted(clients, key=lambda item: int(item.get("pid", 0))):
        pid = info.get("pid")
        if pid is None:
            continue
        if pid not in _login_visual_bootstrap_pending:
            _login_visual_bootstrap_pending.add(pid)
            # Only one client is processed per tick.
            visual_login = _detect_login_screen_from_window(info)
            _login_visual_checked_at_by_pid[pid] = time.time()
            if visual_login is True:
                _login_state_by_pid[pid] = "login_screen"
                known = _known_clients.setdefault(pid, {})
                known["persistent_state"] = "login_screen"
                known["last_state_source"] = "background window OCR / Play Now"
                _save_persistent_client_states()
            elif visual_login is False:
                # A clean visual negative confirms that the old persisted
                # login-screen state is stale. Do not invent a logged-in state;
                # the normal log monitor will confirm login separately.
                if _login_state_by_pid.get(pid) == "login_screen":
                    _login_state_by_pid[pid] = "unknown"
                known = _known_clients.setdefault(pid, {})
                known["last_state_source"] = "background window OCR / no login screen"
            break

    # Forget dead PIDs from the bootstrap queue.
    for pid in list(_login_visual_checked_at_by_pid):
        if pid not in live_pids:
            _login_visual_checked_at_by_pid.pop(pid, None)


@monitor_login_screen_per_client.before_loop
async def before_monitor_login_screen_per_client():
    await client.wait_until_ready()


@monitor_login_screen_per_client.error
async def monitor_login_screen_per_client_error(error):
    _record_monitor_error("per-client login bootstrap", error)
    await asyncio.sleep(2)
    if not monitor_login_screen_per_client.is_running():
        monitor_login_screen_per_client.restart()


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
                    color=GUARDIAN_SUCCESS_COLOR,
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
            if _recent_logout_alert_exists(pid):
                state["closed_alerted"] = True
                _client_health.pop(pid, None)
                _client_closed_candidates.pop(pid, None)
                continue
            state["closed_alerted"] = True
            _last_logout_alert_at[("pid", pid)] = time.time()
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
                color=GUARDIAN_DISCORD_COLOR,
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
            color=GUARDIAN_DISCORD_COLOR,
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
            color=GUARDIAN_SUCCESS_COLOR,
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
            color=GUARDIAN_DISCORD_COLOR,
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
            color=GUARDIAN_DISCORD_COLOR,
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
            color=GUARDIAN_SUCCESS_COLOR,
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
    """Tail ALL client log files and remember the most recently active log.

    The status page must still show the active log when the file has not
    received a new line since the bot started.  Candidate logs are therefore
    selected by filesystem activity first, while all candidates are still
    tailed for event detection.
    """
    global _log_current_file
    files = _candidate_log_files()
    if not files:
        _log_current_file = None
        return []

    # _candidate_log_files() is newest-first.  Keep the newest existing log
    # as the current/active log even when there is no newly appended line.
    try:
        active_candidates = [p for p in files if p.is_file()]
        if active_candidates:
            _log_current_file = max(active_candidates, key=lambda p: p.stat().st_mtime)
    except OSError:
        pass

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
    """Extract only explicit task-level failure/skip reasons.

    Normal resource/equipment diagnostics are deliberately ignored here. They
    become a Discord task error only when the log explicitly indicates that the
    task could not proceed/was skipped.
    """
    lower = message.lower()

    if "can't do this slayer task" in lower:
        return "Slayer task cannot be done with the current requirements"

    if "failed for the reasons above" in lower:
        return _shorten(message)

    if "failed to traverse last mile" in lower:
        return "Could not reach the destination"

    if "i can't reach that" in lower:
        return "Could not reach the destination"

    if "something is missing - skipping withdraw" in lower:
        return "Required item/resource was missing"

    if "one or more requirements are missing" in lower:
        return _shorten(message)

    if "no combat styles available" in lower:
        return "No suitable combat style available"

    if "able to start: false" in lower:
        return "Task could not be started"

    # A generic 'Skipping <item>: untradeable' line is an item-filter decision,
    # not proof that the current task was skipped. Never report it as a task error.
    return None


def _choose_failure_reason_for_log(log_key, before_timestamp=None):
    failures = _log_failure_reasons_by_log.get(log_key, ())
    if not failures:
        return None
    if before_timestamp is None:
        return failures[-1][0]
    for reason, failure_timestamp in reversed(failures):
        if failure_timestamp is None or before_timestamp is None:
            return reason
        age = (before_timestamp - failure_timestamp).total_seconds()
        if 0 <= age <= TASK_FAILURE_CONTEXT_SECONDS:
            return reason
        if age > TASK_FAILURE_CONTEXT_SECONDS:
            break
    return None


def _parse_task_target(message):
    """Extract the actual Slayer target when the log exposes it.

    Common Detuks-style task lines include:
      Slayer -> 11 Dust devil
      Slayer -> Dust devil
      Target: Dust devil
      Target is Dust devil

    The numeric assignment count is deliberately removed from the target.
    """
    patterns = (
        r"\bSlayer\s*[-=]?>\s*(?:\d+\s+)?(.+?)\s*$",
        r"\bTarget\s*(?:is|:)\s*(.+?)\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            target = re.sub(r"^\s*\d+\s+", "", match.group(1).strip())
            target = re.sub(r"\s+for about\s+[0-9]+(?:\.[0-9]+)?\s+minutes?\s*$", "", target, flags=re.IGNORECASE)
            if target:
                return target
    return None


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


async def _send_task_embed(*, event_time, task, activity=None, target=None, location=None,
                     log_file=None, account=None, client_pid=None,
                     error_reason=None, skipped_task=None):
    if TASK_NOTIFY_CHANNEL_ID is None:
        return None
    channel = client.get_channel(TASK_NOTIFY_CHANNEL_ID)
    if channel is None:
        return None

    if error_reason and skipped_task:
        fields = [
            ("Account", account or "Unknown client"),
            ("Task", skipped_task),
            ("Detail", _shorten(error_reason)),
        ]
        if client_pid is not None:
            fields.append(("PID", str(client_pid)))
        card = _guardian_event_card(
            title="TASK ERROR",
            subtitle="P2P Guardian detected a task-level error before a new task was assigned.",
            fields=fields,
            accent=(255,76,76,255),
            badge="ERROR",
        )
        await _send_guardian_card(channel, card, "task_error.png")

    fields = [("Account", account or "Unknown client"), ("Task", task or "Unknown")]
    if activity:
        fields.append(("Activity", activity))
    if target:
        fields.append(("Target", target))
    if location:
        fields.append(("Location", location))
    if client_pid is not None:
        fields.append(("PID", str(client_pid)))

    card = _guardian_event_card(
        title="TASK STARTED",
        subtitle="P2P Guardian detected a new task.",
        fields=fields,
        accent=(0,174,239,255),
        badge="TASK",
    )
    await _send_guardian_card(channel, card, "task_started.png")



async def _send_level_up_embed(*, event_time, skill=None, new_level=None, total_level=None, log_file=None):
    """Send a high-contrast P2P Guardian level-up card."""
    target_channel_id = LEVEL_NOTIFY_CHANNEL_ID or TASK_NOTIFY_CHANNEL_ID
    if target_channel_id is None:
        return None
    channel = client.get_channel(target_channel_id)
    if channel is None:
        return None

    if total_level is not None:
        title="TOTAL LEVEL UP"
        fields=[("Total Level", str(total_level))]
    else:
        title="LEVEL UP"
        fields=[("Skill", skill or "Unknown"), ("New Level", str(new_level) if new_level is not None else "Unknown")]
    if event_time: fields.append(("Time", _format_timestamp(event_time)))

    card=_guardian_event_card(title=title, subtitle="Congratulations! Your progress has been recorded.", fields=fields, accent=(60,210,150,255), badge="LEVEL UP")
    await _send_guardian_card(channel, card, "level_up.png")



async def _handle_log_line(line, log_path=None):
    """Process one new line, keeping task state isolated per log file."""
    global _current_task, _current_task_started, _current_task_duration_minutes
    global _current_task_activity, _current_task_location, _current_task_target, _current_task_last_log_file
    global _current_task_last_update, _next_play_length_hours, _next_break_length_hours

    timestamp = _parse_log_timestamp(line)
    message = _log_message(line)
    global _log_current_file
    if log_path is not None:
        _log_current_file = log_path
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
        previous_failure = _choose_failure_reason_for_log(log_key, timestamp or datetime.now())
        previous_task = _current_task if _current_task_last_log_file == log_name else None
        task_client = _resolve_task_client(log_path)
        task_pid = task_client.get("pid") if task_client else None
        task_account = _client_label(task_client) if task_client else "Unknown client"
        _log_pending_tasks[log_key] = {
            "timestamp": timestamp or datetime.now(),
            "task": None,
            "activity": None,
            "target": None,
            "location": None,
            "duration_minutes": None,
            "failure_reason": previous_failure if previous_task else None,
            "previous_task": previous_task,
            "account": task_account,
            "client_pid": task_pid,
            "log_file": log_name,
        }
        # Failure context is consumed at this task transition. It is not a
        # persistent error and cannot fire an alert by itself.
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

    match = re.search(r"Location\s*(?:is|:|=|->)\s*(.+)$", message, re.IGNORECASE)
    if match:
        pending["location"] = match.group(1).strip()

    target = _parse_task_target(message)
    if target:
        pending["target"] = target

    selected = _parse_selected_task(message)
    if selected:
        pending.update(selected)

    enough = pending["task"] is not None and (
        pending["duration_minutes"] is not None or pending["activity"] is not None
    )
    # Slayer task notifications are only emitted once the actual target and
    # destination are known. This prevents an early card showing only
    # "Slayer / Nieve" while the log has not yet supplied Dust devil and the
    # Slayer location.
    if pending["task"].strip().lower() == "slayer":
        enough = enough and pending.get("target") is not None and pending.get("location") is not None
    if not enough:
        return

    event_key = (
        log_key, pending["timestamp"], pending["task"], pending["activity"],
        pending.get("target"), pending["location"], pending["duration_minutes"],
    )
    if event_key == _log_last_task_event_keys.get(log_key):
        return

    previous_task = pending.get("previous_task")

    _current_task = pending["task"]
    _current_task_started = pending["timestamp"]
    _current_task_duration_minutes = pending["duration_minutes"]
    _current_task_activity = pending["activity"]
    _current_task_location = pending["location"]
    _current_task_target = pending.get("target")
    _current_task_last_log_file = log_name
    _current_task_last_update = timestamp or pending["timestamp"]
    # Keep the latest complete task context per log after the pending entry is
    # consumed. /status can then show the correct task for the PID that owns
    # that log instead of falling back to one global task.
    _last_task_by_log[log_key] = dict(pending)
    _last_task_by_log[log_key]["last_update"] = timestamp or pending["timestamp"]
    _log_last_task_event_keys[log_key] = event_key

    skipped_reason = pending.get("failure_reason")
    if skipped_reason and previous_task:
        await _send_task_embed(
            event_time=pending["timestamp"],
            task=pending["task"],
            activity=pending["activity"],
            target=pending.get("target"),
            location=pending["location"],
            log_file=log_name,
            account=pending.get("account"),
            client_pid=pending.get("client_pid"),
            error_reason=skipped_reason,
            skipped_task=previous_task,
        )
    else:
        await _send_task_embed(
            event_time=pending["timestamp"],
            task=pending["task"],
            activity=pending["activity"],
            target=pending.get("target"),
            location=pending["location"],
            log_file=log_name,
            account=pending.get("account"),
            client_pid=pending.get("client_pid"),
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
                card=_guardian_alert_card(
                    title="OSRS Client Stopped",
                    subtitle="P2P Guardian detected that the OSRS client left the game.",
                    description=message,
                    accent=(255,85,85,255),
                    badge="LOGOUT",
                    border=(0,174,239,255),
                )
                card_buf=io.BytesIO(); card.save(card_buf, format="PNG", optimize=True); card_buf.seek(0)
                await channel.send(
                    content=(f"<@{PING_USER_ID}>" if PING_USER_ID is not None else None),
                    files=[discord.File(card_buf, filename="guardian_alert.png"), discord.File(buffer, filename="logout_screenshot.png")],
                )
            except Exception as exc:
                card=_guardian_alert_card(
                    title="OSRS Client Stopped",
                    subtitle="P2P Guardian detected that the OSRS client left the game.",
                    description=f"{message}\n\nCould not take a screenshot: {str(exc)[:500]}",
                    accent=(255,85,85,255),
                    badge="LOGOUT",
                    border=(0,174,239,255),
                )
                card_buf=io.BytesIO(); card.save(card_buf, format="PNG", optimize=True); card_buf.seek(0)
                await channel.send(content=(f"<@{PING_USER_ID}>" if PING_USER_ID is not None else None), file=discord.File(card_buf, filename="guardian_alert.png"))

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
        if _recent_logout_alert_exists():
            _login_pixel_was_visible = visible
            return
        _last_logout_alert_at["ocr"] = time.time()
        channel = client.get_channel(NOTIFY_CHANNEL_ID)
        if channel is not None:
            ping = f"<@{PING_USER_ID}> " if PING_USER_ID is not None else ""
            message = f"{ping}🔑 Login screen detected — you have been logged out of OSRS!"
            try:
                screenshot = ImageGrab.grab()
                buffer = io.BytesIO()
                screenshot.save(buffer, format="PNG")
                buffer.seek(0)
                card=_guardian_alert_card(
                    title="OSRS Client Stopped",
                    subtitle="P2P Guardian detected that the OSRS client left the game.",
                    description=message,
                    accent=(255,85,85,255),
                    badge="LOGOUT",
                    border=(0,174,239,255),
                )
                card_buf=io.BytesIO(); card.save(card_buf, format="PNG", optimize=True); card_buf.seek(0)
                await channel.send(
                    content=(f"<@{PING_USER_ID}>" if PING_USER_ID is not None else None),
                    files=[discord.File(card_buf, filename="guardian_alert.png"), discord.File(buffer, filename="logout_screenshot.png")],
                )
            except Exception as exc:
                card=_guardian_alert_card(
                    title="OSRS Client Stopped",
                    subtitle="P2P Guardian detected that the OSRS client left the game.",
                    description=f"{message}\n\nCould not take a screenshot: {str(exc)[:500]}",
                    accent=(255,85,85,255),
                    badge="LOGOUT",
                    border=(0,174,239,255),
                )
                card_buf=io.BytesIO(); card.save(card_buf, format="PNG", optimize=True); card_buf.seek(0)
                await channel.send(content=(f"<@{PING_USER_ID}>" if PING_USER_ID is not None else None), file=discord.File(card_buf, filename="guardian_alert.png"))

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
# Screenshot check-ins
# ---------------------------------------------------------------------------

async def send_monitor_screenshot(label="Periodic Check-in"):
    """Send a desktop screenshot to the configured notification channel."""
    if NOTIFY_CHANNEL_ID is None:
        print(f"{label}: notification channel is not configured.")
        return False

    channel = client.get_channel(NOTIFY_CHANNEL_ID)
    if channel is None:
        try:
            channel = await client.fetch_channel(NOTIFY_CHANNEL_ID)
        except Exception as exc:
            _record_monitor_error("screenshot channel", exc)
            print(f"{label}: could not load notification channel: {exc}")
            return False

    try:
        screenshot = ImageGrab.grab()
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        buffer.seek(0)
        card = _guardian_screenshot_card(label, screenshot)
        card_buffer = io.BytesIO()
        card.save(card_buffer, format="PNG", optimize=True)
        card_buffer.seek(0)
        await channel.send(file=discord.File(card_buffer, filename="guardian_screenshot.png"))
        print(f"{label} screenshot sent.")
        return True
    except Exception as exc:
        _record_monitor_error("screenshot", exc)
        print(f"{label}: could not take/send screenshot: {exc}")
        return False


@tasks.loop(minutes=PERIODIC_SCREENSHOT_INTERVAL_MINUTES or 30)
async def periodic_screenshot():
    await send_monitor_screenshot("Automatic Check-in")


@periodic_screenshot.before_loop
async def before_periodic_screenshot():
    await client.wait_until_ready()
    # Wait before the first automatic screenshot so startup only sends the
    # dedicated Startup Check-in. After that, screenshots are sent on the configured interval.
    await asyncio.sleep((PERIODIC_SCREENSHOT_INTERVAL_MINUTES or 30) * 60)


@periodic_screenshot.error
async def periodic_screenshot_error(error):
    _record_monitor_error("automatic screenshot", error)
    print(f"Automatic screenshot task error: {error}")
    await asyncio.sleep(2)
    if not periodic_screenshot.is_running():
        periodic_screenshot.restart()


# ---------------------------------------------------------------------------
# Official release update check
# ---------------------------------------------------------------------------

async def _check_official_update():
    """Check the official GitHub Release and notify this installation's user once."""
    if PING_USER_ID is None or NOTIFY_CHANNEL_ID is None:
        return
    try:
        import urllib.request
        def fetch():
            req = urllib.request.Request(
                GITHUB_LATEST_RELEASE_API,
                headers={"User-Agent": "P2P-Guardian-Bot/24.2.5", "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                return json.loads(response.read().decode("utf-8"))
        release = await asyncio.to_thread(fetch)
        if release.get("draft") or release.get("prerelease"):
            return
        tag = str(release.get("tag_name") or "")
        latest = _normalize_release_version(tag)
        if not latest or _compare_release_versions(PRODUCT_VERSION, latest) >= 0:
            return
        last_notified = ""
        try:
            last_notified = UPDATE_NOTICE_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            pass
        if last_notified == latest:
            return
        channel = await client.fetch_channel(NOTIFY_CHANNEL_ID)
        await channel.send(
            content=f"<@{PING_USER_ID}>",
            embed=guardian_embed(
                title="🛡️ P2P Guardian Update Available",
                description=(
                    f"A new official P2P Guardian release is available.\n\n"
                    f"Installed: **V{PRODUCT_VERSION}**\n"
                    f"Available: **V{latest}**\n\n"
                    "Open **P2P Guardian Control** to install the official Setup.exe. "
                    "The running bot will continue using its current version until you choose to update."
                ),
                color=GUARDIAN_DISCORD_COLOR,
            ),
        )
        try:
            UPDATE_NOTICE_FILE.write_text(latest, encoding="utf-8")
        except OSError:
            pass
    except Exception as exc:
        _record_monitor_error("official update check", exc)


def _normalize_release_version(value):
    value = str(value).strip()
    if value.lower().startswith("v"):
        value = value[1:]
    value = value.split("-", 1)[0]
    return value


def _compare_release_versions(left, right):
    def parts(v):
        result = []
        for item in _normalize_release_version(v).split(".")[:3]:
            try:
                result.append(int(item))
            except ValueError:
                result.append(0)
        return (result + [0, 0, 0])[:3]
    return (parts(left) > parts(right)) - (parts(left) < parts(right))


@tasks.loop(minutes=UPDATE_CHECK_INTERVAL_MINUTES)
async def check_official_update():
    await _check_official_update()


@check_official_update.before_loop
async def before_check_official_update():
    await client.wait_until_ready()


@check_official_update.error
async def check_official_update_error(error):
    _record_monitor_error("official update check", error)


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
        await _send_guardian_response_embed(
            interaction,
            guardian_embed(
                title="⛔ Owner Only",
                description="Only the owner of this bot can use this command.",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
    return False


# Apply the owner-only check to every slash command below.


@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Always acknowledge slash-command errors so Discord never shows a timeout."""
    if isinstance(error, app_commands.CheckFailure):
        # owner_only already sent the user-facing response when possible.
        if interaction.response.is_done():
            return
        title = "⛔ Command Not Available"
        description = "You do not have permission to use this command."
    else:
        title = "❌ Command Failed"
        description = f"The command could not be completed: `{str(error)[:500]}`"

    embed = guardian_embed(title=title, description=description, color=discord.Color.red())
    embed.set_footer(text="P2P Guardian • OSRS Monitor • command error")
    embed.timestamp = discord.utils.utcnow()
    try:
        if interaction.response.is_done():
            await _send_guardian_embed_response(interaction, embed, ephemeral=True)
        else:
            await _send_guardian_response_embed(interaction, embed, ephemeral=True)
    except Exception as exc:
        print(f"Slash-command error handler failed: {exc}")


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

    global _startup_screenshot_sent
    if not _startup_screenshot_sent:
        _startup_screenshot_sent = True
        await send_monitor_screenshot("Startup Check-in")

    # Prime one visual login check per live client, serialized in the background.
    # /status itself never restores or captures OSRS windows.
    _login_visual_bootstrap_pending.clear()
    for info in _get_osrs_clients():
        pid = info.get("pid")
        if pid is not None:
            _login_visual_bootstrap_pending.discard(int(pid))
    if not monitor_login_screen_per_client.is_running():
        monitor_login_screen_per_client.start()
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
    if not check_official_update.is_running():
        await _check_official_update()
        check_official_update.start()


@tree.command(name="help", description="Show the available OSRS Monitor commands")
@app_commands.check(owner_only)
async def help_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    embed = guardian_embed(
        title="🛡️ P2P Guardian — Commands",
        description="Commands for monitoring and troubleshooting. All commands are owner-only.",
        color=GUARDIAN_DISCORD_COLOR,
    )
    # Keep the help content complete. The custom card renderer treats each field
    # as a visual block, so the help command uses compact groups that fit without
    # truncating the command list.
    embed.add_field(
        name="MAIN COMMANDS",
        value=(
            "`/status` — overall bot and OSRS client status\n"
            "`/screenshot <PID>` — screenshot a selected active OSRS client\n"
            "`/resources` — show CPU and RAM usage\n"
            "`/bugreport` — create a support ZIP\n"
            "`/clear` — delete 1–50 messages"
        ),
        inline=False,
    )
    embed.add_field(
        name="CLIENT & DIAGNOSTICS",
        value=(
            "`/clienthealth` — OSRS client health\n"
            "`/clientevents` — recent login/logout mappings\n"
            "`/clientmap` — live PID-to-client mappings\n"
            "`/logincheck` — manual login-screen check"
        ),
        inline=False,
    )
    embed.add_field(
        name="LOG & LAUNCHER TOOLS",
        value=(
            "`/logstatus` — log monitoring status\n"
            "`/logscan` — scan Detuks logs\n"
            "`/logdebug` — show recent log changes\n"
            "`/launcherscan` — inspect Jagex Launcher files"
        ),
        inline=False,
    )
    embed.set_footer(text=GUARDIAN_FOOTER + " • /help")
    embed.timestamp = discord.utils.utcnow()
    await _send_guardian_embed_response(interaction, embed, ephemeral=True)


@tree.command(name="bugreport", description="Create a support package for bot or monitoring errors")
@app_commands.check(owner_only)
async def bugreport(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if support_report is None:
        await _send_guardian_embed_response(interaction, guardian_embed(
                title="❌ Support Package Unavailable",
                description="The support package module could not be loaded.",
                color=discord.Color.red(),
            ),
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

        # /bugreport creates the ZIP inside the branded P2P Guardian Support folder on the desktop.
        # Discord receives only the confirmation/path message; the ZIP is not uploaded.
        zip_path = await asyncio.to_thread(
            support_report.build_package,
            "\n".join(diagnostics),
        )

        embed = guardian_embed(
            title="🛠️ Support Package Created",
            description=(
                "The support package was created locally on the monitored PC.\n\n"
                f"**Support folder**\n`{support_report.SUPPORT_DIR}`\n\n"
                f"**ZIP location**\n`{zip_path}`\n\n"
                "The ZIP is not uploaded to Discord. It does not include the Discord bot token. "
                "Review the logs before sharing the file."
            ),
            color=GUARDIAN_DISCORD_COLOR,
        )
        await _send_guardian_embed_response(
            interaction,
            embed,
            ephemeral=True,
        )
    except Exception as exc:
        await _send_guardian_embed_response(interaction, guardian_embed(
                title="❌ Support Package Failed",
                description=f"Could not create the support package: `{str(exc)[:500]}`",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )


async def screenshot_account_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Offer active OSRS accounts while the /screenshot command is being typed."""
    clients = sorted(_get_osrs_clients(), key=lambda info: int(info.get("pid", 0)))
    current = (current or "").strip().lower()
    choices = []
    for info in clients[:25]:
        pid = info.get("pid")
        if pid is None:
            continue
        label = _client_label(info)
        state = _login_state_by_pid.get(pid, "unknown")
        state_text = {
            "logged_in": "Logged in",
            "login_screen": "Login screen",
            "unknown": "State unknown",
        }.get(state, "State unknown")
        display = f"{label} (PID {pid})"
        if current and current not in display.lower() and current not in str(pid).lower():
            continue
        choices.append(app_commands.Choice(name=f"{display} — {state_text}"[:100], value=str(pid)))
    return choices[:25]


@tree.command(name="screenshot", description="Capture a screenshot of a selected OSRS account")
@app_commands.describe(account="OSRS account to capture")
@app_commands.autocomplete(account=screenshot_account_autocomplete)
@app_commands.check(owner_only)
async def ss(interaction: discord.Interaction, account: str):
    try:
        pid = int(account)
    except (TypeError, ValueError):
        await _send_guardian_response_embed(
            interaction,
            guardian_embed(
                title="❌ Screenshot Failed",
                description="Invalid OSRS account selection.",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
        return

    clients = {int(info["pid"]): info for info in _get_osrs_clients() if info.get("pid") is not None}
    client_info = clients.get(pid)
    if not client_info:
        await _send_guardian_response_embed(
            interaction,
            guardian_embed(
                title="❌ Screenshot Failed",
                description=f"The selected OSRS account (PID {pid}) is no longer active.",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    try:
        window = client_info.get("window") or {}
        hwnd = window.get("hwnd")
        if not hwnd:
            raise RuntimeError(f"PID {pid} has no capturable OSRS window.")

        screenshot = await asyncio.to_thread(_capture_window_printwindow, int(hwnd))
        label = _client_label(client_info)
        card = _guardian_screenshot_card(f"Manual Screenshot — PID {pid} — {label}", screenshot)
        card_buffer = io.BytesIO()
        card.save(card_buffer, format="PNG", optimize=True)
        card_buffer.seek(0)
        await interaction.followup.send(
            content=f"📸 Screenshot of **{label}** — PID `{pid}`",
            file=discord.File(card_buffer, filename=f"guardian_screenshot_pid_{pid}.png"),
            ephemeral=True,
        )
    except Exception as exc:
        await interaction.followup.send(
            embed=guardian_embed(
                title="❌ Screenshot Failed",
                description=f"`{str(exc)[:500]}`",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )



def _reconstruct_task_context_from_log(log_path):
    """Rebuild the latest task context from the tail of one client log.

    This is read-only status reconstruction; it does not emit Discord task
    notifications. It is used when Guardian was started after the task was
    already assigned and therefore has no in-memory pending-task entry.
    """
    if not log_path or not Path(log_path).exists():
        return None
    try:
        path = Path(log_path)
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 256 * 1024), 0)
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None

    current = None
    last_complete = None
    for raw in text.splitlines():
        message = _log_message(raw)
        if not message:
            continue
        if "NEW TASK" in message.upper():
            current = {
                "task": None, "activity": None, "location": None,
                "target": None, "duration_minutes": None,
                "timestamp": _parse_log_timestamp(raw) or datetime.now(),
                "log_file": path.name,
            }
            continue
        if current is None:
            # Also accept task details that were written without a NEW TASK
            # marker, which occurs in some client versions.
            if not re.search(r"\bTask is\b|\bActivity is\b|\bLocation\s*(?:is|:|=|->)", message, re.I):
                continue
            current = {
                "task": None, "activity": None, "location": None,
                "target": None, "duration_minutes": None,
                "timestamp": _parse_log_timestamp(raw) or datetime.now(),
                "log_file": path.name,
            }

        match = re.search(r"Task is\s+(.+)$", message, re.I)
        if match:
            current["task"] = match.group(1).strip()
        match = re.search(r"Activity is\s+(.+)$", message, re.I)
        if match:
            current["activity"] = match.group(1).strip()
        match = re.search(r"Location\s*(?:is|:|=|->)\s*(.+)$", message, re.I)
        if match:
            current["location"] = match.group(1).strip()
        target = _parse_task_target(message)
        if target:
            current["target"] = target
        selected = _parse_selected_task(message)
        if selected:
            current.update(selected)

        if current.get("task"):
            # Keep the newest useful state even when the log omits one of the
            # optional fields for this task.
            last_complete = dict(current)

    return last_complete


def _status_context_for_client(client_info):
    """Return task/log context belonging to one live PID.

    Prefer explicit PID->log mappings. With exactly one live client, the
    newest task-bearing log is unambiguous and can be used for that client.
    Never mix a second client's mapped log into the first client's status.
    """
    pid = int(client_info.get("pid"))
    candidates = []
    for raw_path, mapped_pid in list(_task_client_pid_by_log.items()):
        try:
            if int(mapped_pid) != pid:
                continue
        except (TypeError, ValueError):
            continue
        key = str(Path(raw_path).resolve())
        ctx = _last_task_by_log.get(key)
        if ctx:
            try:
                stamp = ctx.get("last_update") or ctx.get("timestamp") or datetime.min
                candidates.append((stamp, key, ctx))
            except Exception:
                candidates.append((datetime.min, key, ctx))

    if candidates:
        return max(candidates, key=lambda item: item[0])[2], Path(max(candidates, key=lambda item: item[0])[1])

    # A single active client is the only safe case for using the current
    # global task/log state. This also keeps status useful immediately after a
    # task was parsed before the per-log cache existed.
    live = _get_osrs_clients()
    if len(live) == 1 and int(live[0].get("pid")) == pid:
        if _current_task:
            ctx = {
                "task": _current_task,
                "activity": _current_task_activity,
                "location": _current_task_location,
                "target": _current_task_target,
                "last_update": _current_task_last_update,
                "log_file": _current_task_last_log_file,
            }
            if _log_current_file:
                return ctx, _log_current_file
            return ctx, None

        if _log_current_file:
            rebuilt = _reconstruct_task_context_from_log(_log_current_file)
            if rebuilt:
                return rebuilt, _log_current_file
            return None, _log_current_file

    return None, None


def _refresh_pid_states_from_log_states():
    """Apply unambiguous current log state to live OSRS PIDs."""
    clients = _get_osrs_clients()
    if not clients:
        return
    live_pids = {int(info.get("pid")) for info in clients if info.get("pid") is not None}
    for raw_path, raw_pid in list(_task_client_pid_by_log.items()):
        try:
            pid = int(raw_pid)
        except (TypeError, ValueError):
            continue
        if pid not in live_pids:
            continue
        state = _login_state_by_log.get(str(Path(raw_path).resolve()))
        if state in ("logged_in", "login_screen"):
            _login_state_by_pid[pid] = state
    if len(live_pids) == 1:
        pid = next(iter(live_pids))
        candidates = []
        for path in _candidate_log_files():
            state = _login_state_by_log.get(str(path.resolve()))
            if state in ("logged_in", "login_screen"):
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    mtime = 0
                candidates.append((mtime, state))
        if candidates:
            _login_state_by_pid[pid] = max(candidates, key=lambda x: x[0])[1]


@tree.command(name="status", description="View the status of OSRS and all monitors")
@app_commands.check(owner_only)
async def status(interaction: discord.Interaction):
    await interaction.response.defer()

    clients = _get_osrs_clients()
    _bootstrap_login_states()
    _refresh_pid_states_from_log_states()
    _refresh_pid_login_states_from_client_health()
    if not clients:
        card = _guardian_status_card(
            osrs_status="⚪ Not Active",
            login_status="⚪ No active client",
            task_text="—",
            activity="—",
            location="—",
            log_name="No log found",
            client_status="No `osclient.exe` clients found.",
            client_health="State: No active client",
            monitor_status="🟢 All monitors operational" if not _monitor_errors else "🟠 Problems Detected",
            error_text="No monitor errors found." if not _monitor_errors else "\n".join(f"• {k}: {v[:140]}" for k,v in _monitor_errors.items()),
        )
        buf = io.BytesIO(); card.save(buf, format="JPEG", quality=92, optimize=True); buf.seek(0)
        await interaction.followup.send(content="🛡️ **P2P Guardian — OSRS Monitor**", file=discord.File(buf, filename="P2P_Guardian_Status.jpg"))
        return

    monitor_status = "🟢 All monitors operational" if not _monitor_errors else "🟠 Problems Detected"
    error_text = "No monitor errors found." if not _monitor_errors else "\n".join(
        f"• **{name}:** `{error[:140]}`" for name, error in _monitor_errors.items()
    )
    # One status card per live PID. This prevents account/PID/task/log data from
    # leaking between clients when several OSRS windows are running.
    for info in sorted(clients, key=lambda item: int(item.get("pid", 0))):
        pid = int(info["pid"])
        state = _login_state_by_pid.get(pid, "unknown")
        health = _client_health.get(pid, {})
        response = health.get("last_response")
        if response is False and health.get("hung_count", 0) >= HUNG_CONSECUTIVE_FAILURES:
            osrs_status = "🚨 Client not responding"
        elif state == "logged_in":
            osrs_status = "🟢 In-game"
        elif state == "login_screen":
            osrs_status = "🔴 Login / Play Now screen"
        else:
            osrs_status = "⚪ Client state unknown"

        if state == "logged_in":
            login_status = "🟢 Login Confirmed"
        elif state == "login_screen":
            login_status = "🔴 Play Now / Login Screen"
        else:
            login_status = "⚪ No confirmed login state"

        context, log_path = _status_context_for_client(info)
        if state != "logged_in":
            # A logged-out client must never display the previous task as if it
            # were still active. The current task is explicitly shown as '-'.
            task_text = "-"
            activity = "-"
            location = "-"
        elif context:
            task = context.get("task") or "-"
            activity = context.get("activity") or "-"
            location = context.get("location") or "-"
            target = context.get("target") or "-"
            task_text = task if target == "-" else f"{task} / {target}"
        else:
            task_text = "Not read yet"
            activity = "-"
            location = "-"

        log_name = log_path.name if log_path else "No log found"
        account = _client_label(info)
        title = ((info.get("window") or {}).get("title") or "OSRS client").strip()
        response_text = "responsive" if response is True else "not responding" if response is False else "not checked"
        window_state = _client_window_state(info)
        client_status = (
            f"PID {pid} — {account}\n"
            f"Window: {window_state} — {response_text}\n"
            f"{title}"
        )

        card = _guardian_status_card(
            osrs_status=osrs_status,
            login_status=login_status,
            task_text=task_text,
            activity=activity,
            location=location,
            log_name=log_name,
            client_status=client_status,
            client_health=(
                f"Window: {window_state}\n"
                f"Response: {response_text}"
            ),
            monitor_status=monitor_status,
            error_text=error_text,
        )
        buf = io.BytesIO(); card.save(buf, format="JPEG", quality=92, optimize=True); buf.seek(0)
        await interaction.followup.send(
            content=f"🛡️ **P2P Guardian — {account} — PID {pid}**",
            file=discord.File(buf, filename=f"P2P_Guardian_Status_PID_{pid}.jpg"),
        )


@tree.command(name="resources", description="View CPU and RAM usage of this PC")
@app_commands.check(owner_only)
async def resources(interaction: discord.Interaction):
    await interaction.response.defer()
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    embed = guardian_embed(title="🖥️ System Resources", color=GUARDIAN_DISCORD_COLOR)
    embed.add_field(name="⚙️ CPU", value=f"**{cpu:.0f}%** used", inline=True)
    embed.add_field(name="🧠 RAM", value=f"**{ram.percent:.0f}%** used", inline=True)
    embed.add_field(name="💾 Memory", value=f"{ram.used // (1024**2):,} MB / {ram.total // (1024**2):,} MB", inline=False)
    embed.set_footer(text="P2P Guardian • OSRS Monitor • /resources")
    embed.timestamp = discord.utils.utcnow()
    await _send_guardian_embed_response(interaction, embed)


@tree.command(name="logincheck", description="Manually check the OSRS login screen using OCR")
@app_commands.check(owner_only)
async def loginpixelstatus(interaction: discord.Interaction):
    await interaction.response.defer()
    visible = is_login_screen_visible_by_pixel()
    embed = guardian_embed(
        title="🔎 OSRS Login Check",
        description=(
            "🔴 **Login screen detected.**" if visible
            else "🟢 **No OSRS login screen detected.**"
        ),
        color=discord.Color.red() if visible else GUARDIAN_SUCCESS_COLOR,
    )
    embed.add_field(name="Method", value="OCR • full screen", inline=True)
    embed.set_footer(text="P2P Guardian • OSRS Monitor • /logincheck")
    embed.timestamp = discord.utils.utcnow()
    await _send_guardian_embed_response(interaction, embed)


@tree.command(name="clienthealth", description="Check all OSRS client processes and Windows responsiveness")
@app_commands.check(owner_only)
async def clienthealth(interaction: discord.Interaction):
    await interaction.response.defer()
    clients = _get_osrs_clients()
    if not clients:
        await _send_guardian_embed_response(interaction, guardian_embed(
                title="🧩 OSRS Client Health",
                description="No `osclient.exe` processes are currently running.",
                color=GUARDIAN_DISCORD_COLOR,
            )
        )
        return

    embed = guardian_embed(title="🧩 OSRS Client Health", color=GUARDIAN_DISCORD_COLOR)
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
    embed.set_footer(text="P2P Guardian • OSRS Monitor • /clienthealth")
    embed.timestamp = discord.utils.utcnow()
    await _send_guardian_embed_response(interaction, embed)


@tree.command(name="clientevents", description="Show recent login/logout event-to-PID mappings")
@app_commands.check(owner_only)
async def clientevents(interaction: discord.Interaction):
    await interaction.response.defer()
    with _action_event_lock:
        events = list(_action_event_queue)[-12:]

    embed = guardian_embed(
        title="🧭 Recent Client Event Mapping",
        description="Most recent action events mapped to live OSRS PIDs.",
        color=GUARDIAN_DISCORD_COLOR,
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

    embed.set_footer(text="P2P Guardian • OSRS Monitor • /clientevents")
    embed.timestamp = discord.utils.utcnow()
    await _send_guardian_embed_response(interaction, embed)


@tree.command(name="clientmap", description="Show live PID-to-client login/logout mappings")
@app_commands.check(owner_only)
async def clientmap(interaction: discord.Interaction):
    await interaction.response.defer()
    clients = _get_osrs_clients()
    if not clients:
        await _send_guardian_embed_response(interaction, guardian_embed(
                title="🧩 OSRS Client PID Map",
                description="No `osclient.exe` clients are currently running.",
                color=GUARDIAN_DISCORD_COLOR,
            )
        )
        return

    embed = guardian_embed(title="🧩 OSRS Client PID Map", color=GUARDIAN_DISCORD_COLOR)
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
    embed.set_footer(text="P2P Guardian • OSRS Monitor • /clientmap")
    embed.timestamp = discord.utils.utcnow()
    await _send_guardian_embed_response(interaction, embed)


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

    embed = guardian_embed(
        title="📄 Log Monitor Status",
        description="The bot recursively monitors the entire `.detuksosrs` tree for relevant logs. Login/logout state is tracked separately per log file; `/logscan` shows what was found.",
        color=GUARDIAN_DISCORD_COLOR,
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
    embed.set_footer(text="P2P Guardian • OSRS Monitor • /logstatus")
    embed.timestamp = discord.utils.utcnow()
    await _send_guardian_embed_response(interaction, embed)



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
        rows = _log_debug_lines(max_files=6, max_lines=60)
        mode = "Recent diagnostic lines (no new matching lines since the last read)"

    base_description = (
        "Diagnostic only — no login/logout alert is generated by this command.\n"
        f"**{mode}**. Detuks root: `{LOG_ROOT_DIRECTORY}`\n"
        f"Jagex Launcher: `{JAGEX_LAUNCHER_DIRECTORY}`"
    )
    if not rows:
        embed = guardian_embed(title="🔎 Detuks Login/Logout Debug", description=base_description, color=GUARDIAN_DISCORD_COLOR)
        embed.add_field(name="No matching lines", value="No recent login/logout diagnostic lines were found.", inline=False)
        embed.set_footer(text="P2P Guardian • OSRS Monitor • /logdebug • diagnostic only")
        embed.timestamp = discord.utils.utcnow()
        await _send_guardian_embed_response(interaction, embed)
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
        # Keep long diagnostic messages readable. Split instead of silently
        # discarding the tail; Discord fields are later chunked safely.
        header = f"`{rel}` • `{label}` • `{_format_timestamp(ts)}`"
        message_text = str(msg or "").strip()
        if not message_text:
            row_lines.append(header)
        else:
            # Preserve the complete message in manageable visual pieces.
            pieces = [message_text[i:i+700] for i in range(0, len(message_text), 700)]
            row_lines.append(header + "\n" + pieces[0])
            for piece in pieces[1:]:
                row_lines.append("↳ " + piece)

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
        embed=guardian_embed(title="🔎 Detuks Login/Logout Debug", description=base_description if not embeds else "Diagnostic results (continued).", color=GUARDIAN_DISCORD_COLOR)
        for offset, chunk in enumerate(chunks[field_start:field_start+5]):
            n=field_start+offset+1
            embed.add_field(name="Recent matching log lines" if n==1 else f"Recent matching log lines ({n})", value=chunk[:1000], inline=False)
        embed.set_footer(text="P2P Guardian • OSRS Monitor • /logdebug • diagnostic only")
        embed.timestamp=discord.utils.utcnow()
        embeds.append(embed)
    await _send_guardian_embed_response(interaction, embeds[0])
    for embed in embeds[1:]:
        await _send_guardian_embed_response(interaction, embed)


@tree.command(name="launcherscan", description="Inspect the installed Jagex Launcher files")
@app_commands.check(owner_only)
async def launcherscan(interaction: discord.Interaction):
    await interaction.response.defer()
    info = await asyncio.to_thread(_launcher_inventory)
    if not info["exists"]:
        await _send_guardian_embed_response(interaction, guardian_embed(
            title="Jagex Launcher Scan",
            description=f"Path not found: `{JAGEX_LAUNCHER_DIRECTORY}`",
            color=GUARDIAN_DISCORD_COLOR,
        ))
        return

    embed = guardian_embed(
        title="🎮 Jagex Launcher Scan",
        description=(
            f"Path: `{JAGEX_LAUNCHER_DIRECTORY}`\n"
            f"Files: **{info['files']:,}** • Directories: **{info['dirs']:,}**\n"
            "Interesting files (logs/config/errors) are listed below."
        ),
        color=GUARDIAN_DISCORD_COLOR,
    )
    if info["items"]:
        lines = [f"`{rel}` — {size:,} bytes" for _, rel, size in info["items"][:60]]
        chunk = []; total = 0; field_index = 0
        for line in lines:
            if chunk and total + len(line) + 1 > 900:
                field_index += 1
                embed.add_field(name="Interesting Files" if field_index == 1 else "Interesting Files (cont.)", value="\n".join(chunk), inline=False)
                chunk = []; total = 0
            chunk.append(line); total += len(line) + 1
        if chunk:
            field_index += 1
            embed.add_field(name="Interesting Files" if field_index == 1 else "Interesting Files (cont.)", value="\n".join(chunk), inline=False)
    else:
        embed.add_field(name="Interesting Files", value="No obvious log/config/error files found in the installation directory.", inline=False)
    embed.set_footer(text="P2P Guardian • OSRS Monitor • /launcherscan")
    embed.timestamp = discord.utils.utcnow()
    await _send_guardian_embed_response(interaction, embed)

@tree.command(name="logscan", description="Scan .detuksosrs and summarize relevant log files")
@app_commands.check(owner_only)
async def logscan(interaction: discord.Interaction):
    await interaction.response.defer()
    results = _log_scan_summary()
    if not results:
        await _send_guardian_embed_response(interaction, guardian_embed(
                title="📂 Detuks Log Scan",
                description=f"No relevant log files were found under `{LOG_ROOT_DIRECTORY}`.",
                color=GUARDIAN_DISCORD_COLOR,
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

    embed = guardian_embed(
        title="📂 Detuks Log Scan",
        description=(
            f"Recursive scan of `{LOG_ROOT_DIRECTORY}`. "
            f"Found **{len(results)}** relevant log files; **{len(active)}** changed within the last 10 minutes.\n\n"
            "Login/logout detection uses per-log state; `LOGIN_SCREEN` during startup is not treated as a logout."
        ),
        color=GUARDIAN_DISCORD_COLOR,
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
    embed.set_footer(text="P2P Guardian • OSRS Monitor • /logscan")
    embed.timestamp = discord.utils.utcnow()
    await _send_guardian_embed_response(interaction, embed)


@tree.command(name="clear", description="Delete 1 to 50 messages from this Discord channel")
@app_commands.describe(amount="Number of messages to delete (1 to 50)")
@app_commands.check(owner_only)
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 50]):
    await interaction.response.defer(ephemeral=True)

    if not isinstance(interaction.channel, discord.TextChannel):
        await _send_guardian_embed_response(interaction, guardian_embed(
                title="❌ Not Available",
                description="This command can only be used in a standard text channel.",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
        return

    permissions = interaction.channel.permissions_for(interaction.guild.me)
    if not permissions.manage_messages:
        await _send_guardian_embed_response(interaction, guardian_embed(
                title="❌ Permission Denied",
                description="The bot needs **Manage Messages** permission in this channel.",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
        return

    try:
        deleted = await interaction.channel.purge(limit=int(amount))
        embed = guardian_embed(
            title="🧹 Messages deleted",
            description=f"**{len(deleted)}** messages were deleted.",
            color=GUARDIAN_SUCCESS_COLOR,
        )
        embed.add_field(name="Requested", value=str(int(amount)), inline=True)
        embed.set_footer(text="P2P Guardian • OSRS Monitor • /clear")
        embed.timestamp = discord.utils.utcnow()
        await _send_guardian_embed_response(interaction, embed, ephemeral=True)
    except discord.Forbidden:
        await _send_guardian_embed_response(interaction, guardian_embed(
                title="❌ Permission Denied",
                description="Discord denied the deletion. Make sure the bot has **Manage Messages** permission.",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
    except Exception as exc:
        await _send_guardian_embed_response(interaction, guardian_embed(
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
