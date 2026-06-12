"""
Main Window — Root QMainWindow for the Dank Memer Bot GUI.

Orchestrates all GUI tabs, the engine lifecycle, signal/slot connections,
cooldown calibration threading, webhook testing, and keyboard killswitch.

Layout
======
  ┌──────────────────────────────────────────────┐
  │           Dank Memer Automation Dashboard     │
  ├──────────┬──────────┬──────────┬─────────────┤
  │ Settings │ Scheduler│Statistics│   Webhook   │  ← QTabWidget
  ├──────────┴──────────┴──────────┴─────────────┤
  │              Activity Logs                    │  ← QTextEdit (read-only)
  ├──────────────────────────────────────────────┤
  │  [START BOT]  [STOP]                         │
  └──────────────────────────────────────────────┘

Signals
=======
  ``BotLogSignals`` carries Qt signals from the background engine thread
  to the GUI thread:
    - log_signal(str)     — appends text to the Activity Logs panel
    - cooldown_signal(float) — updates the cooldown spin box after calibration
    - stopped_signal()    — re-enables START button, disables STOP, sends summary
    - stats_signal(dict)  — updates Statistics tab labels
    - calibration_finished() — re-enables the calibrate button

Engine Lifecycle
================
  start_bot():
    1. Sync all tab configs → ConfigManager → save profile
    2. Apply config to BotEngine
    3. Start BotEngine.run_loop() in a daemon thread

  stop_bot():
    1. Set BotEngine.running = False
    2. Engine thread exits at next tick
    3. stopped_signal fires → on_bot_stopped → re-enable UI + send webhook summary

Killswitch
==========
  ESC key (global ApplicationShortcut) or 'q' key (focused) triggers
  _killswitch_triggered() on the engine, which stops the loop immediately.
"""

import time
from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QTextEdit, QLabel, QGroupBox, QVBoxLayout as VBox
)
from PySide6.QtGui import QFont, QShortcut, QKeySequence

from gui.styles import QSS
from gui.settings_tab import SettingsTab
from gui.scheduler_tab import SchedulerTab
from gui.stats_tab import StatsTab
from gui.webhook_tab import WebhookTab
from bot.config import ConfigManager
from bot.engine import BotEngine
from bot.webhook import test_webhook, build_session_embed, send_webhook


class BotLogSignals(QObject):
    """Container for all Qt Signals used by BotEngine to communicate with the GUI.

    These signals are thread-safe: they can be emitted from the engine thread
    and will be received on the main (GUI) thread via Qt's queued connection.
    """
    log_signal = Signal(str)                # Engine log message → Activity Logs panel
    status_signal = Signal(str)             # (reserved) status bar updates
    cooldown_signal = Signal(float)         # Calibrated cooldown → Settings spin box
    stopped_signal = Signal()               # Engine stopped → UI re-enable + webhook
    stats_signal = Signal(dict)             # Stats dict → Statistics tab labels
    calibration_finished = Signal()         # Calibration thread done → re-enable btn


class MainWindow(QMainWindow):
    """Root application window. Manages the full bot lifecycle."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dank Memer Automation Framework")
        self.resize(920, 720)
        self.setMinimumSize(800, 600)
        self.setStyleSheet(QSS)

        self.config = ConfigManager("default")
        self.signals = BotLogSignals()

        # Connect signals to GUI slots
        self.signals.log_signal.connect(self.append_log)
        self.signals.cooldown_signal.connect(self.update_cooldown_field)
        self.signals.stopped_signal.connect(self.on_bot_stopped)
        self.signals.stats_signal.connect(self.update_stats)
        self.signals.calibration_finished.connect(self.on_calibration_finished)

        self.bot = BotEngine(self.config, self.signals)
        self.bot_thread = None

        self.init_ui()

    # ── UI Construction ──────────────────────────────────────────────

    def init_ui(self):
        """Build the main layout: title, tab widget, log area, buttons."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(8, 6, 8, 6)

        # Title bar
        title = QLabel("Dank Memer Automation Dashboard")
        title.setFont(QFont("Arial", 15, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #f2f3f5; padding: 2px 0;")
        main_layout.addWidget(title)

        # 4-tab widget
        self.tabs = QTabWidget()
        self.settings_tab = SettingsTab(self.config)
        self.scheduler_tab = SchedulerTab(self.config)
        self.stats_tab = StatsTab()
        self.webhook_tab = WebhookTab(self.config)

        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.addTab(self.scheduler_tab, "Scheduler")
        self.tabs.addTab(self.stats_tab, "Statistics")
        self.tabs.addTab(self.webhook_tab, "Webhook")
        main_layout.addWidget(self.tabs, stretch=3)

        # Activity log panel
        log_group = QGroupBox("Activity Logs")
        log_layout = VBox(log_group)
        log_layout.setContentsMargins(4, 4, 4, 4)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(100)
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group, stretch=2)

        # Start / Stop / Calibrate buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        self.start_btn = QPushButton("START BOT")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self.start_bot)
        self.settings_tab.calibrate_btn.clicked.connect(self.start_calibration)
        self.webhook_tab.test_btn.clicked.connect(self.test_webhook)

        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_bot)

        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        main_layout.addLayout(btn_layout)

        self._setup_shortcuts()
        footer = QLabel("Killswitch: ESC (global) · q (focused) · STOP button")
        footer.setStyleSheet("color: #ed4245; font-size: 11px; font-weight: 500;")
        footer.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(footer)

        self.append_log("[+] Dashboard ready. Configure your settings and press START.")

    # ── Signal Slots ────────────────────────────────────────────────

    @Slot(str)
    def append_log(self, text):
        """Append a line of text to the Activity Logs panel and scroll to bottom."""
        self.log_text.append(text)
        self.log_text.ensureCursorVisible()

    @Slot(float)
    def update_cooldown_field(self, val):
        """Update the cooldown spin box in Settings after calibration."""
        self.settings_tab.cooldown_spin.setValue(val)

    @Slot(dict)
    def update_stats(self, stats):
        """Update all Statistics tab labels from a stats dict.

        If ``periodic_summary`` is True, sends a webhook summary instead
        of updating labels (to avoid visual flicker during mid-session reports).
        """
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

    # ── Webhook ─────────────────────────────────────────────────────

    def test_webhook(self):
        """Send a test message to the configured webhook URL."""
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

    # ── Cooldown Calibration ─────────────────────────────────────────

    def start_calibration(self):
        """Run cooldown calibration in a background thread.

        Syncs current config → saves profile → applies to engine → spawns
        a daemon thread that runs BotEngine.calibrate_cooldown(). When done,
        emits calibration_finished to re-enable the UI button.
        """
        self.settings_tab.calibrate_btn.setEnabled(False)
        self.settings_tab.sync_to_config(self.config)
        self.config.save_profile()
        self.bot.apply_config()
        self.append_log("[*] Starting cooldown calibration thread...")

        from threading import Thread
        def run_cal():
            try:
                self.bot.calibrate_cooldown()
            except Exception as e:
                self.append_log(f"[!] Calibration error: {e}")
            finally:
                self.signals.calibration_finished.emit()

        Thread(target=run_cal, daemon=True).start()

    @Slot()
    def on_calibration_finished(self):
        """Re-enable the calibration button after the background thread completes."""
        self.settings_tab.calibrate_btn.setEnabled(True)
        self.append_log("[+] Cooldown calibration thread complete.")

    # ── Engine Start / Stop ──────────────────────────────────────────

    def start_bot(self):
        """Sync all tab configs, save profile, and launch the engine thread."""
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
        """Signal the engine to stop at its next tick."""
        self.append_log("[*] Stopping bot...")
        self.bot.running = False

    @Slot()
    def on_bot_stopped(self):
        """Handle engine shutdown: re-enable UI, send session summary."""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.append_log("[*] Bot stopped.")
        self._send_session_summary()

    # ── Webhook Session Summaries ────────────────────────────────────

    def _send_session_summary(self):
        """Build and send a final session summary embed via webhook."""
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
        """Build and send an hourly periodic summary embed via webhook."""
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

    # ── Killswitch ──────────────────────────────────────────────────

    def _setup_shortcuts(self):
        """Register keyboard shortcuts for the killswitch."""
        self._esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._esc_shortcut.setContext(Qt.ApplicationShortcut)
        self._esc_shortcut.activated.connect(self._shortcut_triggered)

    def _shortcut_triggered(self):
        """Handle ESC key press: kill the engine."""
        if self.bot.running:
            self.append_log("[!] Killswitch triggered via keyboard.")
            self.bot._killswitch_triggered()

    def keyPressEvent(self, event):
        """Handle 'q' key press: kill the engine."""
        if event.key() == Qt.Key_Q and self.bot.running:
            self.append_log("[!] Killswitch triggered via keyboard.")
            self.bot._killswitch_triggered()
        super().keyPressEvent(event)

    def closeEvent(self, event):
        """On window close: stop the engine and save config."""
        self.bot.running = False
        self.config.save_profile()
        event.accept()
