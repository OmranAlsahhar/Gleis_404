"""Command-line entry point for gleis404."""

import argparse

from gleis404 import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser for the gleis404 CLI."""
    parser = argparse.ArgumentParser(
        prog="gleis404",
        description=(
            "Collect realtime public transit departures and analyze "
            "punctuality trends."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the gleis404 command-line interface."""
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
