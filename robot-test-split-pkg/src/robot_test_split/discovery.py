"""
File discovery and interactive selection for Robot Framework output files.
"""

import sys
from pathlib import Path

from .utils import HAS_RICH, console, log

try:
    from rich.table import Table
except ImportError:
    Table = None  # type: ignore


_ROBOT_GLOBS = {"output.xml": "XML", "log.html": "HTML"}


def find_robot_files(search_root: Path) -> list[tuple[Path, str]]:
    """Recursively find output.xml and log.html files. Returns list of (path, type)."""
    found: list[tuple[Path, str]] = []
    for name, ftype in _ROBOT_GLOBS.items():
        for p in sorted(search_root.rglob(name)):
            found.append((p, ftype))
    # Sort by path so paired files appear together
    found.sort(key=lambda x: (x[0].parent, x[1]))
    return found


def resolve_xml_for_html(html_file: Path) -> Path:
    """Find output.xml paired with a log.html in the same directory."""
    candidate = html_file.parent / "output.xml"
    if not candidate.exists():
        log(f"ERROR: No output.xml found next to {html_file}", "bold red")
        sys.exit(1)
    return candidate


def pick_file_interactive(candidates: list[tuple[Path, str]], search_root: Path) -> tuple[Path, str]:
    """Present a numbered list and let the user choose one file."""
    if HAS_RICH and Table is not None:
        table = Table(
            title=f"Robot Framework files found under [cyan]{search_root}[/cyan]",
            show_lines=False,
        )
        table.add_column("#", style="cyan", justify="right", width=4)
        table.add_column("Type", style="bold", width=6)
        table.add_column("Full path", style="white")
        for i, (p, ftype) in enumerate(candidates, start=1):
            color = "green" if ftype == "XML" else "blue"
            table.add_row(str(i), f"[{color}]{ftype}[/{color}]", str(p))
        console.print(table)  # type: ignore
    else:
        print(f"\nRobot Framework files found under {search_root}:\n")
        for i, (p, ftype) in enumerate(candidates, start=1):
            print(f"  [{i:>2}] [{ftype:4}] {p}")

    while True:
        try:
            raw = input("\nEnter number to select a file: ").strip()
            choice = int(raw)
            if 1 <= choice <= len(candidates):
                return candidates[choice - 1]
            log(f"Please enter a number between 1 and {len(candidates)}.", "yellow")
        except (ValueError, EOFError):
            log("Invalid input — please enter a number.", "yellow")
