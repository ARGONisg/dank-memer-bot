import time
import random
import logging
from bot.platform import PlatformManager
from bot.vision import VisionEngine

logger = logging.getLogger("DankBot.Slots")


def execute_slots_spin(screen_bgr, log_func) -> dict:
    """
    Execute one slots spin:
      1. Wait for spin animation to finish
      2. Read result via OCR
      3. Click "Play Again" or "Spin Again"

    Returns dict: {completed, payout, win, error}
    """
    result = {
        'completed': False,
        'payout': 0,
        'win': False,
        'error': None,
    }

    # Wait for the spin animation to settle
    log_func("[*] Slots: waiting for spin result...")
    time.sleep(random.uniform(3.0, 4.5))

    screen_bgr = PlatformManager.capture_scaled_screen()
    text = VisionEngine.ocr_region(screen_bgr, (0, 0, screen_bgr.shape[1], screen_bgr.shape[0]))

    # Try to detect if we won or lost
    text_lower = text.lower()
    if 'won' in text_lower or 'payout' in text_lower or 'win' in text_lower:
        result['win'] = True
        log_func("[+] Slots: detected a win!")
        # Attempt to extract payout amount
        payout = _extract_payout(text)
        if payout:
            result['payout'] = payout
            log_func(f"[+] Payout: {payout}")
    elif 'lost' in text_lower or 'lost' in text_lower:
        result['win'] = False
        log_func("[-] Slots: lost this spin.")
    else:
        log_func("[*] Slots: result unclear (OCR).")

    # Click "Play Again" blurple button
    time.sleep(random.uniform(1.0, 2.0))
    screen_bgr = PlatformManager.capture_scaled_screen()
    play_again = VisionEngine.find_buttons_by_text(screen_bgr, "Play Again", color_name='blurple')
    if not play_again:
        play_again = VisionEngine.find_buttons_by_text(screen_bgr, "Spin Again", color_name='blurple')

    if play_again:
        log_func("[+] Slots: clicking 'Play Again'...")
        VisionEngine.click_button(play_again)
        result['completed'] = True
    else:
        log_func("[!] Slots: 'Play Again' button not found.")
        result['error'] = 'no_play_again'

    return result


def _extract_payout(text: str):
    """Parse a payout amount from OCR text."""
    import re
    patterns = [
        r'(?:won|win|payout|earned)\s*:?\s*\$?([\d,]+)',
        r'([\d,]+)\s*(?:coins|currency)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1).replace(',', ''))
            except ValueError:
                pass
    return None
