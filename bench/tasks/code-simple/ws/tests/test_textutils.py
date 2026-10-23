import unittest
from textutils import slugify, truncate_words


class T(unittest.TestCase):
    def test_slug_basic(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_slug_punct(self):
        self.assertEqual(slugify("Hello,  World!"), "hello-world")

    def test_trunc(self):
        self.assertEqual(truncate_words("one two three four", 2), "one two…")

    def test_trunc_short(self):
        self.assertEqual(truncate_words("one two", 5), "one two")


if __name__ == "__main__":
    unittest.main()
