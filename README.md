# robot-test-split

Split a Robot Framework `output.xml` into one XML file (and optionally one HTML log) per test case.

## Features

- Splits a single `output.xml` into individual per-test XML files
- Optionally generates per-test `log.html` files via `rebot`
- Optionally generates a Markdown summary report of FAIL/SKIP tests
- Auto-discovers `output.xml` and `log.html` files recursively from the current directory with interactive selection
- Rich terminal output with progress bars and tables (when `rich` is installed)

## Requirements

- Python 3.10+
- `robotframework` (for `rebot` / HTML log generation): `pip install robotframework`
- `rich` (optional, for pretty output): `pip install rich`

## Usage

```bash
# Auto-discover files in the current directory (interactive selection)
python test_splitter.py

# Explicit XML input
python test_splitter.py output.xml

# Explicit XML input, always generate HTML logs (skip prompt)
python test_splitter.py output.xml --html

# Provide a log.html — paired output.xml is resolved automatically, HTML logs are generated
python test_splitter.py path/to/log.html

# Custom output directory
python test_splitter.py output.xml -o /tmp/my_results
```

## Output structure

```
split_results/
├── split_xml/
│   ├── 01_TestName_2024-01-01_12-00-00.xml
│   ├── 02_AnotherTest_2024-01-01_12-00-00.xml
│   └── ...
├── split_html/            # only when HTML generation is requested
│   ├── 01_TestName_2024-01-01_12-00-00.log.html
│   └── ...
└── split_robot_report_2024-01-01_12-00-00.md   # only when Markdown report is requested
```

By default files are written to `<script directory>/split_results/`. Use `-o`/`--output-dir` to change this.

## Options

| Flag | Description |
|------|-------------|
| `input` | Path to `output.xml` or `log.html`. Omit to auto-discover. |
| `-o`, `--output-dir` | Directory to write results into (default: `<script dir>/split_results`). |
| `--html` | Skip the HTML prompt and always generate per-test `log.html` files via `rebot`. |

## Example Markdown report

```markdown
# Robot Framework Split Report

**Source:** `/path/to/output.xml`
**Generated:** 2026-03-28 12:50:13
**Total tests:** 10
**FAIL:** 1
**SKIP:** 0
**PASS:** 9

## Failed / Skipped Tests

| # | File | Status |
|---|------|--------|
| 1 | `07_TC07_-_Boolean_Flag_2026-03-28_12-49-59.xml` | **FAIL** |
```
