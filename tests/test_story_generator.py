import unittest
from collections import Counter
from src.story_generator import ENDING_THEMES, select_ending_theme

class TestEndingThemeSelection(unittest.TestCase):
    def test_ending_themes_structure(self):
        """Verify each theme has required fields and correct weights."""
        expected_weights = {
            "bright": 3,
            "dystopia": 2,
            "romance": 3,
            "mystery": 2,
        }
        self.assertEqual(len(ENDING_THEMES), 4)
        for theme in ENDING_THEMES:
            self.assertIn("id", theme)
            self.assertIn("name", theme)
            self.assertIn("weight", theme)
            self.assertIn("description", theme)
            self.assertEqual(theme["weight"], expected_weights[theme["id"]])

    def test_explicit_theme_selection(self):
        """Verify that passing an explicit theme returns the correct theme."""
        self.assertEqual(select_ending_theme("bright")["id"], "bright")
        self.assertEqual(select_ending_theme("dystopia")["id"], "dystopia")
        self.assertEqual(select_ending_theme("romance")["id"], "romance")
        self.assertEqual(select_ending_theme("mystery")["id"], "mystery")

        # Test by Japanese name
        self.assertEqual(select_ending_theme("明るい未来")["id"], "bright")
        self.assertEqual(select_ending_theme("ディストピア")["id"], "dystopia")
        self.assertEqual(select_ending_theme("ラブロマンス")["id"], "romance")
        self.assertEqual(select_ending_theme("ミステリー")["id"], "mystery")

    def test_random_theme_weights_distribution(self):
        """Verify that 3:2:3:2 weighted distribution behaves as expected statistically."""
        sample_size = 5000
        counts = Counter()
        for _ in range(sample_size):
            theme = select_ending_theme(preferred="random")
            counts[theme["id"]] += 1

        # Expected proportions:
        # bright: 30% (0.30)
        # dystopia: 20% (0.20)
        # romance: 30% (0.30)
        # mystery: 20% (0.20)
        # Tolerance: +/- 4%
        bright_ratio = counts["bright"] / sample_size
        dystopia_ratio = counts["dystopia"] / sample_size
        romance_ratio = counts["romance"] / sample_size
        mystery_ratio = counts["mystery"] / sample_size

        self.assertAlmostEqual(bright_ratio, 0.30, delta=0.04)
        self.assertAlmostEqual(dystopia_ratio, 0.20, delta=0.04)
        self.assertAlmostEqual(romance_ratio, 0.30, delta=0.04)
        self.assertAlmostEqual(mystery_ratio, 0.20, delta=0.04)

if __name__ == "__main__":
    unittest.main()
