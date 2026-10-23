import unittest
from textutils import slugify, truncate_words


class H(unittest.TestCase):
    def test_slug(self):
        for s, e in [("Hello World", "hello-world"), ("Hello,  World!", "hello-world"), ("  --Hi--  ", "hi"),
                     ("a_b c", "a-b-c"), ("Ünï 42", "n-42"), ("", ""), ("!!!", ""), ("x", "x"), ("A  B   C", "a-b-c")]:
            self.assertEqual(slugify(s), e, s)

    def test_trunc(self):
        for s, n, e in [("one two three four", 2, "one two…"), ("one two", 5, "one two"), ("a b c", 3, "a b c"),
                        ("a b c", 0, "…"), ("", 3, ""), ("a  b   c d", 3, "a b c…")]:
            self.assertEqual(truncate_words(s, n), e, (s, n))
