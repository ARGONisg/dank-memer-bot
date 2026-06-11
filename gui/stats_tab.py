from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout,
    QScrollArea, QFrame
)
from PySide6.QtGui import QFont

class StatsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        container = QWidget()
        container.setObjectName("statsContainer")
        container.setStyleSheet("#statsContainer { background-color: #313338; }")
        layout = QVBoxLayout(container)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setAlignment(Qt.AlignTop)

        stats_group = QGroupBox("Session Statistics")
        stats_form = QFormLayout(stats_group)
        stats_form.setLabelAlignment(Qt.AlignLeft)
        stats_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        stats_form.setContentsMargins(12, 16, 12, 12)

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

        tip_label = QLabel("Statistics update live while bot runs.")
        tip_label.setStyleSheet("color: #949ba4; padding: 8px;")
        tip_label.setWordWrap(True)
        layout.addWidget(tip_label)

        scroll.setWidget(container)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
