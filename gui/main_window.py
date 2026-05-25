import time
from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QTextEdit, QLabel, QGroupBox, QVBoxLayout as VBox
)
from PySide6.QtGui import QFont

from gui.styles import QSS
from gui.settings_tab import SettingsTab
from gui.scheduler_tab import SchedulerTab
from gui.stats_tab import StatsTab
from gui.webhook_tab import WebhookTab
from bot.config import ConfigManager
from bot.engine import BotEngine
from bot.webhook import test_webhook, build_session_embed, send_webhook

class BotLogSignals(QObject):
    log_signal = Signal(str)
    status_signal = Signal(str)
    cooldown_signal = Signal(float)
    stopped_signal = Signal()
    stats_signal = Signal(dict)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dank Memer Automation Framework")
        self.resize(820, 620)
        self.setStyleSheet(QSS)

        self.config = ConfigManager("default")
        self.signals = BotLogSignals()
        self.signals.log_signal.connect(self.append_log)
        self.signals.cooldown_signal.connect(self.update_cooldown_field)
        self.signals.stopped_signal.connect(self.on_bot_stopped)
        self.signals.stats_signal.connect(self.update_stats)

        self.bot = BotEngine(self.config, self.signals)
        self.bot_thread = None

        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(6)

        # Title
        title = QLabel("Dank Memer Automation Dashboard")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #b4befe; margin-bottom: 6px;")
        main_layout.addWidget(title)

        # Tabs
        self.tabs = QTabWidget()
        self.settings_tab = SettingsTab(self.config)
        self.scheduler_tab = SchedulerTab(self.config)
        self.stats_tab = StatsTab()
        self.webhook_tab = WebhookTab(self.config)

        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.addTab(self.scheduler_tab, "Scheduler")
        self.tabs.addTab(self.stats_tab, "Statistics")
        self.tabs.addTab(self.webhook_tab, "Webhook")
        main_layout.addWidget(self.tabs)

        # Log area
        log_group = QGroupBox("Activity Logs")
        log_layout = VBox(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group)

        # Start / Stop buttons
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("START BOT")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self.start_bot)
        self.settings_tab.calibrate_btn.clicked.connect(self.bot.calibrate_cooldown)
        self.webhook_tab.test_btn.clicked.connect(self.test_webhook)

        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_bot)

        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        main_layout.addLayout(btn_layout)

        footer = QLabel("Killswitch: Press ESC or q globally to abort.")
        footer.setStyleSheet("color: #f38ba8; font-size: 11px;")
        footer.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(footer)

        self.append_log("[+] Dashboard ready. Configure your settings and press START.")

    @Slot(str)
    def append_log(self, text):
        self.log_text.append(text)
        self.log_text.ensureCursorVisible()

    @Slot(float)
    def update_cooldown_field(self, val):
        self.settings_tab.cooldown_spin.setValue(val)

    @Slot(dict)
    def update_stats(self, stats):
        if stats.get("periodic_summary"):
            self._send_periodic_summary(stats)
            return

        if "casts" in stats:
            self.stats_tab.casts_label.setText(str(stats["casts"]))
        if "catches" in stats:
            self.stats_tab.catches_label.setText(str(stats["catches"]))
        if "sells" in stats:
            self.stats_tab.sells_label.setText(str(stats["sells"]))
        if "errors" in stats:
            self.stats_tab.errors_label.setText(str(stats["errors"]))
        if "rare_kept" in stats:
            self.stats_tab.rare_kept_label.setText(str(stats["rare_kept"]))
        if "earnings" in stats:
            self.stats_tab.earnings_label.setText(f"{stats['earnings']} coins")
        if "session_time" in stats:
            secs = stats["session_time"]
            m, s = divmod(int(secs), 60)
            h, m = divmod(m, 60)
            if h:
                self.stats_tab.session_time_label.setText(f"{h}h {m}m {s}s")
            else:
                self.stats_tab.session_time_label.setText(f"{m}m {s}s")

    def test_webhook(self):
        url = self.webhook_tab.url_input.text().strip()
        if not url:
            self.append_log("[!] No webhook URL configured.")
            return
        self.append_log("[*] Testing webhook...")
        result = test_webhook(url)
        if result["ok"]:
            self.append_log("[+] Webhook test successful.")
        else:
            self.append_log(f"[!] Webhook test failed: {result['error']}")

    def start_bot(self):
        self.append_log("[*] Syncing configuration and starting bot...")
        self.settings_tab.sync_to_config(self.config)
        self.scheduler_tab.sync_to_config(self.config)
        self.webhook_tab.sync_to_config(self.config)
        self.config.save_profile()

        self.bot.apply_config()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        from threading import Thread
        self.bot_thread = Thread(target=self.bot.run_loop, daemon=True)
        self.bot_thread.start()

    def stop_bot(self):
        self.append_log("[*] Stopping bot...")
        self.bot.running = False

    @Slot()
    def on_bot_stopped(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.append_log("[*] Bot stopped.")
        self._send_session_summary()

    def _send_session_summary(self):
        url = self.webhook_tab.url_input.text().strip()
        enabled = self.webhook_tab.enable_check.isChecked()
        summary_events = self.webhook_tab.on_summary_check.isChecked()
        if not url or not enabled or not summary_events:
            self.append_log("[*] Webhook summary disabled — skip.")
            return
        duration = int(time.time() - self.bot.stats.get("session_start", time.time()))
        embed = build_session_embed(self.bot.stats, duration)
        result = send_webhook(url, embed=embed)
        if result["ok"]:
            self.append_log("[+] Session summary sent via webhook.")
        else:
            self.append_log(f"[!] Failed to send session summary: {result['error']}")

    def _send_periodic_summary(self, stats):
        url = self.webhook_tab.url_input.text().strip()
        enabled = self.webhook_tab.enable_check.isChecked()
        if not url or not enabled:
            return
        duration = int(time.time() - self.bot.stats.get("session_start", time.time()))
        embed = build_session_embed(stats, duration)
        result = send_webhook(url, embed=embed)
        if result["ok"]:
            self.append_log("[+] Hourly summary sent via webhook.")
        else:
            self.append_log(f"[!] Hourly summary failed: {result['error']}")

    def closeEvent(self, event):
        self.bot.running = False
        self.config.save_profile()
        event.accept()
