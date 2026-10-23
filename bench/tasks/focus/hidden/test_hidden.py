import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from mini import cli


class Hidden(unittest.TestCase):
    def run_stats(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write(text)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.cmd_stats(fh.name)
            return rc, buf.getvalue()
        finally:
            os.unlink(fh.name)

    def test_basic(self):
        rc, out = self.run_stats("hello world\nfoo\n")
        self.assertEqual((rc, out), (0, "lines=2 words=3 chars=16\n"))

    def test_empty(self):
        rc, out = self.run_stats("")
        self.assertEqual((rc, out), (0, "lines=0 words=0 chars=0\n"))

    def test_main_dispatch(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write("a b")
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["stats", fh.name])
            self.assertEqual((rc, buf.getvalue()), (0, "lines=1 words=2 chars=3\n"))
        finally:
            os.unlink(fh.name)
