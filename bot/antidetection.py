import random
import math
import time
import logging
import pyautogui

logger = logging.getLogger("DankBot.AntiDetection")

# ── Bézier Curve Mouse Movement ──────────────────────────────────────

def bezier_point(t, points):
    """Evaluate a cubic Bézier curve at parameter t (0–1) given 4 control points."""
    if len(points) == 4:
        p = ((1-t)**3 * points[0] +
             3*(1-t)**2 * t * points[1] +
             3*(1-t) * t**2 * points[2] +
             t**3 * points[3])
    else:
        n = len(points) - 1
        p = [0, 0]
        for i, pt in enumerate(points):
            coeff = math.comb(n, i) * (1-t)**(n-i) * t**i
            p[0] += coeff * pt[0]
            p[1] += coeff * pt[1]
    return int(p[0]), int(p[1])


def human_mouse_move(target_x, target_y, velocity_px_per_sec=800, overshoot=True):
    """
    Move the mouse from the current position to (target_x, target_y)
    along a human-like cubic Bézier curve with variable speed.
    """
    start_x, start_y = pyautogui.position()
    dx = target_x - start_x
    dy = target_y - start_y
    dist = math.hypot(dx, dy)
    if dist < 10:
        pyautogui.moveTo(target_x, target_y)
        return

    # Generate 2 random control points biased toward the target direction
    ctrl1 = (
        start_x + dx * random.uniform(0.1, 0.3) + random.randint(-60, 60),
        start_y + dy * random.uniform(0.1, 0.3) + random.randint(-60, 60),
    )
    ctrl2 = (
        start_x + dx * random.uniform(0.7, 0.9) + random.randint(-60, 60),
        start_y + dy * random.uniform(0.7, 0.9) + random.randint(-60, 60),
    )

    # Optional overshoot beyond target, then correct
    if overshoot and dist > 50 and random.random() < 0.25:
        end_point = (
            target_x + dx * random.uniform(0.05, 0.12),
            target_y + dy * random.uniform(0.05, 0.12),
        )
    else:
        end_point = (target_x, target_y)

    points = [(start_x, start_y), ctrl1, ctrl2, end_point]

    duration = dist / velocity_px_per_sec
    duration *= random.uniform(0.85, 1.15)
    steps = max(8, int(dist / random.uniform(3, 8)))

    for i in range(steps + 1):
        t = i / steps
        # Add speed variance: slow at start, faster mid, slow at end
        eased_t = 3*t**2 - 2*t**3
        px, py = bezier_point(eased_t, points)
        pyautogui.moveTo(px, py)
        time.sleep(duration / steps * random.uniform(0.7, 1.3))

    # If we overshot, do a small correction
    if end_point != (target_x, target_y):
        time.sleep(random.uniform(0.03, 0.08))
        pyautogui.moveTo(target_x, target_y)


def human_click(target_x, target_y, button='left'):
    """Move to target with human-like motion, then click."""
    human_mouse_move(target_x, target_y)
    time.sleep(random.uniform(0.02, 0.08))
    pyautogui.click(button=button)


# ── Typing Realism ───────────────────────────────────────────────────

_TYPING_SPEED_PROFILE = {
    'slow':    (0.12, 0.25),
    'normal':  (0.06, 0.15),
    'fast':    (0.03, 0.08),
}

def human_type(text, profile='normal', typo_chance=0.03):
    """
    Type text with realistic timing and occasional typos+corrections.
    profile: 'slow' | 'normal' | 'fast'
    typo_chance: probability of making a typo per character (0–1)
    """
    interval = _TYPING_SPEED_PROFILE.get(profile, (0.06, 0.15))

    for char in text:
        if random.random() < typo_chance:
            wrong = random.choice('abcdefghijklmnopqrstuvwxyz')
            pyautogui.write(wrong, interval=random.uniform(*interval))
            time.sleep(random.uniform(0.1, 0.3))
            pyautogui.press('backspace')
            time.sleep(random.uniform(0.05, 0.15))

        pyautogui.write(char, interval=random.uniform(*interval))

    # Pause briefly before pressing Enter
    time.sleep(random.uniform(0.15, 0.4))


# ── Session Jitter ──────────────────────────────────────────────────

def jitter_delay(min_sec=0.5, max_sec=0.9, jitter_pct=15):
    """Return a delayed time with random jitter applied."""
    base = random.uniform(min_sec, max_sec)
    jitter = base * jitter_pct / 100.0
    return max(0.1, base + random.uniform(-jitter, jitter))


def jitter_sleep(min_sec, max_sec, jitter_pct=15):
    """Sleep for a random duration with jitter."""
    time.sleep(jitter_delay(min_sec, max_sec, jitter_pct))


# ── Break Profiles ───────────────────────────────────────────────────

BREAK_PROFILES = {
    'light': {
        'interval_min': 25 * 60,
        'interval_max': 40 * 60,
        'duration_min': 60,
        'duration_max': 180,
    },
    'medium': {
        'interval_min': 40 * 60,
        'interval_max': 60 * 60,
        'duration_min': 180,
        'duration_max': 420,
    },
    'heavy': {
        'interval_min': 50 * 60,
        'interval_max': 90 * 60,
        'duration_min': 300,
        'duration_max': 900,
    },
    'random': {
        'interval_min': 15 * 60,
        'interval_max': 120 * 60,
        'duration_min': 30,
        'duration_max': 1200,
    },
}


def get_break_duration(profile_name='medium'):
    """Return a random break duration in seconds for the given profile."""
    profile = BREAK_PROFILES.get(profile_name, BREAK_PROFILES['medium'])
    return random.randint(profile['duration_min'], profile['duration_max'])


def get_break_interval(profile_name='medium'):
    """Return a random interval between breaks in seconds for the given profile."""
    profile = BREAK_PROFILES.get(profile_name, BREAK_PROFILES['medium'])
    return random.randint(profile['interval_min'], profile['interval_max'])
