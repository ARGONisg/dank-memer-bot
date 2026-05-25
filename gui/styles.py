QSS = """
QMainWindow { background-color: #313338; }
QWidget { color: #dbdee1; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }
QGroupBox {
    border: 1px solid #3f4147; border-radius: 4px; margin-top: 14px;
    font-weight: 600; color: #f2f3f5; background-color: #2b2d31; padding: 12px 8px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 6px;
}
QLabel { color: #dbdee1; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #1e1f22; border: 1px solid #3f4147;
    border-radius: 3px; padding: 5px 8px; color: #dbdee1;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #5865F2;
}
QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border-radius: 4px;
    border: 2px solid #4e5058; background-color: #1e1f22;
}
QCheckBox::indicator:checked {
    background-color: #5865F2; border-color: #5865F2;
}
QPushButton {
    background-color: #4e5058; border: none; border-radius: 3px;
    padding: 8px 16px; font-weight: 500; color: #f2f3f5;
}
QPushButton:hover { background-color: #6d6f78; }
QPushButton:pressed { background-color: #80848e; }
QPushButton#startBtn { background-color: #23a55a; color: #ffffff; font-size: 14px; font-weight: 600; }
QPushButton#startBtn:hover { background-color: #2dc770; }
QPushButton#startBtn:disabled { background-color: #4e5058; color: #949ba4; }
QPushButton#stopBtn { background-color: #da373c; color: #ffffff; font-size: 14px; font-weight: 600; }
QPushButton#stopBtn:hover { background-color: #e04e52; }
QPushButton#stopBtn:disabled { background-color: #4e5058; color: #949ba4; }
QTabWidget::pane {
    border: 1px solid #3f4147; border-radius: 4px; background-color: #313338;
    top: -1px;
}
QTabBar::tab {
    background-color: #2b2d31; border: 1px solid #3f4147; border-bottom: none;
    padding: 8px 16px; margin-right: 1px;
    border-top-left-radius: 4px; border-top-right-radius: 4px;
    color: #949ba4;
}
QTabBar::tab:selected {
    background-color: #383a40; color: #f2f3f5; font-weight: 600;
    border-bottom: 2px solid #5865F2;
}
QTabBar::tab:hover:!selected { background-color: #383a40; color: #dbdee1; }
QTextEdit {
    background-color: #111214; border: 1px solid #3f4147; border-radius: 4px;
    color: #a6e3a1; font-family: 'Consolas', 'Courier New', 'monospace'; font-size: 12px;
    padding: 8px;
}
QScrollBar:vertical {
    background-color: #1e1f22; width: 8px; margin: 0; border: none;
}
QScrollBar::handle:vertical {
    background-color: #4e5058; min-height: 30px; border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background-color: #6d6f78; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 0; }
"""
