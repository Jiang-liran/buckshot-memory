from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox


APP_NAME = "恶魔轮盘 · 实时膛线"
APP_VERSION = "3.0.2"
FONT = "Microsoft YaHei UI"
MONO = "Consolas"

COLORS = {
    "bg": "#090a0a",
    "panel": "#121414",
    "raised": "#1a1c1c",
    "line": "#303332",
    "ink": "#eeeae1",
    "soft": "#aaa79f",
    "faint": "#74736e",
    "red": "#ed6258",
    "red_dark": "#4f211f",
    "amber": "#caa568",
    "green": "#8fa982",
    "blank": "#d5d1c5",
}

PATCHED_GAME_NAME = "Buckshot Roulette Memory.exe"
OFFICIAL_GAME_NAME = "Buckshot Roulette.exe"
STATE_FILE = (
    Path(os.environ.get("APPDATA") or str(Path.home()))
    / "Godot"
    / "app_userdata"
    / "Buckshot Roulette"
    / "buckshot_memory_state.json"
)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def format_options(values: list[int]) -> str:
    unique = sorted(set(values))
    return " / ".join(str(value) for value in unique) if unique else "—"


def sanitize_state(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("状态文件必须是对象")
    if raw.get("schema") != 1 or raw.get("mode") != "singleplayer":
        raise ValueError("状态文件版本不匹配")
    remaining = int(raw.get("remaining", 0))
    if not 0 <= remaining <= 8:
        raise ValueError("剩余弹数无效")
    sequence = list(raw.get("known_sequence", []))
    sequence = [
        shell if shell in ("unknown", "live", "blank") else "unknown"
        for shell in sequence
    ]
    sequence = (sequence + ["unknown"] * remaining)[:remaining]
    def valid_options(values) -> list[int]:
        result = set()
        for value in values:
            try:
                integer = int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= integer <= remaining:
                result.add(integer)
        return sorted(result)

    live_options = valid_options(raw.get("live_options", []))
    blank_options = valid_options(raw.get("blank_options", []))
    if not live_options:
        live_options = [sequence.count("live")]
    if not blank_options:
        blank_options = sorted({remaining - value for value in live_options})
    return {
        "active": bool(raw.get("active", False)),
        "remaining": remaining,
        "sequence": sequence,
        "live_options": live_options,
        "blank_options": blank_options,
    }


def probability_options(state: dict) -> list[float]:
    remaining = state["remaining"]
    if remaining <= 0:
        return [0.0]
    current = state["sequence"][0]
    if current == "live":
        return [1.0]
    if current == "blank":
        return [0.0]
    known_live = state["sequence"].count("live")
    unknown = state["sequence"].count("unknown")
    if unknown <= 0:
        return [0.0]
    values = []
    for live in state["live_options"]:
        probability = (live - known_live) / unknown
        values.append(clamp(probability, 0.0, 1.0))
    return sorted(set(values)) or [0.0]


def steam_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        import winreg

        keys = (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Valve\Steam",
                "InstallPath",
            ),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        )
        for hive, key_name, value_name in keys:
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    value, _kind = winreg.QueryValueEx(key, value_name)
                    roots.append(Path(value))
            except OSError:
                continue
    except ImportError:
        pass

    for root in list(roots):
        library_file = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = library_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            roots.append(Path(match.group(1).replace(r"\\", "\\")))

    roots.extend(
        [
            Path(r"C:\Program Files (x86)\Steam"),
            Path(r"C:\Program Files\Steam"),
        ]
    )
    result: list[Path] = []
    for root in roots:
        normalized = Path(os.path.normpath(str(root)))
        if normalized not in result:
            result.append(normalized)
    return result


def find_patched_game() -> Path | None:
    override = os.environ.get("BUCKSHOT_MEMORY_GAME")
    if override:
        candidate = Path(override).expanduser()
        return candidate if candidate.is_file() else None
    relative = (
        Path("steamapps")
        / "common"
        / "Buckshot Roulette"
        / "Buckshot Roulette_windows"
        / PATCHED_GAME_NAME
    )
    for root in steam_roots():
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def buckshot_window_open() -> bool:
    if sys.platform != "win32":
        return False
    found = False
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
    )

    def enum_callback(hwnd, _lparam):
        nonlocal found
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if "buckshot roulette" in buffer.value.lower():
            found = True
            return False
        return True

    user32.EnumWindows(callback_type(enum_callback), 0)
    return found


class BridgeApp(tk.Tk):
    def __init__(self, smoke_test: bool = False) -> None:
        super().__init__()
        self.smoke_test = smoke_test
        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, False)
        self.geometry(self._center_geometry(790, 420))
        self.attributes("-topmost", True)

        self.status_var = tk.StringVar(value="正在连接单人游戏…")
        self.live_var = tk.StringVar(value="—")
        self.blank_var = tk.StringVar(value="—")
        self.remaining_var = tk.StringVar(value="—")
        self.last_mtime_ns = -1
        self.last_valid_state: dict | None = None
        self.last_valid_read = 0.0
        self.last_render_signature: tuple | None = None
        self.last_launch = 0.0
        self.game_path = find_patched_game()

        self._build_ui()
        self.after(80, self._poll_state)
        if not smoke_test:
            self.after(450, self._auto_launch)

    def _center_geometry(self, width: int, height: int) -> str:
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        return (
            f"{width}x{height}+{max(0, (screen_w - width) // 2)}+"
            f"{max(0, (screen_h - height) // 2)}"
        )

    def _panel(self, parent: tk.Misc) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=COLORS["panel"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
        )

    def _button(self, parent: tk.Misc, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=COLORS["red"],
            fg="#fff8f3",
            activebackground="#ff766b",
            activeforeground="#ffffff",
            font=(FONT, 9, "bold"),
            relief="flat",
            bd=0,
            padx=13,
            pady=7,
            cursor="hand2",
        )

    def _build_ui(self) -> None:
        top = tk.Frame(self, bg=COLORS["bg"])
        top.pack(fill="x", padx=16, pady=(14, 10))
        title = tk.Frame(top, bg=COLORS["bg"])
        title.pack(side="left")
        tk.Label(
            title,
            text="恶魔轮盘 · 实时膛线",
            bg=COLORS["bg"],
            fg=COLORS["ink"],
            font=(FONT, 16, "bold"),
        ).pack(anchor="w")
        self.status_label = tk.Label(
            title,
            textvariable=self.status_var,
            bg=COLORS["bg"],
            fg=COLORS["amber"],
            font=(FONT, 8),
        )
        self.status_label.pack(anchor="w", pady=(2, 0))
        tk.Label(
            top,
            text="仅单人模式",
            bg=COLORS["red_dark"],
            fg=COLORS["red"],
            font=(FONT, 8, "bold"),
            padx=9,
            pady=5,
        ).pack(side="right", padx=(8, 0))
        self.launch_button = self._button(top, "启动单人游戏", self.launch_game)
        self.launch_button.pack(side="right")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=16)

        risk_panel = self._panel(body)
        risk_panel.pack(side="left", fill="y", padx=(0, 10))
        self.risk_canvas = tk.Canvas(
            risk_panel,
            width=215,
            height=260,
            bg=COLORS["panel"],
            bd=0,
            highlightthickness=0,
        )
        self.risk_canvas.pack(padx=4, pady=4)
        self._draw_waiting()

        right = tk.Frame(body, bg=COLORS["bg"])
        right.pack(side="left", fill="both", expand=True)
        counts = tk.Frame(right, bg=COLORS["bg"])
        counts.pack(fill="x")
        for label, variable, color in (
            ("实弹", self.live_var, COLORS["red"]),
            ("空包弹", self.blank_var, COLORS["blank"]),
            ("总剩余", self.remaining_var, COLORS["ink"]),
        ):
            card = self._panel(counts)
            card.pack(side="left", fill="both", expand=True, padx=(0, 6))
            tk.Label(
                card,
                text=label,
                bg=COLORS["panel"],
                fg=COLORS["soft"],
                font=(FONT, 8),
            ).pack(pady=(8, 0))
            tk.Label(
                card,
                textvariable=variable,
                bg=COLORS["panel"],
                fg=color,
                font=(MONO, 19, "bold"),
            ).pack(pady=(0, 8))

        sequence_panel = self._panel(right)
        sequence_panel.pack(fill="both", expand=True, pady=(9, 0))
        tk.Label(
            sequence_panel,
            text="已知弹序",
            bg=COLORS["panel"],
            fg=COLORS["ink"],
            font=(FONT, 10, "bold"),
        ).pack(anchor="w", padx=12, pady=(10, 5))
        self.sequence_frame = tk.Frame(sequence_panel, bg=COLORS["panel"])
        self.sequence_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._draw_sequence([])

        tk.Label(
            self,
            text="从游戏内部状态实时同步（约 0.16 秒） · 只显示装填数量和道具已经揭示的弹型",
            bg=COLORS["bg"],
            fg=COLORS["faint"],
            font=(FONT, 7),
        ).pack(pady=(9, 10))

    def _set_status(self, text: str, color: str | None = None) -> None:
        self.status_var.set(text)
        self.status_label.configure(fg=color or COLORS["amber"])

    def _auto_launch(self) -> None:
        if self.smoke_test:
            return
        if buckshot_window_open():
            self._set_status("检测到游戏窗口；进入单人牌桌后等待内部状态", COLORS["amber"])
            return
        self.launch_game(automatic=True)

    def launch_game(self, automatic: bool = False) -> None:
        self.game_path = find_patched_game()
        if not self.game_path:
            if not automatic:
                messagebox.showerror(
                    "未安装实时桥接",
                    "没有找到“Buckshot Roulette Memory.exe”。\n"
                    "请按 README 运行 tools/install_bridge.py。",
                    parent=self,
                )
            self._set_status("未找到单人桥接游戏副本", COLORS["red"])
            return
        if buckshot_window_open():
            if not automatic:
                messagebox.showinfo(
                    "游戏已经打开",
                    "如果当前是 Steam 原版，请先关闭它，再从这里启动单人游戏。",
                    parent=self,
                )
            self._set_status("游戏已打开 · 进入单人牌桌后开始同步", COLORS["amber"])
            return
        try:
            subprocess.Popen(
                [str(self.game_path)],
                cwd=str(self.game_path.parent),
                close_fds=True,
            )
            self.last_launch = time.monotonic()
            self._set_status("单人游戏正在启动…", COLORS["amber"])
        except OSError as exc:
            self._set_status(f"游戏启动失败：{exc}", COLORS["red"])

    def _read_state(self) -> tuple[dict | None, str]:
        try:
            stat = STATE_FILE.stat()
        except OSError:
            return None, "等待游戏内部状态"
        age = time.time() - stat.st_mtime
        if age > 1.8:
            return None, "游戏未同步 · 请从本助手启动并进入单人牌桌"
        if stat.st_mtime_ns == self.last_mtime_ns and self.last_valid_state:
            if self.last_valid_state["active"]:
                return self.last_valid_state, ""
            return None, "等待进入单人牌桌"
        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            state = sanitize_state(raw)
        except (OSError, json.JSONDecodeError, TypeError, ValueError, OverflowError):
            # The game can be between truncating and writing this file. Keep a
            # recent good frame, but never extend the grace period on failures.
            if (
                self.last_valid_state
                and self.last_valid_state["active"]
                and time.monotonic() - self.last_valid_read <= 1.8
            ):
                return self.last_valid_state, ""
            return None, "正在读取游戏状态…"
        self.last_mtime_ns = stat.st_mtime_ns
        self.last_valid_state = state
        self.last_valid_read = time.monotonic()
        if not state["active"]:
            return None, "等待进入单人牌桌"
        return state, ""

    def _poll_state(self) -> None:
        state, waiting = self._read_state()
        if state:
            self._render_state(state)
            self._set_status("已连接 · 实时同步中", COLORS["green"])
        else:
            self._render_waiting()
            if time.monotonic() - self.last_launch < 8:
                waiting = "单人游戏正在启动…"
            self._set_status(waiting, COLORS["amber"])
        if self.winfo_exists():
            self.after(100, self._poll_state)

    def _render_state(self, state: dict) -> None:
        signature = (
            "state",
            state["remaining"],
            tuple(state["live_options"]),
            tuple(state["blank_options"]),
            tuple(state["sequence"]),
        )
        if signature == self.last_render_signature:
            return
        self.last_render_signature = signature
        self.live_var.set(format_options(state["live_options"]))
        self.blank_var.set(format_options(state["blank_options"]))
        self.remaining_var.set(str(state["remaining"]))
        self._draw_risk(probability_options(state), state["sequence"])
        self._draw_sequence(state["sequence"])

    def _render_waiting(self) -> None:
        signature = ("waiting",)
        if signature == self.last_render_signature:
            return
        self.last_render_signature = signature
        self.live_var.set("—")
        self.blank_var.set("—")
        self.remaining_var.set("—")
        self._draw_waiting()
        self._draw_sequence([])

    def _draw_waiting(self) -> None:
        canvas = self.risk_canvas
        canvas.delete("all")
        canvas.create_oval(35, 24, 180, 169, outline=COLORS["line"], width=11)
        canvas.create_text(
            107,
            91,
            text="—",
            fill=COLORS["faint"],
            font=(MONO, 30, "bold"),
        )
        canvas.create_text(
            107,
            205,
            text="等待单人牌桌",
            fill=COLORS["soft"],
            font=(FONT, 11, "bold"),
        )
        canvas.create_text(
            107,
            228,
            text="无需手动记录",
            fill=COLORS["faint"],
            font=(FONT, 8),
        )

    def _draw_risk(self, probabilities: list[float], sequence: list[str]) -> None:
        canvas = self.risk_canvas
        canvas.delete("all")
        minimum = round(min(probabilities) * 100)
        maximum = round(max(probabilities) * 100)
        current = sequence[0] if sequence else "unknown"
        percent_text = (
            f"{minimum}%"
            if minimum == maximum
            else f"{minimum}–{maximum}%"
        )
        midpoint = (minimum + maximum) / 2
        canvas.create_oval(35, 24, 180, 169, outline=COLORS["line"], width=11)
        if midpoint > 0:
            canvas.create_arc(
                35,
                24,
                180,
                169,
                start=90,
                extent=-(midpoint * 3.6),
                style="arc",
                outline=COLORS["red"],
                width=11,
            )
        canvas.create_text(
            107,
            87,
            text=percent_text,
            fill=COLORS["ink"],
            font=(MONO, 25 if minimum == maximum else 20, "bold"),
        )
        canvas.create_text(
            107,
            116,
            text="当前实弹概率",
            fill=COLORS["soft"],
            font=(FONT, 9),
        )
        if current == "live":
            headline, color = "确定实弹", COLORS["red"]
        elif current == "blank":
            headline, color = "确定空包弹", COLORS["blank"]
        elif minimum == maximum:
            headline, color = "膛内未知", COLORS["amber"]
        else:
            headline, color = "翻转后概率范围", COLORS["amber"]
        canvas.create_text(
            107,
            205,
            text=headline,
            fill=color,
            font=(FONT, 12, "bold"),
        )
        canvas.create_text(
            107,
            229,
            text="自动随游戏变化更新",
            fill=COLORS["faint"],
            font=(FONT, 8),
        )

    def _draw_sequence(self, sequence: list[str]) -> None:
        for child in self.sequence_frame.winfo_children():
            child.destroy()
        if not sequence:
            tk.Label(
                self.sequence_frame,
                text="进入牌桌后自动显示",
                bg=COLORS["panel"],
                fg=COLORS["faint"],
                font=(FONT, 9),
            ).pack(expand=True)
            return
        for index, shell in enumerate(sequence):
            frame = tk.Frame(
                self.sequence_frame,
                bg=COLORS["raised"],
                highlightthickness=1,
                highlightbackground=(
                    COLORS["amber"]
                    if index == 0
                    else COLORS["red_dark"]
                    if shell == "live"
                    else "#555149"
                    if shell == "blank"
                    else COLORS["line"]
                ),
            )
            frame.pack(side="left", fill="both", expand=True, padx=3, pady=5)
            symbol = "●" if shell == "live" else "○" if shell == "blank" else "?"
            label = "实弹" if shell == "live" else "空包" if shell == "blank" else "未知"
            tk.Label(
                frame,
                text="膛内" if index == 0 else f"第 {index + 1} 发",
                bg=COLORS["raised"],
                fg=COLORS["soft"],
                font=(FONT, 7),
            ).pack(pady=(9, 2))
            tk.Label(
                frame,
                text=symbol,
                bg=COLORS["raised"],
                fg=COLORS["red"] if shell == "live" else COLORS["blank"],
                font=(MONO, 17, "bold"),
            ).pack()
            tk.Label(
                frame,
                text=label,
                bg=COLORS["raised"],
                fg=COLORS["ink"],
                font=(FONT, 8, "bold"),
            ).pack(pady=(1, 9))


def run_self_tests() -> None:
    state = sanitize_state(
        {
            "schema": 1,
            "mode": "singleplayer",
            "active": True,
            "remaining": 5,
            "live_options": [2],
            "blank_options": [3],
            "known_sequence": ["unknown", "blank", "unknown", "unknown", "live"],
        }
    )
    assert probability_options(state) == [1 / 3]
    state["sequence"][0] = "live"
    assert probability_options(state) == [1.0]
    state["sequence"][0] = "unknown"
    state["live_options"] = [1, 3]
    assert probability_options(state) == [0.0, 2 / 3]
    assert format_options([3, 1, 3]) == "1 / 3"
    print("Bridge UI tests passed.")


def configure_windows_dpi() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def main() -> None:
    if "--self-test" in sys.argv:
        run_self_tests()
        return
    configure_windows_dpi()
    state_smoke_test = "--ui-state-smoke-test" in sys.argv
    smoke_test = "--ui-smoke-test" in sys.argv or state_smoke_test
    app = BridgeApp(smoke_test=smoke_test)
    if smoke_test:
        app.withdraw()
        app.update_idletasks()
        assert app.game_path is None or app.game_path.name == PATCHED_GAME_NAME
        if state_smoke_test:
            app._poll_state()
            assert app.live_var.get() == "2"
            assert app.blank_var.get() == "3"
            assert app.remaining_var.get() == "5"
            widgets_before = tuple(str(widget) for widget in app.sequence_frame.winfo_children())
            app._poll_state()
            widgets_after = tuple(str(widget) for widget in app.sequence_frame.winfo_children())
            assert widgets_after == widgets_before
        app.destroy()
        print("Bridge UI state smoke test passed." if state_smoke_test else "Bridge UI smoke test passed.")
        return
    app.mainloop()


if __name__ == "__main__":
    main()
