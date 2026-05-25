QSS = """
QMainWindow { background-color: #1e1e2e; }
QWidget { color: #cdd6f4; font-family: 'Outfit', 'Inter', sans-serif; font-size: 13px; }
QGroupBox {
    border: 2px solid #31314d; border-radius: 8px; margin-top: 12px;
    font-weight: bold; color: #b4befe; background-color: #252538; padding: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 5px;
}
QLabel { color: #cdd6f4; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox {
    background-color: #181825; border: 1px solid #45475a;
    border-radius: 6px; padding: 5px 8px; color: #cdd6f4;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1.5px solid #b4befe;
}
QPushButton {
    background-color: #313244; border: 1px solid #45475a;
    border-radius: 6px; padding: 8px 16px; font-weight: bold; color: #cdd6f4;
}
QPushButton:hover { background-color: #45475a; border: 1.5px solid #b4befe; }
QPushButton#startBtn { background-color: #a6e3a1; color: #11111b; font-size: 14px; border: none; }
QPushButton#startBtn:hover { background-color: #94e2d5; }
QPushButton#stopBtn { background-color: #f38ba8; color: #11111b; font-size: 14px; border: none; }
QPushButton#stopBtn:hover { background-color: #eba0ac; }
QTabWidget::pane { border: 2px solid #31314d; border-radius: 8px; background-color: #1e1e2e; }
QTabBar::tab {
    background-color: #252538; border: 1px solid #31314d; border-bottom: none;
    padding: 8px 16px; margin-right: 2px; border-top-left-radius: 6px; border-top-right-radius: 6px;
}
QTabBar::tab:selected { background-color: #313244; color: #b4befe; font-weight: bold; }
QTextEdit {
    background-color: #11111b; border: 2px solid #31314d; border-radius: 8px;
    color: #a6e3a1; font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; padding: 10px;
}
QTabBar::tab:hover { background-color: #313244; }
"""
