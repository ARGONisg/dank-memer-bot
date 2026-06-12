"""
State machine driving all bot automation.

State flow (happy path)
=======================
  INIT ──(send command)─→ WAIT_EMBED ──→ GO_FISHING ──→ MINIGAME ──→ RESULT ──→ INIT
                                │
                                ├──→ MINIGAME (if water grid already visible)
                                └──→ COOLDOWN (3 consecutive failures)

  INIT ──(round-robin)──→ BLACKJACK ──→ inline cooldown ──→ INIT
                         SLOTS     ──→ inline cooldown ──→ INIT

  Any state → BREAK (when break interval elapsed)
  Any exception → INIT with 5s sleep

Failure handling
================
  _consecutive_failures tracks sequential failures per "attempt group":
    - focus_discord() in INIT
    - embed ownership check in WAIT_EMBED
    - fish shadow detection in MINIGAME
    - catch buttons detection in MINIGAME

  After 3 consecutive failures, engine enters COOLDOWN → INIT (NOT retry loop).
  Counter resets to 0 on first success within the group.

Activity scheduling
===================
  Round-robin via _activity_index. Only config-enabled activities participate.
  Each activity has its own cooldown: fish uses _state_cooldown(), BJ & slots
  use inline 0.1s-tick wait loops with their own _cooldown config values.

Human-like behaviour
====================
  Commands via human_type() (bezier mouse, typos, randomised delays).
  Breaks every _break_interval seconds, _break_min .. _break_max long.
  All cooldowns jittered by _jitter_pct percent + random uniform.
"""

import time
import random
import logging
import re

import pyautogui

from bot.platform import PlatformManager
from bot.vision import VisionEngine
from bot.killswitch import Killswitch
from bot.antidetection import human_type
from bot.minigames import fishing as fishing_mg
from bot.minigames import blackjack as bj_mg
from bot.minigames.blackjack import reset_shoe
from bot.minigames import slots as slots_mg

logger = logging.getLogger("DankBot.Engine")

# ── State Machine Constants ─────────────────────────────────────────────
# Each is a string dispatched in run_loop() via if/elif. See module docstring
# for the full state transition diagram.
STATE_INIT = "init"
STATE_WAIT_EMBED = "wait_embed"
STATE_GO_FISHING = "go_fishing"
STATE_MINIGAME = "minigame"
STATE_RESULT = "result"
STATE_BLACKJACK = "blackjack"
STATE_SLOTS = "slots"
STATE_COOLDOWN = "cooldown"
STATE_BREAK = "break"


class BotEngine:
    """Main state machine that drives all bot automation.

    The engine runs a tight loop dispatching state handlers in sequence.
    Each iteration: focus Discord → pick activity → send command →
    wait for embed → minigame → result → cooldown → repeat.

    Config is applied via apply_config() (called externally by MainWindow
    after construction). All timing values are jittered for anti-detection.

    Signals (Qt signals from the signals object):
      log_signal(str)       — UI log panel output
      stats_signal(dict)    — periodic or event-driven stats update
      cooldown_signal(float) — calibrated cooldown duration (from OCR)
      stopped_signal()      — engine finished (not interrupted)
    """

    def __init__(self, config, signals):
        """Store config/signals references, set all defaults.

        Args:
            config: A config-like object with a ``.settings`` dict.
            signals: A namespace/object with Qt signals attached
                     (log_signal, stats_signal, cooldown_signal, stopped_signal).
        """
        self.config = config
        self.signals = signals
        self.running = False          # Set True by run_loop(), False to stop
        self.state = STATE_INIT       # Current state-machine state

        # ── Runtime state ────────────────────────────────────────────
        self.last_break_time = time.time()
        self.stats = {
            "casts": 0, "catches": 0, "sells": 0,
            "errors": 0, "rare_kept": 0, "earnings": 0,
            "session_start": time.time()
        }

        # ── Config-cached values ─────────────────────────────────────
        # These are overwritten by apply_config().
        # Stored as instance attributes for fast access in the hot loop.
        self._cmd_prefix = "pls "
        self._fish_cmd = "fish catch"
        self._bj_cmd = "bj 5k"
        self._slots_cmd = "slots 100"
        self._min_delay = 0.5         # Min typing delay (seconds)
        self._max_delay = 0.9         # Max typing delay (seconds)
        self._cooldown = 35.0         # Fish cooldown (seconds), may be calibrated
        self._break_profile = "medium"
        self._break_interval = 3600   # Break interval (seconds)
        self._break_min = 300         # Min break duration (seconds)
        self._break_max = 600         # Max break duration (seconds)
        self._jitter_pct = 15         # Random jitter as % of cooldown
        self._username = "Xenron"     # Discord username for embed ownership check
        self._sell_currency = "Coins"
        self._min_rarity = "Rare"     # Minimum rarity to keep (not auto-sell)
        self._fish_bait = "None"
        self._fish_equip = "None"
        self._fish_enabled = True
        self._bj_enabled = False
        self._bj_cooldown = 45.0      # Blackjack cooldown (seconds)
        self._slots_enabled = False
        self._slots_cooldown = 20.0   # Slots cooldown (seconds)

        # ── Internal counters ────────────────────────────────────────
        self._iteration_count = 0
        self._activity_index = 0      # Round-robin index into enabled activities
        self._last_summary_time = time.time()
        self._summary_interval = 3600 # Stats summary interval (seconds)

        # ── Failure resilience ───────────────────────────────────────
        # _consecutive_failures is reset per "failure group" (focus, embed, etc.)
        # After _max_consecutive_failures (3), engine enters COOLDOWN instead of
        # retrying indefinitely. This prevents infinite loops when Discord is
        # closed, the embed doesn't appear, or the minigame is in an unexpected state.
        self._consecutive_failures = 0
        self._max_consecutive_failures = 3
        self._skip_embed_check = False  # If True, skip verify_embed_owner (for testing)

        # ── Killswitch (ESC / 'q') ───────────────────────────────────
        self._killswitch = Killswitch(on_trigger=self._killswitch_triggered)

    # ── Logging ────────────────────────────────────────────────────────

    def log(self, message):
        """Write a message to both the file logger and the UI log panel."""
        timestamp = time.strftime("%H:%M:%S")
        logger.info("%s", message)
        self.signals.log_signal.emit(f"[{timestamp}] {message}")

    # ── Config Sync ────────────────────────────────────────────────────

    def apply_config(self):
        """Copy all relevant values from config.settings into instance attrs.

        Called externally (by MainWindow) after construction or when settings
        are saved, so the hot loop reads plain instance attributes instead of
        hitting the config dict every iteration.
        """
        s = self.config.settings
        self._cmd_prefix = s.get("command_prefix", "pls ")
        self._fish_cmd = s.get("fish_command", "fish catch")
        self._bj_cmd = s.get("bj_command", "bj 5k")
        self._slots_cmd = s.get("slots_command", "slots 100")
        self._min_delay = s.get("min_typing_delay", 0.5)
        self._max_delay = s.get("max_typing_delay", 0.9)
        self._cooldown = s.get("fish_cooldown", 35.0)
        self._break_profile = s.get("break_profile", "medium")
        self._break_interval = s.get("break_interval_mins", 60) * 60
        self._break_min = s.get("break_duration_min_sec", 300)
        self._break_max = s.get("break_duration_max_sec", 600)
        self._jitter_pct = s.get("random_jitter_percent", 15)
        self._username = s.get("discord_username", "Xenron")
        self._sell_currency = s.get("sell_currency_pref", "Coins")
        self._min_rarity = s.get("min_rarity_to_keep", "Rare")
        self._fish_bait = s.get("fish_bait", "None")
        self._fish_equip = s.get("fish_equipment", "None")
        self._fish_enabled = s.get("fish_enabled", True)
        self._bj_enabled = s.get("bj_enabled", False)
        self._bj_cooldown = s.get("bj_cooldown", 45.0)
        self._slots_enabled = s.get("slots_enabled", False)
        self._slots_cmd = s.get("slots_command", "slots 100")
        self._slots_cooldown = s.get("slots_cooldown", 20.0)
        self._skip_embed_check = s.get("skip_embed_check", False)

    # ── Command Helpers ────────────────────────────────────────────────

    def send_command(self, cmd_text):
        """Type ``cmd_text`` into Discord via human_type() and press Enter.

        Uses simulated human typing (bezier-curve delays, randomised typos)
        for anti-detection. Times out immediately if engine is stopped.
        """
        if not self.running:
            return
        human_type(cmd_text, profile='normal', typo_chance=0.02)
        time.sleep(random.uniform(self._min_delay, self._max_delay))
        pyautogui.press('enter')

    def capture_screen(self):
        """Capture the current screen as a BGR numpy array.

        Delegates to PlatformManager which handles Retina vs non-Retina
        display scaling automatically.
        """
        return PlatformManager.capture_scaled_screen()

    def _killswitch_triggered(self):
        """Callback invoked by Killswitch when ESC or 'q' is pressed."""
        self.log("[!] Killswitch activated — stopping bot.")
        self.running = False

    # ── Cooldown Calibration ───────────────────────────────────────────

    def calibrate_cooldown(self):
        """Auto-detect the fish cooldown by sending two rapid commands.

        Sends ``pls fish catch`` twice in quick succession and OCRs the
        chat area for a cooldown message like "Wait 35.0s". Updates
        ``_cooldown`` and emits ``cooldown_signal`` with the detected value.
        Falls back to 35.0s if OCR fails.

        Designed to be called from a background thread (see MainWindow's
        ``calibrate_cooldown``) so the GUI stays responsive.
        """
        self.log("[*] Calibrating cooldown automatically...")
        if not PlatformManager.focus_discord():
            self.log("[!] Focus failed. Ensure Discord is open.")
            return
        time.sleep(1)
        self.running = True
        full_cmd = f"{self._cmd_prefix}{self._fish_cmd}"
        self.send_command(full_cmd)
        time.sleep(random.uniform(1.2, 1.8))
        self.send_command(full_cmd)
        time.sleep(random.uniform(1.5, 2.0))
        self.running = False

        screen = self.capture_screen()
        h, w, _ = screen.shape
        crop_y = int(h * 0.5)
        chat_area = screen[crop_y:, :]
        text = VisionEngine.ocr_region(screen, (0, crop_y, w, h - crop_y))
        duration = self._parse_cooldown_text(text)
        if duration:
            self._cooldown = duration
            self.log(f"[+] Cooldown detected: {duration}s")
            self.signals.cooldown_signal.emit(duration)
        else:
            self.log("[!] Could not parse cooldown. Keeping default.")
            self.signals.cooldown_signal.emit(35.0)

    @staticmethod
    def _parse_cooldown_text(text):
        """Extract a duration in seconds from cooldown message text.

        Tries regex patterns in order:
          1. "wait/cooldown/again in X.X s/sec/second"
          2. Bare "X.X second/sec/s"

        Returns float or None.
        """
        text = text.lower()
        for pattern in [r'(?:wait|cooldown|again in)\s*([\d\.]+)\s*(?:s|sec|second)',
                        r'([\d\.]+)\s*(?:second|sec|s)\b']:
            m = re.search(pattern, text)
            if m:
                return float(m.group(1))
        return None

    # ═══════════════════════════════════════════════════════════════════
    #  STATE MACHINE — Main Loop
    # ═══════════════════════════════════════════════════════════════════
    #
    # The engine's run_loop() runs in a dedicated thread (started by MainWindow).
    # Each iteration:
    #   1. Check if break is due (idle for _break_interval)
    #   2. Check if periodic summary is due
    #   3. Dispatch the current state handler
    #
    # State handlers set self.state to the next state. If an exception
    # escapes any handler, we log it, increment error count, sleep 5s,
    # and reset to INIT.

    def run_loop(self):
        """Main engine loop. Runs until self.running is set False.

        Designed to be started in a background thread (QThread) so the
        GUI stays responsive. States are dispatched via if/elif chain.
        The killswitch (ESC / 'q') is started here and stopped on exit.
        """
        self.running = True
        self.stats["session_start"] = time.time()
        self.state = STATE_INIT
        self._iteration_count = 0
        self._consecutive_failures = 0
        self._killswitch.start()
        reset_shoe()  # Fresh shoe for blackjack on each engine start
        self.log("[*] Bot engine started. Killswitch: ESC or 'q'.")

        while self.running:
            try:
                self._check_break()
                if not self.running:
                    break
                self._check_summary()

                # ── State dispatch ─────────────────────────────────
                if self.state == STATE_INIT:
                    self._state_init()
                elif self.state == STATE_WAIT_EMBED:
                    self._state_wait_embed()
                elif self.state == STATE_GO_FISHING:
                    self._state_go_fishing()
                elif self.state == STATE_MINIGAME:
                    self._state_minigame()
                elif self.state == STATE_RESULT:
                    self._state_result()
                elif self.state == STATE_BLACKJACK:
                    self._state_blackjack()
                elif self.state == STATE_SLOTS:
                    self._state_slots()
                elif self.state == STATE_COOLDOWN:
                    self._state_cooldown()
                elif self.state == STATE_BREAK:
                    self._state_break()
                else:
                    self.state = STATE_INIT

            except Exception as e:
                self.log(f"[!] Error in state {self.state}: {e}")
                logger.exception("Engine loop error")
                self.stats["errors"] += 1
                self.emit_stats()
                time.sleep(5)
                self.state = STATE_INIT

        self._killswitch.stop()
        self.log("[*] Bot engine stopped.")
        self.signals.stopped_signal.emit()

    def _check_break(self):
        """If enough time has passed since the last break, enter BREAK state."""
        interval = self._break_interval
        if time.time() - self.last_break_time > interval:
            self.state = STATE_BREAK

    def _check_summary(self):
        """Emit periodic stats summary if _summary_interval has elapsed."""
        if time.time() - self._last_summary_time > self._summary_interval:
            self._last_summary_time = time.time()
            self.emit_stats(periodic=True)

    def emit_stats(self, periodic=False):
        """Send current stats dict to the GUI via stats_signal.

        Args:
            periodic: True if this is a timer-triggered summary (for UI decoration).
        """
        self.stats["session_time"] = int(time.time() - self.stats["session_start"])
        self.stats["periodic_summary"] = periodic
        self.signals.stats_signal.emit(dict(self.stats))

    def _state_init(self):
        """START state for each activity cycle.

        Flow:
          1. Focus Discord (retry up to 3 times with 10s pauses).
          2. If no activity enabled, sleep 30s and enter COOLDOWN.
          3. Select next activity via round-robin index.
          4. Send the command via Discord chat.
          5. Transition to the appropriate activity state (WAIT_EMBED,
             BLACKJACK, or SLOTS).

        Failure behaviour: after 3 consecutive focus failures, enter
        COOLDOWN directly to avoid infinite retry loops (e.g. if Discord
        process is dead).
        """
        self.log(f"[*] --- Cycle {self._iteration_count} ---")
        if not PlatformManager.focus_discord():
            self.log("[!] Could not focus Discord. Retrying in 10s...")
            time.sleep(10)
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._max_consecutive_failures:
                self.log("[!] Too many consecutive failures. Entering cooldown.")
                self._consecutive_failures = 0
                self.state = STATE_COOLDOWN
                return
            self.state = STATE_INIT
            return
        self._consecutive_failures = 0
        time.sleep(random.uniform(0.3, 0.5))

        # Build list of enabled activities (config-sourced)
        activities = []
        if self._fish_enabled:
            activities.append(('fish', self._fish_cmd))
        if self._bj_enabled:
            activities.append(('bj', self._bj_cmd))
        if self._slots_enabled:
            activities.append(('slots', self._slots_cmd))

        if not activities:
            self.log("[!] No activities enabled. Sleeping 30s...")
            time.sleep(30)
            self.state = STATE_COOLDOWN
            return

        # Round-robin selection — fair scheduling across enabled activities
        act = self._activity_index % len(activities)
        self._activity_index += 1
        act_name, act_cmd = activities[act]

        full_cmd = f"{self._cmd_prefix}{act_cmd}"
        self.send_command(full_cmd)
        self.stats["casts"] += 1
        self.emit_stats()
        self._iteration_count += 1

        if act_name == 'fish':
            self.state = STATE_WAIT_EMBED
        elif act_name == 'bj':
            self.state = STATE_BLACKJACK
        elif act_name == 'slots':
            self.state = STATE_SLOTS

    def _state_wait_embed(self):
        """Wait for the Discord embed to appear and verify ownership.

        After sending ``pls fish catch``, Discord responds with an embed.
        This state:
          1. Waits 2.5–3.5s for the embed to render.
          2. Verifies the embed header contains the bot's username (unless
             ``self._skip_embed_check`` is True).
          3. If the water grid is already visible (re-entry via "Fish Again"),
             skips straight to MINIGAME.
          4. Otherwise transitions to GO_FISHING to click the button.

        Failure: after 3 consecutive embed-not-ours, enter COOLDOWN.
        """
        time.sleep(random.uniform(2.5, 3.5))
        if not self.running:
            return

        screen = self.capture_screen()

        if not self._skip_embed_check:
            owned = VisionEngine.verify_embed_owner(screen, self._username)

            if not owned:
                self._consecutive_failures += 1
                self.log(f"[!] Embed not ours or not visible. (fail {self._consecutive_failures}/{self._max_consecutive_failures})")
                if self._consecutive_failures >= self._max_consecutive_failures:
                    self._consecutive_failures = 0
                    self.log("[!] Too many embed detection failures. Entering cooldown.")
                    self.state = STATE_COOLDOWN
                    return
                time.sleep(random.uniform(2.0, 4.0))
                self.state = STATE_INIT
                return
            self._consecutive_failures = 0

        # Check if water grid is already visible → "Fish Again" was clicked
        water = VisionEngine.find_water_grid(screen)
        if water:
            self.log("[+] Water grid already visible → minigame ready.")
            self.state = STATE_MINIGAME
        else:
            self.log("[+] Embed found. Looking for 'Go Fishing'...")
            self.state = STATE_GO_FISHING

    def _state_go_fishing(self):
        """Locate and click the green 'Go Fishing' button.

        The embed's "Go Fishing" button is a green Discord button located
        at the bottom of the embed. Found by colour (green) + text OCR.

        If not found, checks whether the water grid is already visible
        (e.g. we're already in the minigame). Falls back to re-initialising
        the cycle on failure.
        """
        screen = self.capture_screen()
        btn = VisionEngine.find_buttons_by_text(screen, "Go Fishing", color_name='green')
        if not btn:
            # Maybe it's already in minigame
            water = VisionEngine.find_water_grid(screen)
            if water:
                self.state = STATE_MINIGAME
                return
            self.log("[!] 'Go Fishing' not found. Re-sending command...")
            self.state = STATE_INIT
            return

        VisionEngine.click_button(btn)
        self.log("[+] Clicked 'Go Fishing'.")
        time.sleep(random.uniform(2.0, 3.0))
        self.state = STATE_MINIGAME

    def _state_minigame(self):
        """Solve the fishing minigame: detect fish shadow, click catch button.

        The minigame consists of:
          - A 3x3 grid of blue water cells (found via HSV thresholding).
          - A darker "shadow" in one cell indicating the fish's position.
          - A 3x3 grid of grey "Catch" buttons below the water grid.

        This state:
          1. Locates the water grid.
          2. Determines which cell (0-8) contains the fish shadow.
          3. Locates the 3x3 catch button grid below.
          4. Clicks the catch button at the matching position.

        Failure handling: if shadow or buttons can't be found, retries up
        to 3 times (incrementing _consecutive_failures), then enters COOLDOWN
        to avoid spamming commands when the minigame is in an unexpected state.
        """
        screen = self.capture_screen()

        water_rect = VisionEngine.find_water_grid(screen)
        if not water_rect:
            self.log("[!] Water grid not found (maybe on cooldown).")
            self.state = STATE_COOLDOWN
            return

        shadow_cell = VisionEngine.find_fish_shadow(water_rect, screen)
        if shadow_cell is None:
            self._consecutive_failures += 1
            self.log(f"[!] Fish shadow not found. (fail {self._consecutive_failures}/{self._max_consecutive_failures})")
            if self._consecutive_failures >= self._max_consecutive_failures:
                self._consecutive_failures = 0
                self.state = STATE_COOLDOWN
                return
            self.state = STATE_INIT
            return

        # Find the 3x3 grey Catch buttons below the water grid
        catch_btns = VisionEngine.find_grid_buttons_below(
            screen, water_rect, rows=3, cols=3, color_name='grey'
        )
        if not catch_btns:
            self._consecutive_failures += 1
            self.log(f"[!] Catch buttons not found. (fail {self._consecutive_failures}/{self._max_consecutive_failures})")
            if self._consecutive_failures >= self._max_consecutive_failures:
                self._consecutive_failures = 0
                self.state = STATE_COOLDOWN
                return
            self.state = STATE_INIT
            return
        self._consecutive_failures = 0

        target = catch_btns[shadow_cell]
        self.log(f"[+] Shadow cell {shadow_cell} → clicking Catch @ ({target['cx']}, {target['cy']})")
        VisionEngine.click_button(target)
        time.sleep(random.uniform(2.0, 3.5))
        self.state = STATE_RESULT

    def _state_result(self):
        """Read the fishing result, sell/keep decision, and chain to next round.

        Flow:
          1. Capture screen and OCR the result text.
          2. Extract fish name and rarity.
          3. If rarity is below ``_min_rarity``, auto-sell via the sell dialog
             button. Otherwise keep (counted as ``rare_kept``).
          4. Look for the "Fish Again" button to chain directly into the next
             minigame round. If not found, return to INIT for a fresh cycle.
        """
        screen = self.capture_screen()

        fish_name, rarity = VisionEngine.read_catch_result(screen)
        self.stats["catches"] += 1

        if rarity:
            min_rarity = self._min_rarity
            if fishing_mg.should_sell(rarity, min_rarity):
                self.log(f"[+] Selling {fish_name or 'fish'} [{rarity}]")
                sold = fishing_mg._click_sell_button(screen, self.log, self._sell_currency)
                if sold:
                    self.stats["sells"] += 1
                    # Estimate earnings (no exact value from OCR, use random range)
                    earn = random.randint(50, 200)
                    self.stats["earnings"] += earn
            else:
                self.log(f"[★] Keeping {rarity}: {fish_name or 'unknown'}")
                self.stats["rare_kept"] += 1
        else:
            self.log(f"[+] Caught: {fish_name or 'unknown'} [rarity unknown]")

        self.emit_stats()

        # Click "Fish Again" to go directly to next minigame (skip command re-typing)
        time.sleep(random.uniform(0.5, 1.2))
        screen = self.capture_screen()
        fish_again = VisionEngine.find_buttons_by_text(screen, "Fish Again", color_name='blurple')
        if fish_again:
            VisionEngine.click_button(fish_again)
            self.log("[+] Clicked 'Fish Again'.")
            time.sleep(random.uniform(1.5, 2.5))
            self.state = STATE_MINIGAME
        else:
            self.log("[!] 'Fish Again' not found. Re-initializing...")
            self.state = STATE_INIT

    def _state_blackjack(self):
        """Play a blackjack hand via the blackjack minigame module.

        Flow:
          1. Capture screen after a short delay (2-3s for embed to render).
          2. Verify embed ownership (optional, controlled by _skip_embed_check).
          3. Delegate to ``bj_mg.execute_blackjack_hand()`` which handles all
             OCR, decision logic, and clicking.
          4. Wait for ``_bj_cooldown + 1-3s jitter`` with 0.1s ticks,
             checking for stop/break signals each cycle.

        Note: blackjack uses an inline cooldown tick-loop rather than the
        shared STATE_COOLDOWN so it can use its own cooldown config value.
        """
        self.log("[*] Blackjack hand...")
        time.sleep(random.uniform(2.0, 3.0))
        if not self.running:
            return

        screen = self.capture_screen()
        if not self._skip_embed_check and not VisionEngine.verify_embed_owner(screen, self._username):
            self.log("[!] Blackjack embed not ours. Retrying...")
            self.state = STATE_INIT
            return

        result = bj_mg.execute_blackjack_hand(screen, self.config, self.log)
        if result.get('completed'):
            self.log("[+] Blackjack hand complete.")
        else:
            self.log("[!] Blackjack hand had an issue.")

        bj_wait = self._bj_cooldown + random.uniform(1.0, 3.0)
        self.log(f"Blackjack cooldown: {bj_wait:.1f}s...")
        for _ in range(int(bj_wait * 10)):
            if not self.running:
                return
            time.sleep(0.1)
            self._check_break()
            if self.state == STATE_BREAK:
                return
        self.state = STATE_INIT

    def _state_slots(self):
        """Execute a slots spin via the slots minigame module.

        Flow:
          1. Capture screen after a short delay (2-3s for embed to render).
          2. Verify embed ownership.
          3. Delegate to ``slots_mg.execute_slots_spin()`` for OCR + clicking.
          4. Wait for ``_slots_cooldown + 1-3s jitter`` with 0.1s ticks.

        Same cooldown pattern as blackjack: inline ticks so each activity
        uses its own cooldown config.
        """
        self.log("[*] Slots spin...")
        time.sleep(random.uniform(2.0, 3.0))
        if not self.running:
            return

        screen = self.capture_screen()
        if not self._skip_embed_check and not VisionEngine.verify_embed_owner(screen, self._username):
            self.log("[!] Slots embed not ours. Retrying...")
            self.state = STATE_INIT
            return

        result = slots_mg.execute_slots_spin(screen, self.log)
        if result.get('completed'):
            self.log("[+] Slots spin complete.")
        else:
            self.log("[!] Slots spin had an issue.")

        slots_wait = self._slots_cooldown + random.uniform(1.0, 3.0)
        self.log(f"Slots cooldown: {slots_wait:.1f}s...")
        for _ in range(int(slots_wait * 10)):
            if not self.running:
                return
            time.sleep(0.1)
            self._check_break()
            if self.state == STATE_BREAK:
                return
        self.state = STATE_INIT

    def _state_cooldown(self):
        """Wait out the shared (fish) cooldown period with jitter.

        The cooldown value comes from ``_cooldown`` (may be auto-calibrated
        via ``calibrate_cooldown()``). Jitter is applied as a percentage
        (``_jitter_pct``) of the base cooldown. Minimum wait is 5s.

        This is used for fishing only. Blackjack and slots have their own
        inline cooldown waits.
        """
        jitter = self._cooldown * (self._jitter_pct / 100.0)
        wait = self._cooldown + random.uniform(-jitter, jitter)
        wait = max(wait, 5.0)
        self.log(f"Cooldown: waiting {wait:.1f}s...")
        for _ in range(int(wait * 10)):
            if not self.running:
                return
            time.sleep(0.1)
            self._check_break()
            if self.state == STATE_BREAK:
                return
        self.state = STATE_INIT

    def _state_break(self):
        """Take a human-like break to avoid anti-bot detection.

        Duration is randomised between ``_break_min`` and ``_break_max``
        seconds. The engine does nothing during this time (sleeps 1s ticks).
        After the break, ``_last_break_time`` is reset so the next break
        is scheduled ``_break_interval`` seconds from now.
        """
        duration = random.randint(self._break_min, self._break_max)
        self.log(f"[!] Human break for {duration // 60}m {duration % 60}s...")
        for _ in range(duration):
            if not self.running:
                return
            time.sleep(1)
        self.last_break_time = time.time()
        self.log("[+] Break over. Resuming.")
        self.state = STATE_INIT
