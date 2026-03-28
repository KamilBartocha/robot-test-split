"""
Core splitting logic: split_output() and _ask_and_write_report().
"""

import copy
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from .html import find_rebot, generate_html_log
from .utils import (
    HAS_RICH,
    build_parent_map,
    console,
    get_test_status,
    log,
    rebuild_statistics,
    sanitize_filename,
)

try:
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
    from rich.table import Table
except ImportError:
    Panel = None  # type: ignore
    Progress = None  # type: ignore
    Table = None  # type: ignore


def split_output(input_file: Path, output_dir: Path, generate_html: bool = False) -> None:
    if HAS_RICH and Panel is not None:
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
    if HAS_RICH and Table is not None:
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
        if HAS_RICH and Progress is not None
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
            if HAS_RICH and Table is not None:
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

    if HAS_RICH and Table is not None:
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
        if HAS_RICH and Progress is not None
        else None
    )

    def do_html() -> None:
        for idx, (xml_path, safe_name, _tname, _status) in enumerate(split_files, start=1):
            if HAS_RICH and html_progress:
                html_progress.advance(html_task, 1)

            html_filename = f"{idx:02d}_{safe_name}_{run_dt}.log.html"
            ok = generate_html_log(rebot_cmd, xml_path, html_dir / html_filename)

            if HAS_RICH and Table is not None:
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
