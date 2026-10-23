"""Command line entry point."""
import sys

from mini import stats, textio


def cmd_stats(path):
    """Print statistics for the file at `path`."""
    text = textio.read_text(path)
    print(f"lines={stats.count_lines(text)}")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "stats":
        return cmd_stats(argv[1])
    print("usage: mini stats FILE", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
