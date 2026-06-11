from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QCheckBox, QLabel, QSpinBox,
    QFormLayout, QScrollArea, QFrame
)

def _make_form(group):
    f = QFormLayout(group)
    f.setLabelAlignment(Qt.AlignLeft)
    f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    f.setContentsMargins(12, 16, 12, 12)
    f.setHorizontalSpacing(16)
    f.setVerticalSpacing(8)
    return f

class SchedulerTab(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.init_ui()

    def init_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        container = QWidget()
        container.setObjectName("schedulerContainer")
        container.setStyleSheet("#schedulerContainer { background-color: #313338; }")
        layout = QVBoxLayout(container)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setAlignment(Qt.AlignTop)

        # ── Activity Toggles ──
        act_group = QGroupBox("Activity Toggles")
        act_layout = QVBoxLayout(act_group)
        act_layout.setContentsMargins(12, 16, 12, 12)
        act_layout.setSpacing(10)

        self.fish_check = QCheckBox("Fishing")
        self.fish_check.setChecked(self.config.get("fish_enabled", True))
        self.bj_check = QCheckBox("Blackjack")
        self.bj_check.setChecked(self.config.get("bj_enabled", False))
        self.slots_check = QCheckBox("Slots")
        self.slots_check.setChecked(self.config.get("slots_enabled", False))
        act_layout.addWidget(self.fish_check)
        act_layout.addWidget(self.bj_check)
        act_layout.addWidget(self.slots_check)
        layout.addWidget(act_group)

        # ── Break Settings ──
        break_group = QGroupBox("Human Break Settings")
        break_form = _make_form(break_group)

        self.break_interval_spin = QSpinBox()
        self.break_interval_spin.setRange(15, 480)
        self.break_interval_spin.setValue(self.config.get("break_interval_mins", 60))
        self.break_interval_spin.setSuffix(" min")

        self.break_min_spin = QSpinBox()
        self.break_min_spin.setRange(30, 1800)
        self.break_min_spin.setValue(self.config.get("break_duration_min_sec", 300))
        self.break_min_spin.setSuffix(" sec")
        self.break_max_spin = QSpinBox()
        self.break_max_spin.setRange(30, 1800)
        self.break_max_spin.setValue(self.config.get("break_duration_max_sec", 600))
        self.break_max_spin.setSuffix(" sec")

        self.jitter_spin = QSpinBox()
        self.jitter_spin.setRange(0, 50)
        self.jitter_spin.setValue(self.config.get("random_jitter_percent", 15))
        self.jitter_spin.setSuffix(" %")

        break_form.addRow("Break Interval:", self.break_interval_spin)
        break_form.addRow("Min Break Duration:", self.break_min_spin)
        break_form.addRow("Max Break Duration:", self.break_max_spin)
        break_form.addRow("Random Jitter:", self.jitter_spin)
        layout.addWidget(break_group)

        scroll.setWidget(container)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def sync_to_config(self, config):
        config.set("fish_enabled", self.fish_check.isChecked())
        config.set("bj_enabled", self.bj_check.isChecked())
        config.set("slots_enabled", self.slots_check.isChecked())
        config.set("break_interval_mins", self.break_interval_spin.value())
        config.set("break_duration_min_sec", self.break_min_spin.value())
        config.set("break_duration_max_sec", self.break_max_spin.value())
        config.set("random_jitter_percent", self.jitter_spin.value())
