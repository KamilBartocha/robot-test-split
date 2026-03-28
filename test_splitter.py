#!/usr/bin/env python3
"""
Split a Robot Framework output.xml into one XML file per test case.

Usage
-----
  python split_robot_output.py                    # auto-discover files, interactive selection
  python split_robot_output.py output.xml         # explicit XML input
  python split_robot_output.py output.xml --html  # also generate HTML logs without prompting

Discovery
---------
  When no input file is given the script searches the current directory (recursively)
  for output.xml and log.html files and lets the user pick one.  Selecting a log.html
  automatically resolves the paired output.xml from the same directory.

HTML logs
---------
  After XML splitting completes the script asks whether to generate a per-test log.html
  using Robot Framework's `rebot` tool.  Pass --html to skip the prompt and always
  generate HTML logs.  `rebot` must be installed (pip install robotframework).

Output
------
  Files are written to <script directory>/split_results/ by default, in two subdirectories:
    split_results/split_xml/   — one output.xml per test
    split_results/split_html/  — one log.html per test (only when HTML generation is requested)
  Each file is named:  01_TestName.xml  /  01_TestName.log.html
"""

import argparse
import copy
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
    from rich.table import Table

    console = Console()
    HAS_RICH = True
except ImportError:
    console = None
    HAS_RICH = False


# ─── Helpers ─────────────────────────────────────────────────────────────────


def log(msg: str, style: str = "white") -> None:
    if HAS_RICH:
        console.print(f"[{style}]{msg}[/{style}]")  # type: ignore
    else:
        print(msg)


def sanitize_filename(name: str, max_length: int = 80) -> str:
    """Convert a test name to a filesystem-safe string."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", "_", name)
    name = name.strip("._")
    return name[:max_length]


def get_test_status(test_elem: ET.Element) -> str:
    status_el = test_elem.find("status")
    return status_el.get("status", "FAIL") if status_el is not None else "FAIL"


def build_parent_map(root: ET.Element) -> dict:
    return {child: parent for parent in root.iter() for child in parent}


# ─── Statistics ───────────────────────────────────────────────────────────────


def rebuild_statistics(stats_elem: ET.Element, test_elem: ET.Element) -> None:
    """Update statistics so counts reflect only the given single test."""
    status = get_test_status(test_elem)
    pass_v = 1 if status == "PASS" else 0
    fail_v = 1 if status == "FAIL" else 0
    skip_v = 1 if status == "SKIP" else 0

    total_sec = stats_elem.find("total")
    if total_sec is not None:
        for stat in total_sec.findall("stat"):
            stat.set("pass", str(pass_v))
            stat.set("fail", str(fail_v))
            stat.set("skip", str(skip_v))

    test_tags = {t.text for t in test_elem.findall("tag") if t.text}
    tag_sec = stats_elem.find("tag")
    if tag_sec is not None:
        to_remove = []
        for stat in tag_sec.findall("stat"):
            if stat.text not in test_tags:
                to_remove.append(stat)
            else:
                stat.set("pass", str(pass_v))
                stat.set("fail", str(fail_v))
                stat.set("skip", str(skip_v))
        for elem in to_remove:
            tag_sec.remove(elem)

    suite_sec = stats_elem.find("suite")
    if suite_sec is not None:
        for stat in suite_sec.findall("stat"):
            stat.set("pass", str(pass_v))
            stat.set("fail", str(fail_v))
            stat.set("skip", str(skip_v))


# ─── rebot / HTML helpers ─────────────────────────────────────────────────────


def find_rebot() -> list[str] | None:
    """Return a rebot command list, or None if rebot is not available."""
    if shutil.which("rebot"):
        return ["rebot"]
    # Fallback: try via python -m robot.rebot
    result = subprocess.run(
        [sys.executable, "-m", "robot.rebot", "--version"],
        capture_output=True,
    )
    if result.returncode in (0, 251):  # 251 = version printed, non-zero
        return [sys.executable, "-m", "robot.rebot"]
    return None


def generate_html_log(rebot_cmd: list[str], xml_path: Path, log_path: Path) -> bool:
    """Run rebot to produce a single log.html from xml_path. Returns True on success."""
    result = subprocess.run(
        rebot_cmd + [
            "--log", str(log_path),
            "--report", "NONE",
            "--output", "NONE",
            "--nostatusrc",
            str(xml_path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


# ─── Core splitter ────────────────────────────────────────────────────────────


def split_output(input_file: Path, output_dir: Path, generate_html: bool = False) -> None:
    if HAS_RICH:
        console.print(  # type: ignore
            Panel(
                f"[bold cyan]Robot Framework Output Splitter[/bold cyan]\n"
                f"Input : [yellow]{input_file}[/yellow]\n"
                f"Output: [yellow]{output_dir}[/yellow]",
                expand=False,
            )
        )

    # ── Parse ────────────────────────────────────────────────────────────────
    run_dt = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    log("Parsing XML file …", "yellow")
    try:
        tree = ET.parse(input_file)
    except ET.ParseError as exc:
        log(f"ERROR: Could not parse XML: {exc}", "bold red")
        sys.exit(1)

    root = tree.getroot()
    all_tests = list(root.findall(".//test"))
    total = len(all_tests)

    if total == 0:
        log("No <test> elements found in the file.", "bold red")
        sys.exit(1)

    log(f"Found [bold]{total}[/bold] test(s).", "green")

    xml_dir = output_dir / f"split_xml_{run_dt}"
    xml_dir.mkdir(parents=True, exist_ok=True)

    # ── Split XML ────────────────────────────────────────────────────────────
    if HAS_RICH:
        table = Table(title="Split Results", show_lines=False)
        table.add_column("#", style="cyan", justify="right", width=4)
        table.add_column("Test Name", style="white")
        table.add_column("Status", justify="center", width=8)
        table.add_column("XML", style="dim")

    progress_ctx = (
        Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        )
        if HAS_RICH
        else None
    )

    # Collect (xml_path, safe_name, test_name, status) for second-pass operations
    split_files: list[tuple[Path, str, str, str]] = []

    def do_split() -> None:
        for idx, test_elem in enumerate(all_tests, start=1):
            test_name = test_elem.get("name", f"test_{idx}")
            status = get_test_status(test_elem)

            if HAS_RICH and progress_ctx:
                progress_ctx.advance(task, 1)

            new_root = copy.deepcopy(root)
            new_parent_map = build_parent_map(new_root)
            new_all_tests = list(new_root.findall(".//test"))

            keep_test = new_all_tests[idx - 1]
            new_test_parent = new_parent_map[keep_test]
            for t in new_all_tests:
                if t is not keep_test:
                    new_test_parent.remove(t)

            stats_elem = new_root.find("statistics")
            if stats_elem is not None:
                rebuild_statistics(stats_elem, keep_test)

            safe_name = sanitize_filename(test_name)
            xml_filename = f"{idx:02d}_{safe_name}_{run_dt}.xml"
            xml_path = xml_dir / xml_filename

            ET.ElementTree(new_root).write(str(xml_path), encoding="UTF-8", xml_declaration=True)
            split_files.append((xml_path, safe_name, test_name, status))

            status_style = {"PASS": "green", "FAIL": "red", "SKIP": "yellow"}.get(status, "white")
            if HAS_RICH:
                table.add_row(str(idx), test_name, f"[{status_style}]{status}[/{status_style}]", xml_filename)
            else:
                print(f"  [{idx:02d}/{total}] {status:4s}  {xml_filename}")

    if HAS_RICH and progress_ctx:
        with progress_ctx:
            task = progress_ctx.add_task("[cyan]Splitting XML tests…", total=total)
            do_split()
        console.print(table)  # type: ignore
    else:
        print(f"Splitting {total} test(s) into {output_dir} …")
        do_split()

    log(f"\nDone — {total} XML file(s) written to [bold]{xml_dir}[/bold]", "bold green")

    # ── Ask about HTML generation (unless already forced by --html / log.html) ─
    if not generate_html:
        try:
            answer = input("\nGenerate HTML logs via rebot? [y/N]: ").strip().lower()
            generate_html = answer in ("y", "yes")
        except EOFError:
            generate_html = False

    if not generate_html:
        _ask_and_write_report(split_files, output_dir, input_file, run_dt)
        return

    # ── Generate HTML logs ───────────────────────────────────────────────────
    html_dir = output_dir / f"split_html_{run_dt}"
    html_dir.mkdir(parents=True, exist_ok=True)
    rebot_cmd = find_rebot()
    if rebot_cmd is None:
        log("WARNING: rebot not found — install robotframework to generate HTML logs.", "yellow")
        return

    log("\nGenerating HTML logs …", "yellow")

    if HAS_RICH:
        html_table = Table(title="HTML Log Results", show_lines=False)
        html_table.add_column("#", style="cyan", justify="right", width=4)
        html_table.add_column("HTML log", style="white")
        html_table.add_column("Result", justify="center", width=8)

    html_progress = (
        Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        )
        if HAS_RICH
        else None
    )

    def do_html() -> None:
        for idx, (xml_path, safe_name, _tname, _status) in enumerate(split_files, start=1):
            if HAS_RICH and html_progress:
                html_progress.advance(html_task, 1)

            html_filename = f"{idx:02d}_{safe_name}_{run_dt}.log.html"
            ok = generate_html_log(rebot_cmd, xml_path, html_dir / html_filename)

            if HAS_RICH:
                result_cell = "[green]OK[/green]" if ok else "[red]FAILED[/red]"
                html_table.add_row(str(idx), html_filename, result_cell)
            else:
                print(f"  [{idx:02d}/{total}] {'OK' if ok else 'FAILED'}  {html_filename}")

    if HAS_RICH and html_progress:
        with html_progress:
            html_task = html_progress.add_task("[cyan]Generating HTML logs…", total=total)
            do_html()
        console.print(html_table)  # type: ignore
    else:
        do_html()

    log(f"\nDone — {total} HTML log(s) written to [bold]{html_dir}[/bold]", "bold green")

    # ── Ask about Markdown report ────────────────────────────────────────────
    _ask_and_write_report(split_files, output_dir, input_file, run_dt)


def _ask_and_write_report(
    split_files: list[tuple[Path, str, str, str]],
    output_dir: Path,
    input_file: Path,
    run_dt: str,
) -> None:
    """Prompt the user to generate a Markdown report of FAIL/SKIP tests."""
    try:
        answer = input("\nGenerate Markdown report? [y/N]: ").strip().lower()
    except EOFError:
        return
    if answer not in ("y", "yes"):
        return

    report_path = output_dir / f"split_robot_report_{run_dt}.md"
    non_pass = [(p, sn, tn, st) for p, sn, tn, st in split_files if st != "PASS"]

    lines: list[str] = [
        "# Robot Framework Split Report",
        f"\n**Source:** `{input_file}`",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total tests:** {len(split_files)}",
        f"**FAIL:** {sum(1 for *_, st in split_files if st == 'FAIL')}",
        f"**SKIP:** {sum(1 for *_, st in split_files if st == 'SKIP')}",
        f"**PASS:** {sum(1 for *_, st in split_files if st == 'PASS')}",
        "",
    ]

    if non_pass:
        lines += [
            "## Failed / Skipped Tests",
            "",
            "| # | File | Status |",
            "|---|------|--------|",
        ]
        for i, (xml_path, _safe, test_name, status) in enumerate(non_pass, start=1):
            lines.append(f"| {i} | `{xml_path.name}` | **{status}** |")
    else:
        lines.append("All tests passed.")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"\nMarkdown report written to [bold]{report_path}[/bold]", "bold green")


# ─── File discovery & selection ───────────────────────────────────────────────

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
    if HAS_RICH:
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


# ─── Entry point ─────────────────────────────────────────────────────────────


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
        default=str(Path(__file__).parent / "split_results"),
        help="Directory to write split files into (default: <script dir>/split_results)",
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
