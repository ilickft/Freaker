"""
main.py – PyInstaller entry point.
Keep this file thin; all logic lives in src/.
"""
import sys
import os
from pathlib import Path

# When frozen by PyInstaller, _MEIPASS holds extracted files.
if getattr(sys, "frozen", False):
    _src = Path(sys._MEIPASS) / "src"
else:
    _src = Path(__file__).parent / "src"

sys.path.insert(0, str(_src))

from app import main

if __name__ == "__main__":
    main()
