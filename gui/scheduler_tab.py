from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QCheckBox, QLabel, QSpinBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QScrollArea, QFrame
)
from gui.draggable import DraggableGroupBox, DraggableCanvas

class SchedulerTab(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config
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
        container.setObjectName("schedulerContainer")
        container.setStyleSheet("#schedulerContainer { background-color: #313338; }")
        
        # ── Activity Settings ──
        act_group = DraggableGroupBox("Activity Settings", container)
        act_form = QFormLayout(act_group)
        act_form.setLabelAlignment(Qt.AlignLeft)
        act_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        act_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        act_form.setContentsMargins(15, 15, 15, 15)
        act_form.setHorizontalSpacing(20)
        act_form.setVerticalSpacing(10)
        
        self.fish_check = QCheckBox("Enable Fishing")
        self.fish_check.setChecked(self.config.get("fish_enabled", True))
        
        self.bj_check = QCheckBox("Enable Blackjack")
        self.bj_check.setChecked(self.config.get("bj_enabled", False))
        
        self.bj_cooldown_spin = QDoubleSpinBox()
        self.bj_cooldown_spin.setRange(5.0, 300.0)
        self.bj_cooldown_spin.setValue(self.config.get("bj_cooldown", 45.0))
        self.bj_cooldown_spin.setSuffix(" sec")
        
        self.slots_check = QCheckBox("Enable Slots")
        self.slots_check.setChecked(self.config.get("slots_enabled", False))
        
        self.slots_cooldown_spin = QDoubleSpinBox()
        self.slots_cooldown_spin.setRange(5.0, 300.0)
        self.slots_cooldown_spin.setValue(self.config.get("slots_cooldown", 20.0))
        self.slots_cooldown_spin.setSuffix(" sec")
        
        act_form.addRow("Fishing:", self.fish_check)
        act_form.addRow("Blackjack:", self.bj_check)
        act_form.addRow("Blackjack Cooldown:", self.bj_cooldown_spin)
        act_form.addRow("Slots:", self.slots_check)
        act_form.addRow("Slots Cooldown:", self.slots_cooldown_spin)

        # ── Break Settings ──
        break_group = DraggableGroupBox("Human Break Settings", container)
        break_form = QFormLayout(break_group)
        break_form.setLabelAlignment(Qt.AlignLeft)
        break_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        break_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        break_form.setContentsMargins(15, 15, 15, 15)
        break_form.setHorizontalSpacing(20)
        break_form.setVerticalSpacing(10)

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

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def sync_to_config(self, config):
        config.set("fish_enabled", self.fish_check.isChecked())
        config.set("bj_enabled", self.bj_check.isChecked())
        config.set("bj_cooldown", self.bj_cooldown_spin.value())
        config.set("slots_enabled", self.slots_check.isChecked())
        config.set("slots_cooldown", self.slots_cooldown_spin.value())
        config.set("break_interval_mins", self.break_interval_spin.value())
        config.set("break_duration_min_sec", self.break_min_spin.value())
        config.set("break_duration_max_sec", self.break_max_spin.value())
        config.set("random_jitter_percent", self.jitter_spin.value())
