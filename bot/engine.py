import time
import random
import logging
import re

import pyautogui

from bot.platform import PlatformManager
from bot.vision import VisionEngine
from bot.killswitch import Killswitch
from bot.antidetection import human_type, jitter_sleep, get_break_duration, get_break_interval
from bot.minigames import fishing as fishing_mg
from bot.minigames import blackjack as bj_mg
from bot.minigames import slots as slots_mg

logger = logging.getLogger("DankBot.Engine")

# State constants
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
    def __init__(self, config, signals):
        self.config = config
        self.signals = signals
        self.running = False
        self.state = STATE_INIT

        # Runtime state
        self.last_break_time = time.time()
        self.stats = {
            "casts": 0, "catches": 0, "sells": 0,
            "errors": 0, "rare_kept": 0, "earnings": 0,
            "session_start": time.time()
        }

        # Config-cached values
        self._cmd_prefix = "pls "
        self._fish_cmd = "fish catch"
        self._bj_cmd = "bj 5k"
        self._slots_cmd = "slots 100"
        self._min_delay = 0.5
        self._max_delay = 0.9
        self._cooldown = 35.0
        self._break_profile = "medium"
        self._break_interval = 3600
        self._break_min = 300
        self._break_max = 600
        self._jitter_pct = 15
        self._username = "Xenron"
        self._sell_currency = "Coins"
        self._min_rarity = "Rare"
        self._fish_bait = "None"
        self._fish_equip = "None"
        self._fish_enabled = True
        self._bj_enabled = False
        self._bj_cooldown = 45.0
        self._slots_enabled = False
        self._slots_cmd = "slots 100"

        self._iteration_count = 0
        self._activity_index = 0  # round-robin for multi-activity
        self._killswitch = Killswitch(on_trigger=self._killswitch_triggered)

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.signals.log_signal.emit(f"[{timestamp}] {message}")

    def apply_config(self):
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

    def send_command(self, cmd_text):
        if not self.running:
            return
        human_type(cmd_text, profile='normal', typo_chance=0.02)
        time.sleep(random.uniform(self._min_delay, self._max_delay))
        pyautogui.press('enter')

    def capture_screen(self):
        return PlatformManager.capture_scaled_screen()

    def emit_stats(self):
        self.signals.stats_signal.emit(dict(self.stats))

    def _killswitch_triggered(self):
        self.log("[!] Killswitch activated — stopping bot.")
        self.running = False

    def calibrate_cooldown(self):
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
        text = text.lower()
        for pattern in [r'(?:wait|cooldown|again in)\s*([\d\.]+)\s*(?:s|sec|second)',
                        r'([\d\.]+)\s*(?:second|sec|s)\b']:
            m = re.search(pattern, text)
            if m:
                return float(m.group(1))
        return None

    # ── State Machine ────────────────────────────────────────────────

    def run_loop(self):
        self.running = True
        self.stats["session_start"] = time.time()
        self.state = STATE_INIT
        self._iteration_count = 0
        self._killswitch.start()
        self.log("[*] Bot engine started. Killswitch: ESC or 'q'.")

        while self.running:
            try:
                self._check_break()
                if not self.running:
                    break

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
        interval = get_break_interval(self._break_profile)
        if time.time() - self.last_break_time > interval:
            self.state = STATE_BREAK

    def _state_init(self):
        """Pick the next enabled activity and send its command."""
        self.log(f"[*] --- Cycle {self._iteration_count} ---")
        PlatformManager.focus_discord()
        time.sleep(random.uniform(0.3, 0.5))

        # Build list of enabled activities
        activities = []
        if self._fish_enabled:
            activities.append(('fish', self._fish_cmd))
        if self._bj_enabled:
            activities.append(('bj', self._bj_cmd))
        if self._slots_enabled:
            activities.append(('slots', self._slots_cmd))

        if not activities:
            self.log("[!] No activities enabled. Sleeping...")
            time.sleep(30)
            return

        # Round-robin selection
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
        """Wait for the embed to appear, then check ownership."""
        time.sleep(random.uniform(2.5, 3.5))
        if not self.running:
            return

        screen = self.capture_screen()
        owned = VisionEngine.verify_embed_owner(screen, self._username)

        if not owned:
            self.log("[!] Embed not ours or not visible. Retrying...")
            time.sleep(random.uniform(2.0, 4.0))
            self.state = STATE_INIT
            return

        # Check if the water grid is already visible (Fish Again → minigame)
        water = VisionEngine.find_water_grid(screen)
        if water:
            self.log("[+] Water grid already visible → minigame ready.")
            self.state = STATE_MINIGAME
        else:
            self.log("[+] Embed found. Looking for 'Go Fishing'...")
            self.state = STATE_GO_FISHING

    def _state_go_fishing(self):
        """Find and click the green 'Go Fishing' button."""
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
        """Solve the fishing minigame: detect shadow, click catch button."""
        screen = self.capture_screen()

        water_rect = VisionEngine.find_water_grid(screen)
        if not water_rect:
            self.log("[!] Water grid not found (maybe on cooldown).")
            self.state = STATE_COOLDOWN
            return

        shadow_cell = VisionEngine.find_fish_shadow(water_rect, screen)
        if shadow_cell is None:
            self.log("[!] Fish shadow not found with confidence. Retrying...")
            self.state = STATE_INIT
            return

        # Find the 3x3 grey Catch buttons below the water grid
        catch_btns = VisionEngine.find_grid_buttons_below(
            screen, water_rect, rows=3, cols=3, color_name='grey'
        )
        if not catch_btns:
            self.log("[!] Catch buttons not found.")
            self.state = STATE_INIT
            return

        target = catch_btns[shadow_cell]
        self.log(f"[+] Shadow cell {shadow_cell} → clicking Catch @ ({target['cx']}, {target['cy']})")
        VisionEngine.click_button(target)
        time.sleep(random.uniform(2.0, 3.5))
        self.state = STATE_RESULT

    def _state_result(self):
        """Read the catch result, decide sell/keep, click Fish Again."""
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
                    # Estimate earnings
                    earn = random.randint(50, 200)
                    self.stats["earnings"] += earn
            else:
                self.log(f"[★] Keeping {rarity}: {fish_name or 'unknown'}")
                self.stats["rare_kept"] += 1
        else:
            self.log(f"[+] Caught: {fish_name or 'unknown'} [rarity unknown]")

        self.emit_stats()

        # Click "Fish Again" to go directly to next minigame
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
        """Play a blackjack hand using basic strategy."""
        self.log("[*] Blackjack hand...")
        time.sleep(random.uniform(2.0, 3.0))
        if not self.running:
            return

        screen = self.capture_screen()
        if not VisionEngine.verify_embed_owner(screen, self._username):
            self.log("[!] Blackjack embed not ours. Retrying...")
            self.state = STATE_INIT
            return

        result = bj_mg.execute_blackjack_hand(screen, self.config, self.log)
        if result.get('completed'):
            self.log("[+] Blackjack hand complete.")
        else:
            self.log("[!] Blackjack hand had an issue.")

        # Wait cooldown then cycle to next activity
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
        """Execute a slots spin and wait for cooldown."""
        self.log("[*] Slots spin...")
        time.sleep(random.uniform(2.0, 3.0))
        if not self.running:
            return

        screen = self.capture_screen()
        if not VisionEngine.verify_embed_owner(screen, self._username):
            self.log("[!] Slots embed not ours. Retrying...")
            self.state = STATE_INIT
            return

        result = slots_mg.execute_slots_spin(screen, self.log)
        if result.get('completed'):
            self.log("[+] Slots spin complete.")
        else:
            self.log("[!] Slots spin had an issue.")

        # Slots cooldown (typically shorter than fishing)
        slots_wait = random.uniform(15.0, 25.0)
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
        """Wait out the configured cooldown period with jitter."""
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
        """Take a human-like break using break profile."""
        profile = self._break_profile
        duration = get_break_duration(profile)
        self.log(f"[!] Human break [{profile}] for {duration // 60}m {duration % 60}s...")
        for _ in range(duration):
            if not self.running:
                return
            time.sleep(1)
        self.last_break_time = time.time()
        self.log("[+] Break over. Resuming.")
        self.state = STATE_INIT
