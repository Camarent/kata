"""Run `kata term` as `python -m kata_term`."""

import sys

from kata_term.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
