import cv2
import numpy as np
import pytesseract
import re
import logging
import pyautogui
from bot.antidetection import human_click

logger = logging.getLogger("DankBot.Vision")

pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/bin/tesseract'

# Concrete BGR values for Discord standard button colors
# Discord Blurple  #5865F2 → BGR(242, 101, 88)
# Discord Green    #23A559 → BGR(89, 165, 35)
# Discord Grey     #4E5058 → BGR(88, 80, 78)
# Discord Red      #DA373C → BGR(60, 55, 218)

BUTTON_COLORS = {
    'blurple': [(202, 81, 68), (255, 131, 118)],   # lower, upper BGR
    'green':   [(69, 135, 15), (115, 195, 55)],
    'grey':    [(68, 60, 58),  (115, 110, 108)],
    'red':     [(40, 35, 188), (85, 80, 245)],
}

# Blue water hue bounds in HSV (OpenCV: H 0..180)
WATER_HSV_LOWER = np.array([88, 40, 40])
WATER_HSV_UPPER = np.array([132, 255, 255])


class VisionEngine:
    """Collection of static CV methods for screen analysis."""

    @staticmethod
    def set_tesseract_path(path: str):
        pytesseract.pytesseract.tesseract_cmd = path

    # ── Button Detection ──────────────────────────────────────────────

    @staticmethod
    def find_buttons_by_color(screen_bgr, color_name: str, min_area=300):
        """
        Find rectangular UI buttons on screen by color.
        Returns list of dicts: {rect, cx, cy, area}.
        """
        lower, upper = BUTTON_COLORS.get(color_name)
        if lower is None:
            return []

        mask = cv2.inRange(screen_bgr, lower, upper)
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
            # Discord buttons: wider than tall, roughly 2x–5x
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
        """
        Find a button containing specific text in or near it.
        If color_name is provided, only search that color type.
        Returns the first matching button dict or None.
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
        """
        Find a grid of buttons positioned directly below a reference rectangle.
        Used to locate the 3x3 Catch buttons below the water grid.
        Returns list of up to rows*cols buttons, indexed row-major, or None.
        """
        x_ref, y_ref, w_ref, h_ref = above_rect
        search_y0 = y_ref + h_ref + 5
        search_y1 = min(search_y0 + int(h_ref * 1.8), screen_bgr.shape[0])
        region_bgr = screen_bgr[search_y0:search_y1, :]

        buttons = VisionEngine.find_buttons_by_color(region_bgr, color_name, min_area=150)
        if not buttons:
            return None

        # Re-base coordinates to full screen
        for btn in buttons:
            x, y, w, h = btn['rect']
            y_abs = y + search_y0
            btn['rect'] = (x, y_abs, w, h)
            btn['cy'] = y_abs + h // 2

        # Cluster into rows by vertical proximity
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

        # Keep only the top `rows` row clusters
        row_clusters = row_clusters[:rows]

        # Within each row, sort by x
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

    @staticmethod
    def find_water_grid(screen_bgr):
        """
        Locate the 3x3 blue water grid on screen.
        Returns (x, y, w, h) bounding rect or None.
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
            # Water grid: roughly square, large, in central area
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
        """
        Determine which cell (0-8) in the 3x3 water grid contains the fish.
        Returns cell index or None if confidence is too low.
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

                dark_frac = float(np.sum(cell < 65)) / cell.size
                median_val = float(np.median(cell))
                median_score = 1.0 - median_val / 255.0
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
        """Run OCR on a specific (x, y, w, h) region. Returns stripped text."""
        x, y, w, h = rect
        if w <= 2 or h <= 2:
            return ""
        # Clamp to screen bounds
        sh, sw = screen_bgr.shape[:2]
        x, y = max(0, x), max(0, y)
        w = min(w, sw - x)
        h = min(h, sh - y)
        if w <= 2 or h <= 2:
            return ""

        region = screen_bgr[y:y + h, x:x + w]
        grey = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return pytesseract.image_to_string(thresh, config='--psm 7').strip()

    @staticmethod
    def find_embed_header_text(screen_bgr):
        """
        Scan screen for the thin text line above a Discord embed
        (e.g. 'Xenron pls fish catch' or 'Xenron used :: fish catch').
        Uses fast contour detection instead of an expensive double loop.
        Returns the OCR'd string or empty string.
        """
        sh, sw = screen_bgr.shape[:2]
        # Scan the center band (15%-88% height) for coloured embed-border strips
        scan_top, scan_bot = int(sh * 0.15), int(sh * 0.88)

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
                
                # Check for a thin vertical line in the central horizontal band of the screen
                if (1 <= bw <= 15 and bh >= 20 and
                        by >= scan_top and by <= scan_bot and
                        bx >= sw // 5 and bx <= 4 * sw // 5):
                    # Text sits directly above this coloured strip
                    text_y1 = max(0, by - 40)
                    text_y2 = max(0, by - 5)
                    text_rect = (max(0, bx - 120), text_y1, 350, text_y2 - text_y1)
                    text = VisionEngine.ocr_region(screen_bgr, text_rect)
                    if text:
                        return text
        return ""

    @staticmethod
    def verify_embed_owner(screen_bgr, username: str) -> bool:
        """Return True if the embed header contains the given username."""
        text = VisionEngine.find_embed_header_text(screen_bgr)
        if not text:
            return False
        return username.lower() in text.lower()

    # ── Result Parsing ────────────────────────────────────────────────

    @staticmethod
    def read_catch_result(screen_bgr):
        """
        Scan the bottom portion of screen for catch-result text.
        Returns (fish_name, rarity) where either can be None.
        """
        sh, sw = screen_bgr.shape[:2]
        crop = screen_bgr[sh // 3:, :]
        text = pytesseract.image_to_string(crop)
        text_lower = text.lower()

        # Detect rarity
        rarity_order = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'exotic', 'mythical']
        found_rarity = None
        for word in rarity_order:
            if re.search(rf'\b{word}\b', text_lower):
                found_rarity = word.capitalize()

        # Extract fish/creature name after "caught a" or "caught an"
        fish_name = None
        match = re.search(r'(?:caught\s+(?:a|an))\s+(\w+)', text, re.IGNORECASE)
        if match:
            fish_name = match.group(1).capitalize()

        return fish_name, found_rarity

    # ── Click Helper ──────────────────────────────────────────────────

    @staticmethod
    def click_button(btn_dict, human=True):
        """Move mouse to button centre and click."""
        cx, cy = btn_dict['cx'], btn_dict['cy']
        if human:
            human_click(cx, cy)
        else:
            pyautogui.moveTo(cx, cy)
            pyautogui.click()
