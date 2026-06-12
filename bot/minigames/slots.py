"""
Slots Minigame — Automated slot-machine spin execution.

Provides a single entry point ``execute_slots_spin()`` that:
  1. Waits for the slot animation to complete.
  2. OCRs the full screen to determine win/lose/payout.
  3. Locates and clicks the "Play Again" (or "Spin Again") button.

OCR is coarse (full-screen pass) because the result text can appear
anywhere in the embed window. Payout extraction uses regex patterns
to find numeric values near win/payout/earned keywords.
"""

import time
import random
import logging
from bot.platform import PlatformManager
from bot.vision import VisionEngine

logger = logging.getLogger("DankBot.Slots")


def execute_slots_spin(screen_bgr, log_func) -> dict:
    """Execute one slots spin from result read through to Play Again.

    Flow:
      1. Wait 3-4.5s for the spinning animation to settle.
      2. OCR the entire screen for win/lose/payout keywords.
      3. Log the result and extract payout if applicable.
      4. Find and click "Play Again" or "Spin Again" (blurple button).
      5. Return result dict.

    Args:
        screen_bgr: Full-screen BGR numpy array.
        log_func: Callable for logging (accepts string).

    Returns:
        Dict with keys:
          completed (bool) — True if Play Again was clicked.
          payout (int) — parsed payout amount (0 if unknown).
          win (bool) — whether a win was detected by OCR.
          error (str or None) — error description if button not found.
    """
    result = {
        'completed': False,
        'payout': 0,
        'win': False,
        'error': None,
    }

    log_func("[*] Slots: waiting for spin result...")
    time.sleep(random.uniform(3.0, 4.5))

    screen_bgr = PlatformManager.capture_scaled_screen()
    text = VisionEngine.ocr_region(screen_bgr, (0, 0, screen_bgr.shape[1], screen_bgr.shape[0]))

    text_lower = text.lower()
    if 'won' in text_lower or 'payout' in text_lower or 'win' in text_lower:
        result['win'] = True
        log_func("[+] Slots: detected a win!")
        payout = _extract_payout(text)
        if payout:
            result['payout'] = payout
            log_func(f"[+] Payout: {payout}")
    elif 'lost' in text_lower:
        result['win'] = False
        log_func("[-] Slots: lost this spin.")
    else:
        log_func("[*] Slots: result unclear (OCR).")

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
    """Parse a payout amount from OCR text.

    Tries patterns in order:
      1. "won/win/payout/earned: $X,XXX"
      2. "X,XXX coins/currency"

    Returns int or None if no amount found.
    """
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
