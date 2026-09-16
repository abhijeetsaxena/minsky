"""Enables `python -m minsky "<intent text>"`."""

import sys

from minsky.cli import main

if __name__ == "__main__":
    sys.exit(main())
