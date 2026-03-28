"""
Command-line interface entry point for robot-test-split.
"""

import argparse
import sys
from pathlib import Path

from .discovery import find_robot_files, pick_file_interactive, resolve_xml_for_html
from .splitter import split_output
from .utils import log


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Split a Robot Framework output.xml into one file per test case. "
            "After splitting you will be asked whether to generate per-test HTML logs via rebot. "
            "Pass --html to skip the prompt and always generate them."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        help=(
            "Path to output.xml or log.html. "
            "If omitted, the script searches the current directory."
        ),
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=str(Path.cwd() / "split_results"),
        help="Directory to write split files into (default: ./split_results)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Skip the interactive HTML prompt and always generate per-test log.html files via rebot.",
    )
    args = parser.parse_args()

    generate_html = args.html

    if args.input:
        input_file = Path(args.input)
        if not input_file.exists():
            log(f"ERROR: File not found: {input_file}", "bold red")
            sys.exit(1)
        if input_file.name == "log.html":
            input_file = resolve_xml_for_html(input_file)
            generate_html = True
    else:
        search_root = Path.cwd()
        log(f"Searching for Robot Framework files under [bold]{search_root}[/bold] …", "yellow")
        candidates = find_robot_files(search_root)

        if not candidates:
            log(f"No output.xml or log.html files found under {search_root}.", "bold red")
            sys.exit(1)

        if len(candidates) == 1:
            selected, ftype = candidates[0]
            log(f"Found one file ([bold]{ftype}[/bold]): [bold]{selected}[/bold]", "green")
        else:
            log(f"Found {len(candidates)} file(s).", "green")
            selected, ftype = pick_file_interactive(candidates, search_root)

        log(f"Selected: [bold cyan]{selected}[/bold cyan]", "white")

        if ftype == "HTML":
            input_file = resolve_xml_for_html(selected)
            generate_html = True
        else:
            input_file = selected

    split_output(input_file, Path(args.output_dir), generate_html=generate_html)


if __name__ == "__main__":
    main()
