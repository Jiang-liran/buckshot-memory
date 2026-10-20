from pathlib import Path
from types import SimpleNamespace
import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
import buckshot_bridge_ui as ui
import install_bridge as installer


def payload(**changes):
    result = dict(schema=1, mode="singleplayer", active=True, remaining=5,
                  live_options=[2], blank_options=[3],
                  known_sequence=["unknown", "blank", "unknown", "unknown", "live"])
    result.update(changes)
    return result


class StateTests(unittest.TestCase):
    def test_probability_excludes_known_future_rounds(self):
        self.assertEqual(ui.probability_options(ui.sanitize_state(payload())), [1 / 3])

    def test_known_chamber(self):
        for shell, expected in (("live", 1.0), ("blank", 0.0)):
            state = ui.sanitize_state(payload(known_sequence=[shell] * 5))
            self.assertEqual(ui.probability_options(state), [expected])

    def test_empty_chamber(self):
        state = ui.sanitize_state(payload(remaining=0, live_options=[0], blank_options=[0]))
        self.assertEqual(state["sequence"], [])
        self.assertEqual(ui.probability_options(state), [0.0])

    def test_uncertain_counts(self):
        state = ui.sanitize_state(payload(live_options=[1, 3]))
        self.assertEqual(ui.probability_options(state), [0.0, 2 / 3])

    def test_rejects_other_modes_and_versions(self):
        for raw in ([], None, payload(schema=2), payload(mode="multiplayer"), payload(remaining=9)):
            with self.subTest(raw=raw), self.assertRaises((TypeError, ValueError)):
                ui.sanitize_state(raw)

    def test_unknown_values_are_not_revealed(self):
        state = ui.sanitize_state(payload(known_sequence=["secret", "live"]))
        self.assertEqual(state["sequence"], ["unknown", "live", "unknown", "unknown", "unknown"])

    def test_display_options(self):
        self.assertEqual(ui.format_options([3, 1, 3]), "1 / 3")


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.json"
        self.override = patch.object(ui, "STATE_FILE", self.path)
        self.override.start()
        self.reader = SimpleNamespace(last_mtime_ns=-1, last_valid_state=None, last_valid_read=0.0)

    def tearDown(self):
        self.override.stop()
        self.temp.cleanup()

    def read(self):
        return ui.BridgeApp._read_state(self.reader)

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")
        # Ensure an observation detects a new file on coarse timestamp systems.
        self.reader.last_mtime_ns = -1

    def test_missing_file(self):
        self.assertIsNone(self.read()[0])

    def test_cached_inactive_state_stays_inactive(self):
        self.write(payload(active=False))
        self.assertIsNone(self.read()[0])
        self.assertIsNone(self.read()[0])

    def test_partial_write_preserves_recent_frame_then_expires(self):
        self.write(payload())
        good = self.read()[0]
        self.path.write_text("{", encoding="utf-8")
        self.reader.last_mtime_ns = -1
        self.assertEqual(self.read()[0], good)
        self.reader.last_valid_read -= 2
        self.assertIsNone(self.read()[0])

    def test_stale_file_is_not_displayed(self):
        self.write(payload())
        self.read()
        os.utime(self.path, (time.time() - 10, time.time() - 10))
        self.assertIsNone(self.read()[0])

    def test_invalid_json_object(self):
        self.write([])
        self.assertIsNone(self.read()[0])


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.view = SimpleNamespace(last_render_signature=None, live_var=Mock(),
                                    blank_var=Mock(), remaining_var=Mock(),
                                    _draw_risk=Mock(), _draw_sequence=Mock(), _draw_waiting=Mock())

    def test_identical_updates_do_not_redraw_sequence(self):
        for tick in range(500):
            ui.BridgeApp._render_state(self.view, ui.sanitize_state(payload(tick=tick)))
        self.view._draw_sequence.assert_called_once()
        self.view._draw_risk.assert_called_once()

    def test_meaningful_changes_redraw(self):
        ui.BridgeApp._render_state(self.view, ui.sanitize_state(payload()))
        ui.BridgeApp._render_state(self.view, ui.sanitize_state(payload(known_sequence=["live"])))
        self.assertEqual(self.view._draw_sequence.call_count, 2)

    def test_waiting_does_not_redraw_repeatedly(self):
        for _ in range(500):
            ui.BridgeApp._render_waiting(self.view)
        self.view._draw_sequence.assert_called_once_with([])


class InstallerTests(unittest.TestCase):
    def test_manifest_hashes_are_valid(self):
        for digest in [installer.GAME_SHA256, *installer.SCRIPT_HASHES.values()]:
            self.assertEqual(len(digest), 64)
            self.assertEqual(bytes.fromhex(digest).hex(), digest)

    def test_shell_spawner_patch(self):
        # Synthetic API-shaped fixture, not a copy of a game script.
        original = installer.STARTUP + "\nfunc demo():\n\troundManager.LoadShells()\n\tlocationIndex = 0\n"
        result = installer.patch_script("ShellSpawner.gd", original, "const MEMORY_STATE_PATH = 'test'\n")
        self.assertEqual(result.count("\tMemoryResetKnown()"), 2)
        self.assertNotIn(installer.STARTUP, result)

    def test_phone_and_magnifier_hooks(self):
        phone = "\t\tif(randindex == 8 or randindex == 7): randindex -= 1\n"
        examine = "\tvar shellState = shellSpawner.sequenceArray[0]\n"
        self.assertIn("sh.MemoryMarkKnown(randindex)", installer.patch_script("BurnerPhone.gd", phone, ""))
        self.assertIn("shellSpawner.MemoryMarkKnown(0)", installer.patch_script("ShellExamine.gd", examine, ""))

    def test_rejects_missing_duplicate_or_patched_anchors(self):
        for source in ("unknown", "anchor anchor"):
            with self.assertRaises(ValueError):
                installer.replace_once(source, "anchor", "replacement")
        with self.assertRaises(ValueError):
            installer.patch_script("ShellSpawner.gd", "const MEMORY_STATE_PATH = 'x'", "")

    def test_refuses_original_or_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / "Game.exe"
            game.write_bytes(b"original")
            for output in (game, game.parent / "existing.exe"):
                if output != game:
                    output.write_bytes(b"existing")
                with self.assertRaises((ValueError, FileExistsError)):
                    installer.validate_output(game, output)
            self.assertEqual(game.read_bytes(), b"original")

    def test_unsupported_game_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / "Game.exe"
            game.write_bytes(b"not the supported game")
            with self.assertRaises(ValueError):
                installer.validate_game(game)


if __name__ == "__main__":
    unittest.main()
