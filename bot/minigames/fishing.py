import time
import random
import logging
from bot.vision import VisionEngine

logger = logging.getLogger("DankBot.Fishing")

# Rarity hierarchy (index = value order)
RARITY_ORDER = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Exotic", "Mythical"]


def rarity_index(rarity_name: str) -> int:
    try:
        return RARITY_ORDER.index(rarity_name)
    except ValueError:
        return -1


def should_sell(rarity: str, min_rarity_to_keep: str) -> bool:
    """
    Compare caught rarity vs configured threshold.
    Returns True if the fish should be sold (caught rarity < threshold).
    """
    caught_idx = rarity_index(rarity)
    keep_idx = rarity_index(min_rarity_to_keep)
    if caught_idx == -1:
        return True   # unknown rarity → sell to be safe
    return caught_idx < keep_idx


def execute_fishing_cycle(screen_bgr, config, log_func) -> dict:
    """
    Execute one full fishing cycle:
      1. Find & click Go Fishing (if present)
      2. Solve minigame (find shadow, click catch)
      3. Read result
      4. Sell or keep based on rarity
      5. Click Fish Again

    Returns stats dict: {caught, sold, kept, rarity, fish_name, error}
    """
    result = {
        'caught': False,
        'sold': False,
        'kept': False,
        'rarity': None,
        'fish_name': None,
        'error': None,
    }

    username = config.get("discord_username", "Xenron")
    min_rarity = config.get("min_rarity_to_keep", "Rare")
    sell_currency = config.get("sell_currency_pref", "Coins")

    # ── Step 1: Verify embed ownership ──
    if not VisionEngine.verify_embed_owner(screen_bgr, username):
        log_func("[!] Embed not ours or not detected. Waiting...")
        result['error'] = 'embed_owner_mismatch'
        return result

    # ── Step 2: Click "Go Fishing" (green) if present ──
    go_fishing = VisionEngine.find_buttons_by_text(screen_bgr, "Go Fishing", color_name='green')
    if go_fishing:
        log_func("[+] Clicking 'Go Fishing'...")
        VisionEngine.click_button(go_fishing)
        time.sleep(random.uniform(2.0, 3.0))
        # Re-capture after clicking
        from bot.platform import PlatformManager
        screen_bgr = PlatformManager.capture_scaled_screen()

    # ── Step 3: Solve minigame ──
    water_rect = VisionEngine.find_water_grid(screen_bgr)
    if not water_rect:
        log_func("[!] No water grid detected. May be on cooldown.")
        result['error'] = 'no_water_grid'
        return result

    log_func(f"[+] Water grid: {water_rect}")

    shadow_cell = VisionEngine.find_fish_shadow(water_rect, screen_bgr)
    if shadow_cell is None:
        log_func("[!] Could not locate fish shadow with confidence.")
        result['error'] = 'no_fish_shadow'
        return result

    # Find the 3x3 Catch buttons below the water grid
    catch_buttons = VisionEngine.find_grid_buttons_below(
        screen_bgr, water_rect, rows=3, cols=3, color_name='grey'
    )
    if not catch_buttons:
        log_func("[!] Could not locate Catch buttons below grid.")
        result['error'] = 'no_catch_buttons'
        return result

    # Click the correct Catch button
    target_btn = catch_buttons[shadow_cell]
    log_func(f"[+] Fish in cell {shadow_cell} → clicking Catch button at ({target_btn['cx']}, {target_btn['cy']})")
    VisionEngine.click_button(target_btn)

    # ── Step 4: Wait for result ──
    time.sleep(random.uniform(2.0, 3.5))

    # ── Step 5: Read catch result ──
    from bot.platform import PlatformManager
    screen_bgr = PlatformManager.capture_scaled_screen()
    fish_name, rarity = VisionEngine.read_catch_result(screen_bgr)

    result['caught'] = True
    result['fish_name'] = fish_name
    result['rarity'] = rarity
    log_func(f"[+] Caught: {fish_name or 'unknown'} [{rarity or 'unknown rarity'}]")

    # ── Step 6: Sell or keep ──
    if rarity and should_sell(rarity, min_rarity):
        sell_result = _click_sell_button(screen_bgr, log_func, sell_currency)
        if sell_result:
            result['sold'] = True
            result['kept'] = False
            log_func(f"[+] Sold {fish_name or 'the fish'} for {sell_currency}.")
        else:
            log_func("[!] Could not find sell button.")
    else:
        result['kept'] = True
        result['sold'] = False
        if rarity:
            log_func(f"[★] Keeping {rarity} fish: {fish_name or 'unknown'}")

    # ── Step 7: Click "Fish Again" ──
    time.sleep(random.uniform(0.5, 1.2))
    screen_bgr = PlatformManager.capture_scaled_screen()
    fish_again = VisionEngine.find_buttons_by_text(screen_bgr, "Fish Again", color_name='blurple')
    if fish_again:
        log_func("[+] Clicking 'Fish Again'...")
        VisionEngine.click_button(fish_again)
        time.sleep(random.uniform(1.5, 2.5))
    else:
        log_func("[!] 'Fish Again' button not found.")

    return result


def _click_sell_button(screen_bgr, log_func, currency: str) -> bool:
    """
    Find and click the appropriate Sell Creature button.
    Returns True if a sell button was clicked.
    """
    # Determine which button colour to target based on currency preference
    if currency.lower() == "coins":
        # Yellow-ish sell button (🟡 Sell Creature) → grey region button with "Sell"
        btn = VisionEngine.find_buttons_by_text(screen_bgr, "Sell", color_name='grey')
    else:
        # Green sell button (🟢 Sell Creature)
        btn = VisionEngine.find_buttons_by_text(screen_bgr, "Sell", color_name='green')

    if btn:
        VisionEngine.click_button(btn)
        log_func(f"[+] Clicked Sell Creature ({currency}).")
        time.sleep(random.uniform(0.8, 1.5))

        # Handle sell confirmation dialog if present
        from bot.platform import PlatformManager
        screen_bgr = PlatformManager.capture_scaled_screen()
        confirm = VisionEngine.find_buttons_by_text(screen_bgr, "Confirm", color_name='green')
        if confirm:
            VisionEngine.click_button(confirm)
            log_func("[+] Sell confirmed.")
            time.sleep(random.uniform(0.5, 1.0))

        return True

    return False
