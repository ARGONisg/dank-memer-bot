from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout
from PySide6.QtGui import QFont

class StatsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        stats_group = QGroupBox("Session Statistics")
        stats_form = QFormLayout(stats_group)

        self.session_time_label = QLabel("0s")
        self.casts_label = QLabel("0")
        self.catches_label = QLabel("0")
        self.sells_label = QLabel("0")
        self.errors_label = QLabel("0")
        self.rare_kept_label = QLabel("0")
        self.earnings_label = QLabel("0 coins")

        stats_form.addRow("Session Time:", self.session_time_label)
        stats_form.addRow("Total Casts:", self.casts_label)
        stats_form.addRow("Total Catches:", self.catches_label)
        stats_form.addRow("Total Sells:", self.sells_label)
        stats_form.addRow("Rare Kept:", self.rare_kept_label)
        stats_form.addRow("Errors:", self.errors_label)
        stats_form.addRow("Estimated Earnings:", self.earnings_label)

        layout.addWidget(stats_group)

        tip_label = QLabel("Statistics will update live once the bot is running.")
        tip_label.setStyleSheet("color: #fab387; padding: 10px; background-color: #313244; border-radius: 6px;")
        tip_label.setWordWrap(True)
        layout.addWidget(tip_label)
        layout.addStretch()
