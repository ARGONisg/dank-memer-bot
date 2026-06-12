"""
Webhook Tab — Discord webhook configuration for notifications and summaries.

Contains three draggable card groups:
  - Discord Webhook Configuration: enable toggle, URL input, test button
  - Notification Events: checkboxes for which events trigger webhook messages
    (start, stop, error, rare catch, break, hourly summary)
  - Webhook Information: status/tips label
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QCheckBox, QLineEdit, QPushButton,
    QFormLayout, QLabel, QScrollArea, QFrame
)
from gui.draggable import DraggableGroupBox, DraggableCanvas


class WebhookTab(QWidget):
    """Webhook notification configuration tab."""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.init_ui()

    def init_ui(self):
        """Build the scrollable canvas with three draggable cards."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        container = DraggableCanvas()
        container.setObjectName("webhookContainer")
        container.setStyleSheet("#webhookContainer { background-color: #313338; }")

        # ── Webhook Configuration ──
        main_group = DraggableGroupBox("Discord Webhook Configuration", container)
        main_form = QFormLayout(main_group)
        main_form.setLabelAlignment(Qt.AlignLeft)
        main_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        main_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        main_form.setContentsMargins(15, 15, 15, 15)
        main_form.setHorizontalSpacing(20)
        main_form.setVerticalSpacing(10)

        self.enable_check = QCheckBox("Enable Webhook Notifications")
        self.enable_check.setChecked(self.config.get("webhook_enabled", False))
        self.url_input = QLineEdit(self.config.get("webhook_url", ""))
        self.url_input.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.test_btn = QPushButton("Test Webhook")
        main_form.addRow("", self.enable_check)
        main_form.addRow("Webhook URL:", self.url_input)
        main_form.addRow("", self.test_btn)

        # ── Notification Events ──
        events_group = DraggableGroupBox("Notification Events", container)
        events_form = QFormLayout(events_group)
        events_form.setLabelAlignment(Qt.AlignLeft)
        events_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        events_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        events_form.setContentsMargins(15, 15, 15, 15)
        events_form.setHorizontalSpacing(20)
        events_form.setVerticalSpacing(10)

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

        # ── Webhook Info Card ──
        info_group = DraggableGroupBox("Webhook Information", container)
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(15, 15, 15, 15)
        status_label = QLabel("Webhooks send rich embed messages with session stats and alerts.")
        status_label.setStyleSheet("color: #a6e3a1;")
        status_label.setWordWrap(True)
        info_layout.addWidget(status_label)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def sync_to_config(self, config):
        """Write widget values into the ConfigManager settings dict."""
        config.set("webhook_enabled", self.enable_check.isChecked())
        config.set("webhook_url", self.url_input.text())
