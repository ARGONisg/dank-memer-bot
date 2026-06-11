from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout,
    QScrollArea, QFrame
)
from PySide6.QtGui import QFont
from gui.draggable import DraggableGroupBox, DraggableCanvas

class StatsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        # Main layout for the widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create a scroll area
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        # Container widget for scroll contents (using DraggableCanvas for thinking board support)
        container = DraggableCanvas()
        container.setObjectName("statsContainer")
        container.setStyleSheet("#statsContainer { background-color: #313338; }")

        stats_group = DraggableGroupBox("Session Statistics", container)
        stats_form = QFormLayout(stats_group)
        stats_form.setLabelAlignment(Qt.AlignLeft)
        stats_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        stats_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        stats_form.setContentsMargins(15, 15, 15, 15)
        stats_form.setHorizontalSpacing(20)
        stats_form.setVerticalSpacing(10)

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

        # Tips Card
        tip_group = DraggableGroupBox("Dashboard Tips", container)
        tip_layout = QVBoxLayout(tip_group)
        tip_layout.setContentsMargins(15, 15, 15, 15)
        tip_label = QLabel("Statistics will update live once the bot is running.")
        tip_label.setStyleSheet("color: #fab387;")
        tip_label.setWordWrap(True)
        tip_layout.addWidget(tip_label)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)
