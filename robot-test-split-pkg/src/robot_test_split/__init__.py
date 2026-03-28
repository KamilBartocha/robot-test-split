"""
robot_test_split — Split a Robot Framework output.xml into one file per test case.
"""

from .splitter import split_output

__version__ = "0.1.0"
__all__ = ["split_output"]
