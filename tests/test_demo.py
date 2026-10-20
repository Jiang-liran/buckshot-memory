from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import preview_demo as demo


class DemoTests(unittest.TestCase):
    def test_scenes_have_consistent_counts(self):
        for key in demo.SCENES:
            with self.subTest(scene=key):
                state = demo.demo_state(key)
                self.assertEqual(len(state["sequence"]), state["remaining"])
                self.assertEqual(state["live_options"][0] + state["blank_options"][0], state["remaining"])
                self.assertLessEqual(state["sequence"].count("live"), state["live_options"][0])
                self.assertLessEqual(state["sequence"].count("blank"), state["blank_options"][0])

    def test_shot_consumes_blank_and_shifts_phone_position(self):
        before, after = demo.demo_state("2"), demo.demo_state("3")
        self.assertEqual(before["sequence"][0], "blank")
        self.assertEqual(before["sequence"][1:], after["sequence"])
        self.assertEqual(before["live_options"], after["live_options"])
        self.assertEqual(before["blank_options"][0] - 1, after["blank_options"][0])


if __name__ == "__main__":
    unittest.main()
