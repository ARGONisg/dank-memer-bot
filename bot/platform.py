import sys
import os
import subprocess
import time
import logging
import pyautogui
import cv2
import numpy as np

logger = logging.getLogger("DankBot.Platform")

class PlatformManager:
    @staticmethod
    def get_os():
        """Returns the current operating system identifier."""
        if sys.platform.startswith('darwin'):
            return 'macos'
        elif sys.platform.startswith('win32') or sys.platform.startswith('cygwin'):
            return 'windows'
        elif sys.platform.startswith('linux'):
            return 'linux'
        return 'unknown'

    @classmethod
    def get_screen_scale(cls):
        """
        Detects the screen scale factor (DPI multiplier).
        Compares physical screenshot dimensions to pyautogui logical dimensions.
        """
        try:
            logical_w, logical_h = pyautogui.size()
            screenshot = pyautogui.screenshot()
            actual_w, _ = screenshot.size
            scale = float(actual_w) / logical_w
            logger.debug(f"Detected screen scale factor: {scale:.2f} (Logical: {logical_w}x{logical_h})")
            return scale
        except Exception as e:
            logger.warning(f"Failed to auto-detect screen scale, defaulting to 1.0: {e}")
            return 1.0

    @classmethod
    def focus_discord(cls):
        """Focuses the Discord window, searching desktop apps or browser tabs."""
        os_name = cls.get_os()
        if os_name == 'macos':
            return cls._focus_discord_macos()
        elif os_name == 'windows':
            return cls._focus_discord_windows()
        elif os_name == 'linux':
            return cls._focus_discord_linux()
        return False

    @staticmethod
    def _focus_discord_macos():
        """Brings Discord to focus on macOS using AppleScript."""
        # 1. Try focusing Discord Desktop Application
        script_desktop = '''
        tell application "System Events"
            set processList to every process whose name is "Discord"
            if (count of processList) > 0 then
                set frontmost of process "Discord" to true
                return true
            end if
        end tell
        return false
        '''
        try:
            res = subprocess.check_output(["osascript", "-e", script_desktop], stderr=subprocess.DEVNULL).decode().strip()
            if res == "true":
                logger.info("Focused Discord macOS Desktop application.")
                return True
        except Exception:
            pass

        # 2. Try focusing Google Chrome tab with Discord
        script_chrome = '''
        tell application "Google Chrome"
            set winList to every window
            repeat with win in winList
                set tabList to every tab of win
                set tabIndex to 1
                repeat with t in tabList
                    if title of t contains "Discord" or URL of t contains "discord.com" then
                        set active tab index of win to tabIndex
                        set index of win to 1
                        activate
                        return true
                    end if
                    set tabIndex to tabIndex + 1
                end repeat
            end repeat
        end tell
        return false
        '''
        try:
            res = subprocess.check_output(["osascript", "-e", script_chrome], stderr=subprocess.DEVNULL).decode().strip()
            if res == "true":
                logger.info("Focused Discord inside Google Chrome (macOS).")
                return True
        except Exception:
            pass

        # 3. Try focusing Safari tab with Discord
        script_safari = '''
        tell application "Safari"
            set winList to every window
            repeat with win in winList
                set tabList to every tab of win
                set tabIndex to 1
                repeat with t in tabList
                    if name of t contains "Discord" or URL of t contains "discord.com" then
                        set current tab of win to t
                        set index of win to 1
                        activate
                        return true
                    end if
                    set tabIndex to tabIndex + 1
                end repeat
            end repeat
        end tell
        return false
        '''
        try:
            res = subprocess.check_output(["osascript", "-e", script_safari], stderr=subprocess.DEVNULL).decode().strip()
            if res == "true":
                logger.info("Focused Discord inside Safari (macOS).")
                return True
        except Exception:
            pass

        logger.warning("Could not find or focus Discord window on macOS.")
        return False

    @staticmethod
    def _focus_discord_windows():
        """Brings Discord to focus on Windows."""
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle('Discord')
            if windows:
                # Find the main window (usually longest title or active)
                discord_win = windows[0]
                discord_win.activate()
                logger.info("Focused Discord Windows Desktop application.")
                return True
        except Exception as e:
            logger.debug(f"Failed focusing via pygetwindow: {e}")

        # Fallback to win32gui if pygetwindow fails
        try:
            import win32gui
            import win32con
            def enum_cb(hwnd, result):
                title = win32gui.GetWindowText(hwnd)
                if "discord" in title.lower():
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                    result.append(hwnd)
            hwnds = []
            win32gui.EnumWindows(enum_cb, hwnds)
            if hwnds:
                logger.info("Focused Discord using win32gui (Windows).")
                return True
        except Exception as e:
            logger.debug(f"Failed focusing via win32gui: {e}")

        logger.warning("Could not find or focus Discord window on Windows.")
        return False

    @staticmethod
    def _focus_discord_linux():
        """Brings Discord to focus on Linux using xdotool."""
        try:
            # Look for a window with Discord in its name and focus it
            cmd = "xdotool windowactivate $(xdotool search --onlyvisible --class discord | head -n 1)"
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Focused Discord via xdotool (Linux).")
            return True
        except Exception:
            pass

        try:
            # Fallback to wmctrl
            cmd = "wmctrl -a Discord"
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Focused Discord via wmctrl (Linux).")
            return True
        except Exception:
            pass

        logger.warning("Could not find or focus Discord window on Linux.")
        return False

    @classmethod
    def capture_scaled_screen(cls):
        """
        Captures the primary screen and resizes it to logical coordinate scale.
        This guarantees that pixel positions computed on the returned image match
        pyautogui's click coordinates 1:1, resolving Retina / high-DPI scaling issues.
        """
        try:
            logical_w, logical_h = pyautogui.size()
            screenshot = pyautogui.screenshot()
            
            # Convert PIL image to OpenCV BGR
            img_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # Check if screen scaling is active
            if img_bgr.shape[1] != logical_w:
                logger.debug(f"Scaling screenshot from {img_bgr.shape[1]}x{img_bgr.shape[0]} down to logical {logical_w}x{logical_h}")
                img_bgr = cv2.resize(img_bgr, (logical_w, logical_h), interpolation=cv2.INTER_AREA)
                
            return img_bgr
        except Exception as e:
            logger.error(f"Failed to capture scaled screen: {e}")
            raise e
