#!/usr/bin/env python3
"""
Dank Memer Automation Framework
Modular, cross-platform macro bot with PySide6 GUI.
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
