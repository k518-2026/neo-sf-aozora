import unittest
from collections import Counter
from src.story_generator import (
    ENDING_THEMES,
    select_ending_theme,
    clean_doi_string,
    extract_dois_from_text,
)

class TestEndingThemeSelection(unittest.TestCase):
    def test_ending_themes_structure(self):
        """Verify each theme has required fields and correct weights."""
        expected_weights = {
            "bright": 3,
            "dystopia": 2,
            "romance": 3,
            "mystery": 2,
            "parody": 3,
        }
        self.assertEqual(len(ENDING_THEMES), 5)
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
        self.assertEqual(select_ending_theme("parody")["id"], "parody")

        # Test by Japanese name
        self.assertEqual(select_ending_theme("明るい未来")["id"], "bright")
        self.assertEqual(select_ending_theme("ディストピア")["id"], "dystopia")
        self.assertEqual(select_ending_theme("ラブロマンス")["id"], "romance")
        self.assertEqual(select_ending_theme("ミステリー")["id"], "mystery")
        self.assertEqual(select_ending_theme("パロディー・風刺コメディ")["id"], "parody")

    def test_random_theme_weights_distribution(self):
        """Verify that 3:2:3:2:3 weighted distribution behaves as expected statistically."""
        sample_size = 5000
        counts = Counter()
        for _ in range(sample_size):
            theme = select_ending_theme(preferred="random")
            counts[theme["id"]] += 1

        # Expected proportions (total weight = 13):
        # bright: 3/13 ≈ 0.231
        # dystopia: 2/13 ≈ 0.154
        # romance: 3/13 ≈ 0.231
        # mystery: 2/13 ≈ 0.154
        # parody: 3/13 ≈ 0.231
        # Tolerance: +/- 4%
        bright_ratio = counts["bright"] / sample_size
        dystopia_ratio = counts["dystopia"] / sample_size
        romance_ratio = counts["romance"] / sample_size
        mystery_ratio = counts["mystery"] / sample_size
        parody_ratio = counts["parody"] / sample_size

        self.assertAlmostEqual(bright_ratio, 3 / 13, delta=0.04)
        self.assertAlmostEqual(dystopia_ratio, 2 / 13, delta=0.04)
        self.assertAlmostEqual(romance_ratio, 3 / 13, delta=0.04)
        self.assertAlmostEqual(mystery_ratio, 2 / 13, delta=0.04)
        self.assertAlmostEqual(parody_ratio, 3 / 13, delta=0.04)

    def test_doi_extraction_with_parentheses(self):
        """Ensure DOIs containing parentheses like 10.1016/0031-9201(81)90046-7 are extracted intact."""
        md = (
            "1. Dziewonski, A. M., & Anderson, D. L. (1981). Preliminary reference Earth model. "
            "[https://doi.org/10.1016/0031-9201(81)90046-7](https://doi.org/10.1016/0031-9201(81)90046-7).\n"
            "2. Tromp, J. (2005). [https://doi.org/10.1111/j.1365-246X.2004.02453.x](https://doi.org/10.1111/j.1365-246X.2004.02453.x)"
        )
        dois = extract_dois_from_text(md)
        self.assertEqual(
            dois,
            ["10.1016/0031-9201(81)90046-7", "10.1111/j.1365-246X.2004.02453.x"]
        )
        self.assertEqual(clean_doi_string("10.1016/0031-9201(81)90046-7)."), "10.1016/0031-9201(81)90046-7")

if __name__ == "__main__":
    unittest.main()
