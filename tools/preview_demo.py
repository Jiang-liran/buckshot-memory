"""Show the real desktop UI with deterministic, clearly labeled demo data.

No game is started, no game state file is read or written, and no save is used.
Press 1, 2 or 3 to change scenes; Escape closes the preview.
"""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import buckshot_bridge_ui as ui

SCENES = {
    "1": {
        "caption": "演示数据 · 刚装填：3 实弹 / 3 空包，弹序未知",
        "live": 3,
        "sequence": ["unknown"] * 6,
    },
    "2": {
        "caption": "演示数据 · 放大镜：膛内空包；手机：第 5 发实弹",
        "live": 3,
        "sequence": ["blank", "unknown", "unknown", "unknown", "live", "unknown"],
    },
    "3": {
        "caption": "演示数据 · 消耗 1 发空包：原第 5 发已前移至第 4 发",
        "live": 3,
        "sequence": ["unknown", "unknown", "unknown", "live", "unknown"],
    },
}


def demo_state(scene: str) -> dict:
    data = SCENES[scene]
    remaining = len(data["sequence"])
    return ui.sanitize_state({
        "schema": 1, "mode": "singleplayer", "active": True,
        "remaining": remaining,
        "live_options": [data["live"]],
        "blank_options": [remaining - data["live"]],
        "known_sequence": list(data["sequence"]),
    })


class DemoApp(ui.BridgeApp):
    def __init__(self, scene: str):
        super().__init__(smoke_test=True)
        self.title(f"{ui.APP_NAME}  v{ui.APP_VERSION} · 演示预览")
        self.attributes("-topmost", False)
        self.configure(cursor="none")  # Keyboard-only preview; clean screenshots.
        self.launch_button.configure(state="disabled")
        for number in SCENES:
            self.bind(number, lambda _event, key=number: self.show_scene(key))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.show_scene(scene)

    def _poll_state(self):
        # Override the scheduled poll: demo mode must never touch live state.
        pass

    def launch_game(self, automatic=False):
        pass

    def show_scene(self, scene: str):
        self._render_state(demo_state(scene))
        self._set_status(SCENES[scene]["caption"], ui.COLORS["amber"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=SCENES, default="1")
    args = parser.parse_args()
    # Avoid even Steam-path discovery in a documentation-only preview.
    ui.find_patched_game = lambda: None
    # Use Tk's default logical-pixel scale for consistent documentation previews.
    # The actual application keeps its normal Windows DPI-awareness behavior.
    app = DemoApp(args.scene)
    app.mainloop()


if __name__ == "__main__":
    main()
