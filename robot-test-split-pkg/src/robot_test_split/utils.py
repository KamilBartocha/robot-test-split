"""
Shared utilities: logging, filename sanitization, XML helpers, statistics rebuilding.
"""

import re
import xml.etree.ElementTree as ET

try:
    from rich.console import Console

    console = Console()
    HAS_RICH = True
except ImportError:
    console = None
    HAS_RICH = False


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
