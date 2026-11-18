"""Entry point for the packaged desktop app (PyInstaller) and `python omniview.py`."""

from src.app import main

if __name__ == "__main__":
    raise SystemExit(main())
