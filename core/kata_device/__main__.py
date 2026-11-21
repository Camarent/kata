"""Entry point: `python -m kata_device <command> [args...]`."""

import sys

from kata_device.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
