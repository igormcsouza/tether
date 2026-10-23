import unittest

from mini import stats


class StatsTest(unittest.TestCase):
    def test_lines(self):
        self.assertEqual(stats.count_lines("a\nb\n"), 2)

    def test_words(self):
        self.assertEqual(stats.count_words("a b  c"), 3)
