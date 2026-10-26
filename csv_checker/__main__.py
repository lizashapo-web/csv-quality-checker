"""Allow ``python -m csv_checker``."""

import sys

from csv_checker.cli import main

if __name__ == "__main__":
    sys.exit(main())
