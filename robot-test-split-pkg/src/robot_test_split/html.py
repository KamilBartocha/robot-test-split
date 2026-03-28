"""
HTML log generation: finding rebot and running it to produce per-test log.html files.
"""

import shutil
import subprocess
import sys
from pathlib import Path


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
