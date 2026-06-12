"""
Vision Engine — screen analysis for the Dank Memer automation framework.

This module provides all computer-vision primitives used by the bot:
  - Color-based button detection (Discord UI buttons by hue)
  - OCR (pytesseract) for reading text from embedded messages
  - Contour-based embed-header scanning
  - Water-grid / fish-shadow detection for the fishing minigame
  - Result parsing for catch outcomes

Coordinate convention
---------------------
All rectangles are (x, y, w, h) in full-screen pixel coordinates.
OpenCV images are in BGR (Blue-Green-Red) channel order, NOT RGB.
All HSV ranges use OpenCV's H range 0..180 (not 0..360).

Colour ranges are deliberately broad to tolerate Discord theme,
zoom, and GPU-rendering variations across macOS and Windows.
False-positive button clicks are preferable to missed buttons because
the bot can recover from a wrong click (cooldown/state reset).

Debug mode
----------
Call VisionEngine.enable_debug(True) in main.py. When enabled, annotated
screenshots are saved to data/debug/ automatically when:
  - OCR returns empty text from a button or embed region
  - A candidate region is too small (< 2 px) for OCR
"""

import cv2
import numpy as np
import pytesseract
import re
import logging
import pyautogui
from bot.antidetection import human_click

logger = logging.getLogger("DankBot.Vision")

# ── Tesseract Path (macOS Homebrew ARM) ────────────────────────────────
# Change this path for other OS/distributions or override at runtime
# with VisionEngine.set_tesseract_path().
pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/bin/tesseract'

# ── Discord Button Colours (BGR) ───────────────────────────────────────
# Discord uses four standard button colours, rendered in sRGB.
# Because GPU blending, theme contrast, and display calibration vary, each
# range is intentionally broad (~20-50% tolerance) to avoid false negatives.
#
# Reference hex → BGR:
#   Blurple  #5865F2 → BGR(242, 101, 88)
#   Green    #23A559 → BGR(89, 165, 35)
#   Grey     #4E5058 → BGR(88, 80, 78)
#   Red      #DA373C → BGR(60, 55, 218)
#
# Each entry is a tuple (lower_bgr, upper_bgr) passed directly to cv2.inRange.
BUTTON_COLORS = {
    'blurple': [(180, 60, 50),  (275, 150, 135)],
    'green':   [(55, 115, 10),  (135, 215, 75)],
    'grey':    [(55, 45, 45),   (135, 130, 130)],
    'red':     [(30, 25, 175),  (100, 95, 255)],
}

# ── Debug Screenshot Dumping ───────────────────────────────────────────
# Controlled by VisionEngine.enable_debug(). When enabled, failed OCR
# regions and small-region warnings are saved as PNG to data/debug/.
_DEBUG_SAVE = False
_DEBUG_DIR = None

# ── Fishing Water Grid (HSV) ───────────────────────────────────────────
# OpenCV HSV: H 0..180, S 0..255, V 0..255.
# Discord's water-blue in the fishing embed falls in this band.
WATER_HSV_LOWER = np.array([88, 40, 40])
WATER_HSV_UPPER = np.array([132, 255, 255])


class VisionEngine:
    """Collection of static CV methods for screen analysis.

    Every method accepts a BGR numpy array (from pyautogui.screenshot()
    converted via numpy) and returns screen coordinates or parsed results.
    """

    # ── Debug Control ──────────────────────────────────────────────────

    @staticmethod
    def enable_debug(enable: bool = True, directory: str = None):
        """Turn debug screenshot dumping on/off.

        Args:
            enable: Set True to save screenshots on OCR failure.
            directory: Optional custom directory (default: data/debug/).
        """
        global _DEBUG_SAVE, _DEBUG_DIR
        _DEBUG_SAVE = enable
        _DEBUG_DIR = directory

    @staticmethod
    def save_debug_screenshot(screen_bgr, label: str, annotated=None):
        """Save an annotated screenshot to the debug directory.

        Only writes if debug mode is enabled. Adds green rectangles for
        each entry in the optional ``annotated`` list (each dict must have
        a 'rect' key with (x, y, w, h)). Filename includes the label
        and a HHMMSS timestamp.
        """
        if not _DEBUG_SAVE:
            return
        import os, time
        d = _DEBUG_DIR or os.path.join(os.path.dirname(__file__), '..', 'data', 'debug')
        os.makedirs(d, exist_ok=True)
        ts = time.strftime("%H%M%S")
        img = screen_bgr.copy()
        if annotated is not None:
            for r in annotated:
                x, y, w, h = r['rect']
                cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.imwrite(os.path.join(d, f"{label}_{ts}.png"), img)

    @staticmethod
    def set_tesseract_path(path: str):
        """Override the Tesseract binary path at runtime."""
        pytesseract.pytesseract.tesseract_cmd = path

    # ── Button Detection ──────────────────────────────────────────────
    #
    # Pipeline:
    #   1. cv2.inRange() isolate pixels within BUTTON_COLORS for a given colour
    #   2. Morphological erode/dilate to remove noise and fill gaps
    #   3. cv2.findContours() to discover connected blobs
    #   4. Filter by area and aspect ratio (Discord buttons are ~2-5x wide)
    #   5. Return list of {rect, cx, cy, area} for clickable candidates

    @staticmethod
    def find_buttons_by_color(screen_bgr, color_name: str, min_area=300):
        """Find rectangular UI buttons on screen by colour.

        Args:
            screen_bgr: Full-screen BGR numpy array.
            color_name: Key into BUTTON_COLORS ('blurple', 'green', 'grey', 'red').
            min_area: Minimum pixel area to accept a candidate (filters noise).

        Returns:
            List of dicts with keys:
              'rect' → (x, y, w, h)
              'cx'   → centre x (for clicking)
              'cy'   → centre y
              'area' → pixel area (w * h)
        """
        lower, upper = BUTTON_COLORS.get(color_name)
        if lower is None:
            return []

        mask = cv2.inRange(screen_bgr, lower, upper)
        # Erode to remove stray single-pixel noise, then dilate to re-connect
        # nearby clusters that belong to the same button (rendered with antialiasing).
        mask = cv2.erode(mask, None, iterations=1)
        mask = cv2.dilate(mask, None, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            if area < min_area:
                continue
            aspect = w / h if h > 0 else 0
            # Discord buttons are wider than tall, roughly 2:1 to 5:1.
            # Reject very tall/narrow blobs (likely scrollbars, dividers, etc.).
            if 1.3 < aspect < 6.0:
                results.append({
                    'rect': (x, y, w, h),
                    'cx': x + w // 2,
                    'cy': y + h // 2,
                    'area': area,
                })
        return results

    @staticmethod
    def find_buttons_by_text(screen_bgr, text_contains: str, color_name=None):
        """Find a button whose OCR text contains a given substring.

        This is the primary method for locating action buttons like
        "Hit", "Stand", "Spin", "Fish", etc. It searches all colour
        channels (or a single colour if ``color_name`` is given) and
        returns the first button whose OCR'd text matches.

        Args:
            screen_bgr: Full-screen BGR numpy array.
            text_contains: Substring to search for (case-insensitive).
            color_name: Optional colour filter (e.g. 'blurple' to only
                        check blurple buttons).

        Returns:
            First matching button dict, or None if no match found.
        """
        colors = [color_name] if color_name else list(BUTTON_COLORS.keys())
        for color in colors:
            buttons = VisionEngine.find_buttons_by_color(screen_bgr, color)
            for btn in buttons:
                text = VisionEngine.ocr_region(screen_bgr, btn['rect'])
                if text_contains.lower() in text.lower():
                    return btn
        return None

    @staticmethod
    def find_grid_buttons_below(
        screen_bgr, above_rect, rows=3, cols=3, color_name='grey'
    ):
        """Find a grid of buttons directly below a reference rectangle.

        Designed for the fishing minigame where a 3x3 button grid
        (the 'catch' buttons) appears below the water grid embed.

        Steps:
          1. Crop region below ``above_rect``.
          2. Find all grey buttons in that region via ``find_buttons_by_color``.
          3. Cluster buttons into rows by vertical proximity.
          4. Sort each row left-to-right.
          5. Index row-major (0..rows*cols-1).

        Args:
            screen_bgr: Full-screen BGR numpy array.
            above_rect: (x, y, w, h) of the element above the grid.
            rows: Expected number of grid rows (default 3).
            cols: Expected number of grid columns (default 3).
            color_name: Button colour to search for (default 'grey').

        Returns:
            List of up to rows*cols button dicts with an extra 'grid_index' key,
            or None if no buttons were found.
        """
        x_ref, y_ref, w_ref, h_ref = above_rect
        search_y0 = y_ref + h_ref + 5
        search_y1 = min(search_y0 + int(h_ref * 1.8), screen_bgr.shape[0])
        region_bgr = screen_bgr[search_y0:search_y1, :]

        buttons = VisionEngine.find_buttons_by_color(region_bgr, color_name, min_area=150)
        if not buttons:
            return None

        # Re-base coordinates from cropped region back to full screen.
        for btn in buttons:
            x, y, w, h = btn['rect']
            y_abs = y + search_y0
            btn['rect'] = (x, y_abs, w, h)
            btn['cy'] = y_abs + h // 2

        # Cluster into rows by vertical proximity (buttons in the same
        # row have centres within 25 px of each other vertically).
        buttons.sort(key=lambda b: b['cy'])
        row_clusters = []
        cur = [buttons[0]]
        for b in buttons[1:]:
            if b['cy'] - cur[-1]['cy'] < 25:
                cur.append(b)
            else:
                row_clusters.append(cur)
                cur = [b]
        if cur:
            row_clusters.append(cur)

        # Keep only the expected number of top rows.
        row_clusters = row_clusters[:rows]

        # Within each row, sort left-to-right and assign grid indices.
        indexed = []
        for r_idx, row in enumerate(row_clusters):
            row.sort(key=lambda b: b['cx'])
            for c_idx, btn in enumerate(row[:cols]):
                indexed.append({
                    'grid_index': r_idx * cols + c_idx,
                    'rect': btn['rect'],
                    'cx': btn['cx'],
                    'cy': btn['cy'],
                })

        return indexed if indexed else None

    # ── Water Grid & Fish Shadow ─────────────────────────────────────
    #
    # The fishing minigame shows a 3x3 grid of blue-ish water cells.
    # One cell contains a darker "shadow" (the fish). The bot needs to
    # click the matching cell in the 3x3 button grid below.

    @staticmethod
    def find_water_grid(screen_bgr):
        """Locate the 3x3 blue water grid on screen.

        Uses HSV colour thresholding (WATER_HSV_LOWER / WATER_HSV_UPPER)
        to isolate blue regions, then finds the largest roughly-square
        contour near the centre of the screen.

        Returns:
            (x, y, w, h) bounding rectangle of the water grid, or None.
        """
        hsv = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, WATER_HSV_LOWER, WATER_HSV_UPPER)
        mask = cv2.erode(mask, None, iterations=1)
        mask = cv2.dilate(mask, None, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_rect = None
        best_area = 0
        sh, sw = screen_bgr.shape[:2]

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            aspect = w / h if h else 0
            # Water grid: roughly square, large, in central area.
            if 0.7 < aspect < 1.3 and area > 4000:
                cx, cy = x + w // 2, y + h // 2
                if (cx > sw * 0.08 and cx < sw * 0.92 and
                        cy > sh * 0.08 and cy < sh * 0.92):
                    if area > best_area:
                        best_area = area
                        best_rect = (x, y, w, h)

        return best_rect

    @staticmethod
    def find_fish_shadow(water_rect, screen_bgr):
        """Determine which cell (0-8) in the 3x3 water grid contains the fish.

        Strategy: divide the water grid into 9 cells, compute a darkness
        score for each cell (fraction of dark pixels + median brightness),
        and return the index of the darkest cell. Confidence threshold
        prevents false positives from noise.

        Args:
            water_rect: (x, y, w, h) from ``find_water_grid()``.
            screen_bgr: Full-screen BGR numpy array.

        Returns:
            Cell index 0..8, or None if confidence < 0.25.
        """
        x, y, w, h = water_rect
        crop = screen_bgr[y:y + h, x:x + w]
        grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        cell_h, cell_w = h // 3, w // 3
        scores = []

        for row in range(3):
            for col in range(3):
                y1, y2 = row * cell_h, (row + 1) * cell_h
                x1, x2 = col * cell_w, (col + 1) * cell_w
                cell = grey[y1:y2, x1:x2]

                # dark_frac: proportion of pixels with value < 65 (dark).
                dark_frac = float(np.sum(cell < 65)) / cell.size
                # median_score: how dark the median pixel is (1.0 = black).
                median_val = float(np.median(cell))
                median_score = 1.0 - median_val / 255.0
                # Weighted combination: dark fraction is slightly more
                # important than median brightness.
                combined = dark_frac * 0.55 + median_score * 0.45
                scores.append((combined, row * 3 + col))

        scores.sort(key=lambda t: t[0], reverse=True)
        best_score, best_idx = scores[0]

        if best_score < 0.25:
            logger.debug(f"Fish shadow confidence too low: {best_score:.3f}")
            return None

        logger.debug(f"Fish shadow cell {best_idx}  score={best_score:.3f}")
        return best_idx

    # ── OCR Utilities ────────────────────────────────────────────────

    @staticmethod
    def ocr_region(screen_bgr, rect):
        """Run Tesseract OCR on a specific (x, y, w, h) region.

        Pipeline:
          1. Clamp rectangle to screen bounds (OCR crashes on negative coords).
          2. Convert region to grayscale.
          3. Apply Otsu thresholding to binarize (white text on dark bg).
          4. Run pytesseract with ``--psm 6`` (uniform block) and ``--oem 3``
             (LSTM + legacy engine fallback).

        PSM 6 is preferred over PSM 7 (single line) because Discord embeds
        often contain multi-line text (e.g. "Hit\nStand\nDouble Down").

        If the result is empty and debug mode is on, a screenshot is saved
        automatically to data/debug/ for post-mortem analysis.

        Args:
            screen_bgr: Full-screen BGR numpy array.
            rect: (x, y, w, h) region to OCR.

        Returns:
            Stripped text string (may be empty).
        """
        x, y, w, h = rect
        if w <= 2 or h <= 2:
            VisionEngine.save_debug_screenshot(screen_bgr, f"ocr_tiny_{x}_{y}")
            return ""
        # Clamp to screen bounds so we never pass negative coordinates to OpenCV.
        sh, sw = screen_bgr.shape[:2]
        x, y = max(0, x), max(0, y)
        w = min(w, sw - x)
        h = min(h, sh - y)
        if w <= 2 or h <= 2:
            return ""

        region = screen_bgr[y:y + h, x:x + w]
        grey = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(thresh, config='--psm 6 --oem 3').strip()
        if not text:
            VisionEngine.save_debug_screenshot(screen_bgr, f"ocr_empty_{x}_{y}_{w}_{h}")
        return text

    @staticmethod
    def find_embed_header_text(screen_bgr):
        """Scan the screen for the thin coloured border of a Discord embed
        and OCR the header text directly above it.

        Discord embeds have a 4-6 px coloured strip on the left edge.
        The embed's header text (e.g. "Xenron pls fish catch") sits
        just above that strip. This method uses contour detection to find
        these strips — far faster than the previous nested-pixel-loop approach
        (~1 ms vs 5-10 seconds).

        It checks four standard embed-border colours: green, blurple, red, grey.

        Returns:
            OCR'd header text string, or empty string if nothing found.
        """
        sh, sw = screen_bgr.shape[:2]
        # Scan the centre band (15%-88% height) for coloured strips.
        scan_top, scan_bot = int(sh * 0.15), int(sh * 0.88)

        # Border colour ranges (BGR). Each corresponds to a Discord embed colour.
        border_colors = [
            (np.array([50, 130, 15]), np.array([110, 195, 55])),   # green border
            (np.array([200, 75, 60]), np.array([255, 135, 110])),  # blurple border
            (np.array([55, 45, 200]), np.array([95, 80, 245])),    # red border
            (np.array([65, 60, 60]), np.array([125, 120, 120])),   # grey border
        ]

        for lower, upper in border_colors:
            mask = cv2.inRange(screen_bgr, lower, upper)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                bx, by, bw, bh = cv2.boundingRect(cnt)
                # Check for a thin vertical line in the central horizontal band.
                if (1 <= bw <= 15 and bh >= 20 and
                        by >= scan_top and by <= scan_bot and
                        bx >= sw // 5 and bx <= 4 * sw // 5):
                    # Text sits directly above the coloured strip.
                    text_y1 = max(0, by - 40)
                    text_y2 = max(0, by - 5)
                    text_rect = (max(0, bx - 120), text_y1, 350, text_y2 - text_y1)
                    text = VisionEngine.ocr_region(screen_bgr, text_rect)
                    if text:
                        return text
        return ""

    @staticmethod
    def verify_embed_owner(screen_bgr, username: str) -> bool:
        """Check whether the embed header contains the given username.

        Used to confirm the bot's own embed is being read (not another
        user's message in the same channel).

        Returns: True if username is found in the embed header text.
        """
        text = VisionEngine.find_embed_header_text(screen_bgr)
        if not text:
            return False
        return username.lower() in text.lower()

    # ── Result Parsing ────────────────────────────────────────────────

    @staticmethod
    def read_catch_result(screen_bgr):
        """Parse the bottom portion of the screen for fishing result text.

        Scans the lower two-thirds of the screen for strings like:
          "You caught a Salmon (Rare!)"

        Uses a simple regex approach rather than structured layout parsing.

        Returns:
            (fish_name, rarity) where either or both may be None.
            rarity is one of: Common, Uncommon, Rare, Epic, Legendary,
            Exotic, Mythical.
        """
        sh, sw = screen_bgr.shape[:2]
        crop = screen_bgr[sh // 3:, :]
        text = pytesseract.image_to_string(crop)
        text_lower = text.lower()

        # Ordered list (lowest to highest) for rarity detection.
        rarity_order = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'exotic', 'mythical']
        found_rarity = None
        for word in rarity_order:
            if re.search(rf'\b{word}\b', text_lower):
                found_rarity = word.capitalize()

        # Extract the fish/creature name after "caught a" or "caught an".
        fish_name = None
        match = re.search(r'(?:caught\s+(?:a|an))\s+(\w+)', text, re.IGNORECASE)
        if match:
            fish_name = match.group(1).capitalize()

        return fish_name, found_rarity

    # ── Click Helper ──────────────────────────────────────────────────

    @staticmethod
    def click_button(btn_dict, human=True):
        """Move the mouse to a button's centre and click.

        Args:
            btn_dict: Dict with 'cx' and 'cy' keys (from find_buttons_*).
            human: If True, use human-like Bezier-curve movement and
                   randomised delay via ``human_click``.
        """
        cx, cy = btn_dict['cx'], btn_dict['cy']
        if human:
            human_click(cx, cy)
        else:
            pyautogui.moveTo(cx, cy)
            pyautogui.click()
