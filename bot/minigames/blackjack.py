import time
import random
import re
import logging
from functools import lru_cache
from bot.platform import PlatformManager
from bot.vision import VisionEngine

logger = logging.getLogger("DankBot.Blackjack")

FACE_MAP = {'j': 10, 'q': 10, 'k': 10, 'a': 11,
            'jack': 10, 'queen': 10, 'king': 10, 'ace': 11}

CARD_VALUES = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
PER_DECK = {2: 4, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 16, 11: 4}


class Shoe:
    def __init__(self, num_decks=5):
        self.num_decks = num_decks
        self.reset()

    def reset(self, num_decks=None):
        if num_decks is not None:
            self.num_decks = num_decks
        self.counts = {v: PER_DECK[v] * self.num_decks for v in CARD_VALUES}

    def remove(self, card_value):
        c = self.counts.get(card_value)
        if c and c > 0:
            self.counts[card_value] = c - 1

    def total(self):
        return sum(self.counts.values())

    def copy(self):
        s = Shoe(self.num_decks)
        s.counts = dict(self.counts)
        return s

    def as_tuple(self):
        return tuple(self.counts[v] for v in CARD_VALUES)


_shoe = Shoe()

def reset_shoe(num_decks=5):
    _shoe.reset(num_decks)

def get_shoe():
    return _shoe


def card_value(text: str) -> int:
    text = text.strip().lower()
    if text in FACE_MAP:
        return FACE_MAP[text]
    try:
        return int(text)
    except ValueError:
        return 0

def parse_player_cards(ocr_text: str):
    text = ocr_text.lower()
    m = re.search(r'(?:you|your)\s*:\s*([\d\sajqk]+?)\s*(?:\(|$)', text)
    if m:
        raw = m.group(1)
        tokens = re.findall(r'(10|[2-9]|[ajqk])', raw)
        if len(tokens) >= 2:
            return [card_value(t) for t in tokens]
    return None

def parse_dealer_upcard(ocr_text: str):
    text = ocr_text.lower()
    m = re.search(r'(?:dealer|their)\s*:\s*(\w+)', text)
    if m:
        return card_value(m.group(1))
    return None

def parse_dealer_final_cards(ocr_text: str):
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


@lru_cache(maxsize=8192)
def dealer_outcomes(up_value, shoe_tuple):
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


def extract_hand_info(ocr_text: str):
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
    h, w = screen_bgr.shape[:2]
    text = VisionEngine.ocr_region(screen_bgr, (0, int(h * 0.15), w, int(h * 0.7)))
    if not text:
        return {'player_total': None, 'dealer_up': None, 'hand_over': False, 'player_cards': None}
    return extract_hand_info(text)


def find_bj_buttons(screen_bgr):
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

        dec = compute_decision(total, is_soft, dealer, _shoe.as_tuple(),
                               is_pair=is_pair, pair_card_val=pair_val)
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
