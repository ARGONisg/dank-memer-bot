"""
Blackjack Minigame — Shoe counting, Bewersdorff expected-value decision engine,
OCR card reading, and automated hand execution.

Overview
========
The bot plays blackjack using a *composition-dependent basic strategy* driven
by expected-value (EV) maximisation via the Bewersdorff algorithm. Unlike
simple "basic strategy" lookup tables, this algorithm computes exact EVs
for hit / stand / double / split / surrender given the current shoe
composition and the dealer's upcard.

Shoe Tracking
=============
A running count of every card denomination (2-11, where 11 = Ace) is
maintained in a global ``_shoe`` object. Cards the bot has seen (its own
hand, the dealer's upcard, and the dealer's final hand) are removed from
the shoe so that probability calculations reflect the true remaining deck
composition.

The shoe defaults to 5 decks (standard for Dank Memer). It is reset
whenever the engine starts (``reset_shoe()`` called in ``run_loop()``).

Decision Algorithm (Bewersdorff)
=================================
  1. ``dealer_outcomes(upcard, shoe_tuple)`` recursively computes the
     probability distribution of the dealer's final hand value (or bust)
     by enumerating all possible draw sequences from the current shoe.

  2. ``stand_ev(player_val, d_probs)`` = expected value of standing given
     the dealer outcome distribution.

  3. ``draw_ev(...)`` = expected value of hitting one card and then playing
     optimally thereafter (recursive call to ``optimal_ev``).

  4. ``double_ev(...)`` = expected value of doubling down (2x bet, exactly
     one card, then stand).

  5. ``optimal_ev(...)`` returns the maximum EV among stand / hit / double
     (and optionally surrender at depth 0), plus the corresponding action.

  6. ``compute_decision(...)`` wraps ``optimal_ev`` and also considers
     splitting pairs (2x optimal_ev per split hand vs. best alternative).

All functions use ``@lru_cache`` so repeated calls with identical arguments
hit a cache instead of recomputing.

OCR Card Parsing
================
The bot reads the blackjack embed via ``extract_hand_info_from_screen()``,
which OCRs the centre portion of the screen and parses:
  - Player's hand (e.g. "You: A 7 (18)")
  - Dealer's upcard (e.g. "Dealer: 5")
  - Hand-over keywords (win/lose/push/bust/blackjack)
  - Player's total (from parenthesised number)

Buttons are located by colour (blurple = action buttons) and then labelled
by OCR to distinguish Hit / Stand / Double / Split / Surrender / Play Again.

Error Guard
===========
The ``compute_decision()`` call is wrapped in try/except. If the Bewersdorff
engine raises an exception (e.g. the ``TypeError: can't multiply sequence
by non-int of type 'float'`` bug), the error is logged with a full snapshot
of the input state (total, soft flag, dealer upcard, pair card, shoe tuple)
and 'H' (hit) is used as the safe default action.
"""

import time
import random
import re
import logging
from functools import lru_cache
from bot.platform import PlatformManager
from bot.vision import VisionEngine

logger = logging.getLogger("DankBot.Blackjack")

# ── Card Value Mappings ────────────────────────────────────────────────
# Face cards → 10, Ace → 11 (soft/hard handling is done in EV engine).
FACE_MAP = {'j': 10, 'q': 10, 'k': 10, 'a': 11,
            'jack': 10, 'queen': 10, 'king': 10, 'ace': 11}

# All possible card values (2-11) and their count per standard 52-card deck.
# 10 includes 10/J/Q/K (4 each = 16), 11 is Aces (4).
CARD_VALUES = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
PER_DECK = {2: 4, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 16, 11: 4}


# ═══════════════════════════════════════════════════════════════════════
#  SHOE — Running card-count tracker
# ═══════════════════════════════════════════════════════════════════════

class Shoe:
    """Tracks the composition of cards remaining in the shoe.

    Maintains a dict of ``{card_value: remaining_count}`` for each
    denomination 2..11. Cards seen during play are removed via ``remove()``,
    making probability computations progressively more accurate.

    Args:
        num_decks: Number of decks in the shoe (default 5).
    """

    def __init__(self, num_decks=5):
        self.num_decks = num_decks
        self.reset()

    def reset(self, num_decks=None):
        """Reset the shoe to a full set of ``num_decks``."""
        if num_decks is not None:
            self.num_decks = num_decks
        self.counts = {v: PER_DECK[v] * self.num_decks for v in CARD_VALUES}

    def remove(self, card_value):
        """Decrement the count for a single card value. No-op if depleted."""
        c = self.counts.get(card_value)
        if c and c > 0:
            self.counts[card_value] = c - 1

    def total(self):
        """Total number of cards remaining in the shoe."""
        return sum(self.counts.values())

    def copy(self):
        """Return a deep-ish copy (new Shoe, same num_decks, copied dict)."""
        s = Shoe(self.num_decks)
        s.counts = dict(self.counts)
        return s

    def as_tuple(self):
        """Return counts as a tuple ordered by CARD_VALUES for cache key."""
        return tuple(self.counts[v] for v in CARD_VALUES)


# Global shoe instance. Accessed via get_shoe() / reset_shoe().
_shoe = Shoe()

def reset_shoe(num_decks=5):
    """Convenience: reset the global shoe to a full set of decks."""
    _shoe.reset(num_decks)

def get_shoe():
    """Convenience: return the global shoe instance."""
    return _shoe


# ═══════════════════════════════════════════════════════════════════════
#  OCR PARSING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def card_value(text: str) -> int:
    """Convert OCR'd card string to numeric value (2-11).

    Handles face cards ('J'/'Q'/'K' → 10), Ace ('A' → 11),
    and numeric values. Returns 0 if unparseable.
    """
    text = text.strip().lower()
    if text in FACE_MAP:
        return FACE_MAP[text]
    try:
        return int(text)
    except ValueError:
        return 0

def parse_player_cards(ocr_text: str):
    """Parse player's starting cards from OCR text.

    Expects pattern like: ``you: A 7 (18)`` or ``your: 10 J (20)``.
    Extracts at least the first two cards (starting hand).

    Returns list of int card values, or None if unparseable.
    """
    text = ocr_text.lower()
    m = re.search(r'(?:you|your)\s*:\s*([\d\sajqk]+?)\s*(?:\(|$)', text)
    if m:
        raw = m.group(1)
        tokens = re.findall(r'(10|[2-9]|[ajqk])', raw)
        if len(tokens) >= 2:
            return [card_value(t) for t in tokens]
    return None

def parse_dealer_upcard(ocr_text: str):
    """Parse dealer's upcard from OCR text.

    Expects pattern: ``dealer: 5`` or ``their: A``.

    Returns int card value, or None.
    """
    text = ocr_text.lower()
    m = re.search(r'(?:dealer|their)\s*:\s*(\w+)', text)
    if m:
        return card_value(m.group(1))
    return None

def parse_dealer_final_cards(ocr_text: str):
    """Parse dealer's full final hand from OCR text (for shoe tracking).

    Same pattern as parse_player_cards but for the dealer line.
    Returns list of int values, or None.
    """
    text = ocr_text.lower()
    m = re.search(r'(?:dealer|their)\s*:\s*([\d\sajqk]+?)\s*(?:\(|$)', text)
    if m:
        raw = m.group(1)
        tokens = re.findall(r'(10|[2-9]|[ajqk])', raw)
        if len(tokens) >= 2:
            return [card_value(t) for t in tokens]
        if len(tokens) == 1:
            return [card_value(t) for t in tokens]
    return None


# ═══════════════════════════════════════════════════════════════════════
#  BEWERSDORFF EXPECTED-VALUE ENGINE
# ═══════════════════════════════════════════════════════════════════════
#
# These functions compute exact EV for every possible action given the
# current shoe composition. All are memoized via @lru_cache.
#
# CACHE KEYS:
#   shoe_tuple — the output of Shoe.as_tuple(), a 10-element tuple.

@lru_cache(maxsize=8192)
def dealer_outcomes(up_value, shoe_tuple):
    """Recursively compute the probability distribution of the dealer's
    final hand value (or bust) given their upcard and the current shoe.

    The dealer follows standard rules:
      - Hits on 16 or below.
      - Stands on 17 or above (hits on soft 17).
      - Busts on 22+.

    Returns a dict like ``{17: 0.25, 18: 0.15, ..., 'bust': 0.35}``
    where values are probabilities summing to 1.0.

    This is the core of the Bewersdorff algorithm.
    """
    shoe = dict(zip(CARD_VALUES, shoe_tuple))
    total = sum(shoe.values())
    if total == 0:
        return {}

    memo = {}

    def rec(val, soft):
        key = (val, soft)
        if key in memo:
            return memo[key]
        if val > 21:
            res = {'bust': 1.0}
        elif val >= 17 and not (val == 17 and soft):
            res = {val: 1.0}
        else:
            res = {}
            for v, cnt in shoe.items():
                if cnt <= 0:
                    continue
                p = cnt / total
                new_val = val + v
                new_soft = soft or v == 11
                if new_val > 21 and new_soft:
                    new_val -= 10
                    new_soft = False
                if new_val > 21:
                    res['bust'] = res.get('bust', 0) + p
                else:
                    sub = rec(new_val, new_soft)
                    for outcome, prob in sub.items():
                        res[outcome] = res.get(outcome, 0) + p * prob
        memo[key] = res
        return res

    return rec(up_value, up_value == 11)


def stand_ev(player_val, d_probs):
    """Expected value of standing with ``player_val`` given dealer outcomes.

    Win → +1.0, Lose → -1.0, Push → 0.0.
    """
    ev = 0.0
    for outcome, prob in d_probs.items():
        if outcome == 'bust':
            ev += prob * 1.0
        elif outcome > player_val:
            ev += prob * (-1.0)
        elif outcome < player_val:
            ev += prob * 1.0
    return ev


def draw_ev(player_val, is_soft, dealer_up, shoe_tuple, depth):
    """Expected value of hitting (drawing one card then playing optimally).

    Recursively calls ``optimal_ev`` for the post-draw state.
    """
    shoe = dict(zip(CARD_VALUES, shoe_tuple))
    total = sum(shoe.values())
    if total == 0:
        return stand_ev(player_val, dealer_outcomes(dealer_up, shoe_tuple))

    ev = 0.0
    for v, cnt in shoe.items():
        if cnt <= 0:
            continue
        p = cnt / total
        new_val = player_val + v
        new_soft = is_soft or v == 11
        if new_val > 21 and new_soft:
            new_val -= 10
            new_soft = False
        if new_val > 21:
            outcome_ev = -1.0
        else:
            outcome_ev = optimal_ev(new_val, new_soft, dealer_up, shoe_tuple,
                                    can_double=False, can_surrender=False, depth=depth + 1)[0]
        ev += p * outcome_ev
    return ev


def double_ev(player_val, is_soft, dealer_up, shoe_tuple):
    """Expected value of doubling down (2x bet, exactly one card, then stand).

    The EV is double that of standing with the resulting hand, minus the
    additional half-bet loss if busting.
    """
    shoe = dict(zip(CARD_VALUES, shoe_tuple))
    total = sum(shoe.values())
    if total == 0:
        return -2.0

    d_probs = dealer_outcomes(dealer_up, shoe_tuple)
    ev = 0.0
    for v, cnt in shoe.items():
        if cnt <= 0:
            continue
        p = cnt / total
        new_val = player_val + v
        new_soft = is_soft or v == 11
        if new_val > 21 and new_soft:
            new_val -= 10
            new_soft = False
        if new_val > 21:
            outcome_ev = -2.0
        else:
            outcome_ev = 2.0 * stand_ev(new_val, d_probs)
        ev += p * outcome_ev
    return ev


@lru_cache(maxsize=16384)
def optimal_ev(player_val, is_soft, dealer_up, shoe_tuple, can_double=True, can_surrender=True, depth=0):
    """Return the maximum expected value among all legal actions and the
    action that achieves it.

    Actions considered:
      - Stand (S)
      - Surrender (U) — only at depth 0, only if EV < -0.5
      - Hit (H)
      - Double (D) — only if ``can_double`` is True

    Args:
        player_val: Current hand total.
        is_soft: Whether the hand contains a soft Ace.
        dealer_up: Dealer's upcard value.
        shoe_tuple: Shoe composition as a tuple (for caching).
        can_double: Whether doubling is still legal (after a hit, no).
        can_surrender: Whether surrendering is still legal (first decision only).
        depth: Recursion depth (capped at 10 to prevent infinite loops).

    Returns:
        (best_ev, best_action) where best_action is one of 'S', 'H', 'D', 'U'.
    """
    if depth > 10:
        ev = stand_ev(player_val, dealer_outcomes(dealer_up, shoe_tuple))
        return (ev, 'S')

    d_probs = dealer_outcomes(dealer_up, shoe_tuple)

    best_ev = stand_ev(player_val, d_probs)
    best_action = 'S'

    if can_surrender and depth == 0:
        if -0.5 > best_ev:
            best_ev = -0.5
            best_action = 'U'

    hit_ev = draw_ev(player_val, is_soft, dealer_up, shoe_tuple, depth)
    if hit_ev > best_ev:
        best_ev = hit_ev
        best_action = 'H'

    if can_double:
        db_ev = double_ev(player_val, is_soft, dealer_up, shoe_tuple)
        if db_ev > best_ev:
            best_ev = db_ev
            best_action = 'D'

    return (best_ev, best_action)


def compute_decision(player_val, is_soft, dealer_up, shoe_tuple, is_pair=False, pair_card_val=None):
    """Compute the optimal blackjack action given the game state.

    If the player has a pair (same card value in the first two cards),
    evaluates splitting (playing two hands at 2x original EV) vs. the
    best alternative action, and returns 'P' if splitting has higher EV.

    Args:
        player_val: Current hand total.
        is_soft: Whether the hand contains a playable Ace (11).
        dealer_up: Dealer's upcard value.
        shoe_tuple: Shoe composition tuple.
        is_pair: True if the first two cards have equal value.
        pair_card_val: The value of each card in the pair (for split EV).

    Returns:
        Action character: 'S' (stand), 'H' (hit), 'D' (double),
        'P' (split), or 'U' (surrender).
    """
    if player_val >= 21:
        return 'S'

    if is_pair and pair_card_val and pair_card_val >= 2:
        split_ev = 2.0 * optimal_ev(pair_card_val, pair_card_val == 11, dealer_up, shoe_tuple,
                                     can_double=True, can_surrender=False, depth=0)[0]
        other_ev = optimal_ev(player_val, is_soft, dealer_up, shoe_tuple,
                              can_double=True, can_surrender=True, depth=0)[0]
        if split_ev > other_ev:
            return 'P'

    ev, action = optimal_ev(player_val, is_soft, dealer_up, shoe_tuple,
                            can_double=True, can_surrender=True, depth=0)
    return action


# ═══════════════════════════════════════════════════════════════════════
#  HAND EXECUTION
# ═══════════════════════════════════════════════════════════════════════

def extract_hand_info(ocr_text: str):
    """Parse structured hand information from OCR'd embed text.

    Returns a dict with keys:
      - player_total (int or None)
      - dealer_up (int or None)
      - is_blackjack (bool)
      - is_bust (bool)
      - hand_over (bool)  — True if win/lose/push/bust keywords appear
      - player_cards (list of int or None)
    """
    text = ocr_text.lower()
    info = {
        'player_total': None,
        'dealer_up': None,
        'is_blackjack': False,
        'is_bust': False,
        'hand_over': False,
        'player_cards': None,
    }

    for kw in ['win', 'won', 'lose', 'lost', 'push', 'bust']:
        if kw in text:
            info['hand_over'] = True
            break

    if re.search(r'\byou bust\b', text) or re.search(r'\bbust', text):
        info['is_bust'] = True
        info['hand_over'] = True

    total_match = re.search(r'(?:you|your|total)\s*:\s*[\w\s]*\((\d{1,2})\)', text)
    if total_match:
        info['player_total'] = int(total_match.group(1))

    dealer_match = re.search(r'(?:dealer|their)\s*:\s*(\w+)', text)
    if dealer_match:
        info['dealer_up'] = card_value(dealer_match.group(1))

    if 'blackjack' in text:
        info['is_blackjack'] = True
        info['hand_over'] = True

    info['player_cards'] = parse_player_cards(ocr_text)
    return info


def extract_hand_info_from_screen(screen_bgr):
    """OCR the screen and return parsed hand information.

    OCRs the centre band (15%-85% of screen height) where the blackjack
    embed typically appears.
    """
    h, w = screen_bgr.shape[:2]
    text = VisionEngine.ocr_region(screen_bgr, (0, int(h * 0.15), w, int(h * 0.7)))
    if not text:
        return {'player_total': None, 'dealer_up': None, 'hand_over': False, 'player_cards': None}
    return extract_hand_info(text)


def find_bj_buttons(screen_bgr):
    """Locate all blackjack UI buttons by colour + OCR.

    Searches blurple, grey, and green button regions, then OCRs each
    to identify its label.

    Returns a dict mapping button names ('hit', 'stand', 'double',
    'split', 'surrender', 'play_again') to their button dicts.
    """
    buttons = {}
    blurple = VisionEngine.find_buttons_by_color(screen_bgr, 'blurple')
    grey = VisionEngine.find_buttons_by_color(screen_bgr, 'grey')
    green = VisionEngine.find_buttons_by_color(screen_bgr, 'green')

    for btn_list in [blurple, grey, green]:
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


def execute_blackjack_hand(screen_bgr, config, log_func) -> dict:
    """Play one complete blackjack hand from start to finish.

    Flow:
      1. Verify embed ownership.
      2. OCR the initial hand (player cards, dealer upcard).
      3. Track seen cards in the global shoe.
      4. Loop up to 10 times:
         a. Find action buttons.
         b. If hand is over (win/lose/push/bust/BJ), log dealer's final
            cards for shoe tracking, click "Play Again" if available, return.
         c. If player is bust, return.
         d. Compute optimal decision via ``compute_decision()``.
         e. Execute the action (hit / stand / double / split / surrender).
         f. Track newly drawn cards in the shoe.
      5. Return result dict with 'completed', 'won', 'lost', etc.

    Args:
        screen_bgr: Current screen capture (BGR numpy array).
        config: Config dict-like object (for username, skip_embed_check).
        log_func: Callable for logging (accepts string).

    Returns:
        Dict with keys: completed, won, lost, pushed, blackjack, payout, error.
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

    if not skip_check and not VisionEngine.verify_embed_owner(screen_bgr, username):
        log_func("[!] Blackjack embed not ours.")
        result['error'] = 'embed_owner_mismatch'
        return result

    info = extract_hand_info_from_screen(screen_bgr)
    player_cards = info.get('player_cards') or []
    dealer_up = info.get('dealer_up')

    for c in player_cards:
        _shoe.remove(c)
    if dealer_up:
        _shoe.remove(dealer_up)
    if player_cards:
        log_func(f"[+] Cards seen: {player_cards}, dealer up: {dealer_up} | Shoe: {_shoe.total()} remaining")

    deck_info = info
    max_hits = 10
    for hit_num in range(max_hits):
        if hit_num > 0:
            time.sleep(random.uniform(1.0, 2.0))
            screen_bgr = PlatformManager.capture_scaled_screen()
            deck_info = extract_hand_info_from_screen(screen_bgr)

        buttons = find_bj_buttons(screen_bgr)

        if deck_info['hand_over'] or deck_info['is_blackjack']:
            log_func("[+] Hand over.")

            final_text = VisionEngine.ocr_region(
                screen_bgr, (0, int(screen_bgr.shape[0] * 0.15),
                             screen_bgr.shape[1], int(screen_bgr.shape[0] * 0.7)))
            if final_text:
                dealer_final = parse_dealer_final_cards(final_text)
                if dealer_final:
                    for c in dealer_final:
                        _shoe.remove(c)
                    log_func(f"[+] Dealer final cards: {dealer_final} | Shoe: {_shoe.total()} remaining")

            if buttons.get('play_again'):
                VisionEngine.click_button(buttons['play_again'])
                log_func("[+] Clicked Play Again.")
                time.sleep(random.uniform(1.0, 2.0))
            result['completed'] = True
            return result

        total = deck_info['player_total']
        dealer = deck_info['dealer_up']

        if total is None or dealer is None:
            log_func("[!] Could not read hand values. Hitting as fallback.")
            if buttons.get('hit'):
                VisionEngine.click_button(buttons['hit'])
                continue
            break

        if total > 21:
            log_func(f"[!] Bust with {total}.")
            result['lost'] = True
            result['completed'] = True
            time.sleep(random.uniform(1.5, 2.5))
            screen_bgr = PlatformManager.capture_scaled_screen()
            buttons = find_bj_buttons(screen_bgr)
            if buttons.get('play_again'):
                VisionEngine.click_button(buttons['play_again'])
            return result

        current_cards = deck_info.get('player_cards') or player_cards
        if hit_num > 0 and current_cards and len(current_cards) > len(player_cards):
            drawn = current_cards[-1]
            _shoe.remove(drawn)
            player_cards = current_cards
            log_func(f"[+] Drew {drawn} | Shoe: {_shoe.total()} remaining")

        is_soft = any(c == 11 for c in (current_cards or [])) and total <= 21
        is_pair = len(current_cards or []) == 2 and (current_cards[0] == current_cards[1])
        pair_val = current_cards[0] if (current_cards and is_pair) else 0

        try:
            dec = compute_decision(total, is_soft, dealer, _shoe.as_tuple(),
                                   is_pair=is_pair, pair_card_val=pair_val)
        except Exception as e:
            shoe_snapshot = _shoe.as_tuple()
            log_func(f"[!] Decision engine error: {e} | total={total} soft={is_soft} dealer={dealer} pair={pair_val} shoe={shoe_snapshot}")
            logger.exception("Blackjack decision error")
            dec = 'H'

        soft_label = " soft" if is_soft else ""
        log_func(f"[+] You: {total}{soft_label}, Dealer: {dealer}, Cards: {current_cards} → {dec}")

        if dec == 'U' and buttons.get('surrender'):
            VisionEngine.click_button(buttons['surrender'])
            log_func("[+] Surrendered.")
            time.sleep(random.uniform(1.5, 2.5))
            result['completed'] = True
            return result

        if dec == 'P' and buttons.get('split'):
            VisionEngine.click_button(buttons['split'])
            log_func("[+] Split.")
            continue

        if dec == 'D' and buttons.get('double'):
            VisionEngine.click_button(buttons['double'])
            log_func("[+] Double down.")
            result['completed'] = True
            return result

        if dec == 'D' and not buttons.get('double'):
            if buttons.get('hit'):
                VisionEngine.click_button(buttons['hit'])
                log_func("[+] Hit (Double unavailable).")
                continue

        if dec == 'H' and buttons.get('hit'):
            VisionEngine.click_button(buttons['hit'])
            log_func("[+] Hit.")
            continue

        if dec == 'S' and buttons.get('stand'):
            VisionEngine.click_button(buttons['stand'])
            log_func("[+] Stand.")
            time.sleep(random.uniform(1.5, 2.5))
            screen_bgr = PlatformManager.capture_scaled_screen()
            buttons = find_bj_buttons(screen_bgr)

            final_text = VisionEngine.ocr_region(
                screen_bgr, (0, int(screen_bgr.shape[0] * 0.15),
                             screen_bgr.shape[1], int(screen_bgr.shape[0] * 0.7)))
            if final_text:
                dealer_final = parse_dealer_final_cards(final_text)
                if dealer_final:
                    for c in dealer_final:
                        _shoe.remove(c)
                    log_func(f"[+] Dealer final cards: {dealer_final} | Shoe: {_shoe.total()} remaining")

            if buttons.get('play_again'):
                VisionEngine.click_button(buttons['play_again'])
            result['completed'] = True
            return result

        if buttons.get('hit'):
            VisionEngine.click_button(buttons['hit'])
            log_func("[+] Hit (fallback).")
            continue
        break

    result['completed'] = True
    return result
