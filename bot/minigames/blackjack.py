import time
import random
import re
import logging
from bot.platform import PlatformManager
from bot.vision import VisionEngine

logger = logging.getLogger("DankBot.Blackjack")

# ── Card value mapping for OCR ──────────────────────────────────────

FACE_MAP = {
    'j': 10, 'q': 10, 'k': 10, 'a': 11,
    'jack': 10, 'queen': 10, 'king': 10, 'ace': 11,
}

def card_value(text: str) -> int:
    """Parse a card string into its blackjack numerical value."""
    text = text.strip().lower()
    if text in FACE_MAP:
        return FACE_MAP[text]
    try:
        return int(text)
    except ValueError:
        return 0

# ── Basic Strategy Lookup (S17, 5 decks, no peek) ──────────────────
# Row = player total index (hard: 5-21 mapped to 0-16, soft: A2-A9 mapped to 17-24)
# Col = dealer upcard (2-11, where 11 = Ace)
# Values: H=Hit, S=Stand, D=Double, P=Split, U=Surrender (for Surrender)
# X = not applicable / play as hard total

# Hard totals strategy (5-21 → rows 0-16)
HARD_STRATEGY = {
    # total: [2, 3, 4, 5, 6, 7, 8, 9, 10, A]
    5:  ['H','H','H','H','H','H','H','H','H','H'],
    6:  ['H','H','H','H','H','H','H','H','H','H'],
    7:  ['H','H','H','H','H','H','H','H','H','H'],
    8:  ['H','H','H','H','H','H','H','H','H','H'],
    9:  ['H','D','D','D','D','H','H','H','H','H'],
    10: ['D','D','D','D','D','D','D','D','H','H'],
    11: ['D','D','D','D','D','D','D','D','D','H'],
    12: ['H','H','S','S','S','H','H','H','H','H'],
    13: ['S','S','S','S','S','H','H','H','H','H'],
    14: ['S','S','S','S','S','H','H','H','H','H'],
    15: ['S','S','S','S','S','H','H','H','U','H'],
    16: ['S','S','S','S','S','H','H','U','U','U'],
    17: ['S','S','S','S','S','S','S','S','S','S'],
    18: ['S','S','S','S','S','S','S','S','S','S'],
    19: ['S','S','S','S','S','S','S','S','S','S'],
    20: ['S','S','S','S','S','S','S','S','S','S'],
    21: ['S','S','S','S','S','S','S','S','S','S'],
}

# Soft totals strategy (A2-A9 = rows, dealer 2-A = cols)
SOFT_STRATEGY = {
    # soft_total: [2, 3, 4, 5, 6, 7, 8, 9, 10, A]
    'A2': ['H','H','D','D','D','H','H','H','H','H'],
    'A3': ['H','H','D','D','D','H','H','H','H','H'],
    'A4': ['H','H','D','D','D','H','H','H','H','H'],
    'A5': ['H','H','D','D','D','H','H','H','H','H'],
    'A6': ['H','D','D','D','D','H','H','H','H','H'],
    'A7': ['S','D','D','D','D','S','S','H','H','H'],
    'A8': ['S','S','S','S','D','S','S','S','S','S'],
    'A9': ['S','S','S','S','S','S','S','S','S','S'],
}

# Pair splitting strategy
PAIR_STRATEGY = {
    # pair_value: [2, 3, 4, 5, 6, 7, 8, 9, 10, A]
    '2-2': ['P','P','P','P','P','P','H','H','H','H'],
    '3-3': ['P','P','P','P','P','P','H','H','H','H'],
    '4-4': ['H','H','H','P','P','H','H','H','H','H'],
    '5-5': ['D','D','D','D','D','D','D','D','H','H'],  # never split 5s
    '6-6': ['P','P','P','P','P','H','H','H','H','H'],
    '7-7': ['P','P','P','P','P','P','H','H','H','H'],
    '8-8': ['P','P','P','P','P','P','P','P','P','P'],
    '9-9': ['P','P','P','P','P','S','P','P','S','S'],
    '10-10': ['S','S','S','S','S','S','S','S','S','S'],
    'A-A': ['P','P','P','P','P','P','P','P','P','P'],
}


def decision(player_total: int, dealer_up: int, is_soft: bool = False, pair_value: int = 0) -> str:
    """
    Returns the basic strategy decision for the given hand.
    player_total: the runner's hand total (e.g. 18)
    dealer_up: the dealer's visible card (2-11, where 11=Ace)
    is_soft: True if the hand contains an Ace counted as 11
    pair_value: the value of one card if it's a pair (e.g. 8 for 8-8, 11 for A-A). 0 = not a pair.
    Returns: 'H' (Hit), 'S' (Stand), 'D' (Double), 'P' (Split), 'U' (Surrender).
    """
    dealer_col = min(dealer_up, 11) - 2  # 2→0, 3→1, ..., 10→8, A→9
    if dealer_col < 0 or dealer_col > 9:
        return 'H'

    # Pair strategy (checked first as it takes priority)
    if pair_value >= 2:
        pair_lookup = {
            2: '2-2', 3: '3-3', 4: '4-4', 5: '5-5', 6: '6-6',
            7: '7-7', 8: '8-8', 9: '9-9', 10: '10-10', 11: 'A-A',
        }
        key = pair_lookup.get(pair_value)
        if key and key in PAIR_STRATEGY:
            return PAIR_STRATEGY[key][dealer_col]

    # Soft total
    if is_soft:
        soft_key = f'A{player_total - 11}'  # A2 → total 13 → key 'A2'
        if soft_key in SOFT_STRATEGY:
            return SOFT_STRATEGY[soft_key][dealer_col]

    # Hard total
    clamped = max(5, min(21, player_total))
    return HARD_STRATEGY[clamped][dealer_col]


# ── OCR helpers for card values and game state ──────────────────────

def extract_hand_info(ocr_text: str):
    """
    Parse OCR output from a blackjack embed to extract:
      - player_total (int or None)
      - dealer_up (int or None)
      - is_blackjack (bool)
      - is_bust (bool)
      - is_pair (bool)
      - hand_over (bool) - game result shown
    """
    text = ocr_text.lower()
    info = {
        'player_total': None,
        'dealer_up': None,
        'is_blackjack': False,
        'is_bust': False,
        'is_pair': False,
        'hand_over': False,
    }

    # Detect game over keywords
    for kw in ['win', 'won', 'lose', 'lost', 'push', 'bust', 'blackjack']:
        if kw in text:
            info['hand_over'] = True
            break

    # Detect bust
    if re.search(r'\byou bust\b', text) or re.search(r'\bbust', text):
        info['is_bust'] = True
        info['hand_over'] = True

    # Parse player total: look for "you: X" or "total: X" or "X (current)"
    total_match = re.search(r'(?:you|your|total)[:\s]*(\d{1,2})', text)
    if total_match:
        info['player_total'] = int(total_match.group(1))

    # Parse dealer upcard: look for "dealer: X" or a card value after "dealer"
    dealer_match = re.search(r'(?:dealer|their)[:\s]*(\w+)', text)
    if dealer_match:
        info['dealer_up'] = card_value(dealer_match.group(1))

    # Check for pair (both cards same value)
    pair_match = re.search(r'pair|(?:two|both)\s+\w+', text)
    if pair_match:
        info['is_pair'] = True

    # Blackjack
    if 'blackjack' in text:
        info['is_blackjack'] = True
        info['hand_over'] = True

    return info


def extract_hand_info_from_screen(screen_bgr):
    """
    OCR the blackjack embed region and extract hand info.
    Reads from the bottom 40-90% of screen.
    """
    h, w = screen_bgr.shape[:2]
    crop = screen_bgr[int(h * 0.15):int(h * 0.85), :]
    text = VisionEngine.ocr_region(screen_bgr, (0, int(h * 0.15), w, int(h * 0.7)))
    if not text:
        return {'player_total': None, 'dealer_up': None, 'hand_over': False}
    return extract_hand_info(text)


# ── Button detection ─────────────────────────────────────────────────

def find_bj_buttons(screen_bgr):
    """
    Find all blackjack action buttons on screen.
    Returns dict with keys: 'hit', 'stand', 'double', 'split', 'surrender', 'play_again'.
    Each value is a button dict or None.
    """
    buttons = {}
    blurple = VisionEngine.find_buttons_by_color(screen_bgr, 'blurple')
    grey = VisionEngine.find_buttons_by_color(screen_bgr, 'grey')
    green = VisionEngine.find_buttons_by_color(screen_bgr, 'green')

    # Label-check each button by OCR
    for btn_list, group in [(blurple, 'blurple'), (grey, 'grey'), (green, 'green')]:
        for btn in btn_list:
            label = VisionEngine.ocr_region(screen_bgr, btn['rect']).lower()
            if 'hit' in label:
                buttons['hit'] = btn
            elif 'stand' in label:
                buttons['stand'] = btn
            elif 'double' in label:
                buttons['double'] = btn
            elif 'split' in label:
                buttons['split'] = btn
            elif 'surrender' in label or 'concede' in label:
                buttons['surrender'] = btn
            elif 'play again' in label or 'new bet' in label:
                buttons['play_again'] = btn

    return buttons


# ── Main blackjack hand execution ────────────────────────────────────

def execute_blackjack_hand(screen_bgr, config, log_func) -> dict:
    """
    Play one full hand of blackjack using basic strategy.
    Returns stats dict: {won, lost, pushed, blackjack, payout_estimate}
    """
    result = {
        'completed': False,
        'won': False,
        'lost': False,
        'pushed': False,
        'blackjack': False,
        'payout': 0,
        'error': None,
    }

    username = config.get("discord_username", "Xenron")
    skip_check = config.get("skip_embed_check", False)

    # Verify embed ownership
    if not skip_check and not VisionEngine.verify_embed_owner(screen_bgr, username):
        log_func("[!] Blackjack embed not ours.")
        result['error'] = 'embed_owner_mismatch'
        return result

    # Play the hand loop (Hit until stand/bust/21)
    max_hits = 10
    for hit_num in range(max_hits):
        if hit_num > 0:
            time.sleep(random.uniform(1.0, 2.0))
            screen_bgr = PlatformManager.capture_scaled_screen()

        info = extract_hand_info_from_screen(screen_bgr)
        buttons = find_bj_buttons(screen_bgr)

        # If hand is over (bust, stand, blackjack, etc.)
        if info['hand_over'] or info['is_blackjack']:
            log_func(f"[+] Hand over. Looking for Play Again...")
            if buttons.get('play_again'):
                VisionEngine.click_button(buttons['play_again'])
                log_func("[+] Clicked Play Again.")
                time.sleep(random.uniform(1.0, 2.0))
            result['completed'] = True
            return result

        total = info['player_total']
        dealer = info['dealer_up']

        if total is None or dealer is None:
            log_func("[!] Could not read hand values. Hitting as fallback.")
            if buttons.get('hit'):
                VisionEngine.click_button(buttons['hit'])
                continue
            break

        # Determine hand type and make decision
        is_soft = False
        # Heuristic pair detection: if detected as pair, pair value = total/2
        # (A-A is ambiguous with 6-6; will be improved with card-specific OCR)
        pair_value = (total // 2) if info['is_pair'] and total % 2 == 0 else 0
        # If total > 21, we busted
        if total > 21:
            log_func(f"[!] Bust with {total}.")
            result['lost'] = True
            result['completed'] = True
            # Wait for result screen
            time.sleep(random.uniform(1.5, 2.5))
            screen_bgr = PlatformManager.capture_scaled_screen()
            buttons = find_bj_buttons(screen_bgr)
            if buttons.get('play_again'):
                VisionEngine.click_button(buttons['play_again'])
            return result

        dec = decision(total, dealer, is_soft, pair_value)
        log_func(f"[+] You: {total}, Dealer: {dealer} → {dec}")

        if dec == 'U' and buttons.get('surrender'):
            VisionEngine.click_button(buttons['surrender'])
            log_func("[+] Surrendered.")
            time.sleep(random.uniform(1.5, 2.5))
            screen_bgr = PlatformManager.capture_scaled_screen()
            buttons = find_bj_buttons(screen_bgr)
            if buttons.get('play_again'):
                VisionEngine.click_button(buttons['play_again'])
            result['completed'] = True
            return result

        elif dec == 'P' and buttons.get('split'):
            VisionEngine.click_button(buttons['split'])
            log_func("[+] Split.")
            continue

        elif dec == 'D' and buttons.get('double'):
            VisionEngine.click_button(buttons['double'])
            log_func("[+] Double down.")
            result['completed'] = True
            return result

        elif dec == 'D' and not buttons.get('double'):
            # Can't double, hit instead
            if buttons.get('hit'):
                VisionEngine.click_button(buttons['hit'])
                log_func("[+] Hit (Double unavailable).")
                continue

        elif dec == 'H' and buttons.get('hit'):
            VisionEngine.click_button(buttons['hit'])
            log_func("[+] Hit.")
            continue

        elif dec == 'S' and buttons.get('stand'):
            VisionEngine.click_button(buttons['stand'])
            log_func("[+] Stand.")
            time.sleep(random.uniform(1.5, 2.5))
            screen_bgr = PlatformManager.capture_scaled_screen()
            buttons = find_bj_buttons(screen_bgr)
            if buttons.get('play_again'):
                VisionEngine.click_button(buttons['play_again'])
            result['completed'] = True
            return result

        else:
            # Fallback: hit if unsure
            if buttons.get('hit'):
                VisionEngine.click_button(buttons['hit'])
                log_func("[+] Hit (fallback).")
                continue
            break

    result['completed'] = True
    return result
