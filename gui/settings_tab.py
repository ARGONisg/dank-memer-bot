from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLineEdit,
    QComboBox, QDoubleSpinBox, QPushButton, QLabel, QScrollArea, QFrame
)

RARITIES = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Exotic", "Mythical"]
SELL_CURRENCIES = ["Coins", "Fish Points"]
BAIT_ITEMS = ["None", "Bread", "Worms", "Soggy Salad", "Magical Bait", "Minnow", "Shrimp", "Squid"]
EQUIP_ITEMS = ["None", "Fishing Rod", "Fibreglass Rod", "Golden Rod", "Diamond Rod", "Lava Rod", "Galactic Rod"]

GROUP_STYLE = "QGroupBox { max-width: 500px; }"

def _make_form(group):
    f = QFormLayout(group)
    f.setLabelAlignment(Qt.AlignLeft)
    f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    f.setContentsMargins(12, 16, 12, 12)
    f.setHorizontalSpacing(16)
    f.setVerticalSpacing(8)
    return f

class SettingsTab(QWidget):
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
        container.setObjectName("settingsContainer")
        container.setStyleSheet("#settingsContainer { background-color: #313338; }")
        layout = QVBoxLayout(container)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setAlignment(Qt.AlignTop)

        # ── Command Settings ──
        cmd_group = QGroupBox("Command Settings")
        cmd_form = _make_form(cmd_group)
        self.prefix_input = QLineEdit(self.config.get("command_prefix", "pls "))
        self.username_input = QLineEdit(self.config.get("discord_username", "Xenron"))
        self.fish_command_input = QLineEdit(self.config.get("fish_command", "fish catch"))
        self.bj_command_input = QLineEdit(self.config.get("bj_command", "bj 5k"))
        self.slots_command_input = QLineEdit(self.config.get("slots_command", "slots 100"))
        cmd_form.addRow("Prefix:", self.prefix_input)
        cmd_form.addRow("Discord Username:", self.username_input)
        cmd_form.addRow("Fish Command:", self.fish_command_input)
        cmd_form.addRow("Blackjack Command:", self.bj_command_input)
        cmd_form.addRow("Slots Command:", self.slots_command_input)
        layout.addWidget(cmd_group)

        # ── Gear Configuration ──
        gear_group = QGroupBox("Gear Configuration")
        gear_form = _make_form(gear_group)
        self.bait_combo = QComboBox()
        self.bait_combo.addItems(BAIT_ITEMS)
        bait_idx = self.bait_combo.findText(self.config.get("fish_bait", "None"))
        if bait_idx >= 0: self.bait_combo.setCurrentIndex(bait_idx)
        self.equip_combo = QComboBox()
        self.equip_combo.addItems(EQUIP_ITEMS)
        equip_idx = self.equip_combo.findText(self.config.get("fish_equipment", "None"))
        if equip_idx >= 0: self.equip_combo.setCurrentIndex(equip_idx)
        gear_form.addRow("Bait:", self.bait_combo)
        gear_form.addRow("Equipment:", self.equip_combo)
        layout.addWidget(gear_group)

        # ── Rarity & Sell ──
        sell_group = QGroupBox("Sell / Keep Strategy")
        sell_form = _make_form(sell_group)
        self.rarity_combo = QComboBox()
        self.rarity_combo.addItems(RARITIES)
        rarity_idx = self.rarity_combo.findText(self.config.get("min_rarity_to_keep", "Rare"))
        if rarity_idx >= 0: self.rarity_combo.setCurrentIndex(rarity_idx)
        self.sell_currency_combo = QComboBox()
        self.sell_currency_combo.addItems(SELL_CURRENCIES)
        curr_idx = self.sell_currency_combo.findText(self.config.get("sell_currency_pref", "Coins"))
        if curr_idx >= 0: self.sell_currency_combo.setCurrentIndex(curr_idx)
        sell_form.addRow("Min Rarity to Keep:", self.rarity_combo)
        sell_form.addRow("Sell For:", self.sell_currency_combo)
        layout.addWidget(sell_group)

        # ── Timing & Calibration ──
        timing_group = QGroupBox("Timing & Calibration")
        timing_form = _make_form(timing_group)
        self.cooldown_spin = QDoubleSpinBox()
        self.cooldown_spin.setRange(5.0, 300.0)
        self.cooldown_spin.setValue(self.config.get("fish_cooldown", 35.0))
        self.cooldown_spin.setSuffix(" sec")
        self.min_delay_spin = QDoubleSpinBox()
        self.min_delay_spin.setRange(0.1, 5.0)
        self.min_delay_spin.setValue(self.config.get("min_typing_delay", 0.5))
        self.min_delay_spin.setSingleStep(0.1)
        self.max_delay_spin = QDoubleSpinBox()
        self.max_delay_spin.setRange(0.2, 10.0)
        self.max_delay_spin.setValue(self.config.get("max_typing_delay", 0.9))
        self.max_delay_spin.setSingleStep(0.1)
        self.calibrate_btn = QPushButton("Calibrate Cooldown")
        self.calibrate_btn.setStyleSheet("QPushButton { background-color: #5865F2; color: #ffffff; font-weight: 600; } QPushButton:hover { background-color: #4752C4; }")
        timing_form.addRow("Fish Cooldown:", self.cooldown_spin)
        timing_form.addRow("", self.calibrate_btn)
        timing_form.addRow("Min Typing Delay:", self.min_delay_spin)
        timing_form.addRow("Max Typing Delay:", self.max_delay_spin)
        layout.addWidget(timing_group)

        # ── Emergency Key ──
        safety_group = QGroupBox("Safety")
        safety_form = _make_form(safety_group)
        self.emergency_key_input = QLineEdit(self.config.get("emergency_key", "esc"))
        safety_form.addRow("Killswitch Key:", self.emergency_key_input)
        layout.addWidget(safety_group)

        scroll.setWidget(container)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def sync_to_config(self, config):
        config.set("command_prefix", self.prefix_input.text())
        config.set("discord_username", self.username_input.text())
        config.set("fish_command", self.fish_command_input.text())
        config.set("bj_command", self.bj_command_input.text())
        config.set("slots_command", self.slots_command_input.text())
        config.set("fish_bait", self.bait_combo.currentText())
        config.set("fish_equipment", self.equip_combo.currentText())
        config.set("min_rarity_to_keep", self.rarity_combo.currentText())
        config.set("sell_currency_pref", self.sell_currency_combo.currentText())
        config.set("fish_cooldown", self.cooldown_spin.value())
        config.set("min_typing_delay", self.min_delay_spin.value())
        config.set("max_typing_delay", self.max_delay_spin.value())
        config.set("emergency_key", self.emergency_key_input.text())
