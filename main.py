#!/usr/bin/env python3
"""
Dank Memer Automation Framework — Application Entry Point.

Initialises:
  1. Project root in sys.path (for reliable imports from subdirectories).
  2. Logging (file + stdout) at DEBUG level.
  3. VisionEngine debug mode (saves annotated screenshots to data/debug/).
  4. QApplication with Discord-dark style.
  5. MainWindow (the root GUI).

Invocation:
    python3 main.py          # Launch the GUI
    python3 main.py --headless  # (future) headless CLI mode
"""

import sys
import os
import logging

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow
from bot.vision import VisionEngine

def setup_logging():
    log_dir = os.path.join(project_root, "data")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "dankbot.log")

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="a"),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    setup_logging()
    # Enable debug screenshot dumping to data/debug/ when OCR fails
    VisionEngine.enable_debug(True)
    logger = logging.getLogger("DankBot.Main")
    logger.info("Starting Dank Memer Automation Framework...")

    app = QApplication(sys.argv)
    app.setApplicationName("Dank Memer Bot")
    app.setOrganizationName("Antigravity")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
