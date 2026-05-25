from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QCheckBox, QLineEdit, QPushButton,
    QFormLayout, QLabel, QHBoxLayout
)

class WebhookTab(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        main_group = QGroupBox("Discord Webhook Configuration")
        main_form = QFormLayout(main_group)

        self.enable_check = QCheckBox("Enable Webhook Notifications")
        self.enable_check.setChecked(self.config.get("webhook_enabled", False))

        self.url_input = QLineEdit(self.config.get("webhook_url", ""))
        self.url_input.setPlaceholderText("https://discord.com/api/webhooks/...")

        self.test_btn = QPushButton("Test Webhook")

        main_form.addRow("", self.enable_check)
        main_form.addRow("Webhook URL:", self.url_input)
        main_form.addRow("", self.test_btn)
        layout.addWidget(main_group)

        events_group = QGroupBox("Notification Events")
        events_form = QFormLayout(events_group)
        self.on_start_check = QCheckBox("Bot Started")
        self.on_start_check.setChecked(True)
        self.on_stop_check = QCheckBox("Bot Stopped")
        self.on_stop_check.setChecked(True)
        self.on_error_check = QCheckBox("Error / Intervention Required")
        self.on_error_check.setChecked(True)
        self.on_rare_check = QCheckBox("Rare Catch")
        self.on_rare_check.setChecked(True)
        self.on_break_check = QCheckBox("Break Started / Ended")
        self.on_break_check.setChecked(True)
        self.on_summary_check = QCheckBox("Session Summary (Hourly)")
        self.on_summary_check.setChecked(False)

        events_form.addRow("", self.on_start_check)
        events_form.addRow("", self.on_stop_check)
        events_form.addRow("", self.on_error_check)
        events_form.addRow("", self.on_rare_check)
        events_form.addRow("", self.on_break_check)
        events_form.addRow("", self.on_summary_check)
        layout.addWidget(events_group)

        status_label = QLabel("Webhooks send rich embed messages with session stats and alerts.")
        status_label.setStyleSheet("color: #a6e3a1; padding: 8px;")
        status_label.setWordWrap(True)
        layout.addWidget(status_label)
        layout.addStretch()

    def sync_to_config(self, config):
        config.set("webhook_enabled", self.enable_check.isChecked())
        config.set("webhook_url", self.url_input.text())
