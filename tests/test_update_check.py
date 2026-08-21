"""Version comparison for the update banner: exactly the class of bug it
exists to avoid is "1.1.9" reading as newer than "1.1.10"."""
import unittest

from app.update_check import _is_newer


class IsNewerTest(unittest.TestCase):
    def test_numeric_not_lexicographic(self):
        self.assertTrue(_is_newer("1.1.10", "1.1.9"))
        self.assertFalse(_is_newer("1.1.9", "1.1.10"))

    def test_equal_is_not_newer(self):
        self.assertFalse(_is_newer("1.1.24", "1.1.24"))

    def test_major_minor_patch_order(self):
        self.assertTrue(_is_newer("2.0.0", "1.9.9"))
        self.assertTrue(_is_newer("1.2.0", "1.1.99"))

    def test_v_prefix_and_junk_tolerated(self):
        self.assertTrue(_is_newer("v1.1.10", "1.1.9"))
        self.assertFalse(_is_newer("not-a-version", "1.1.9"))
