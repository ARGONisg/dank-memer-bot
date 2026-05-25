import threading
import logging
from pynput import keyboard

logger = logging.getLogger("DankBot.Killswitch")

class Killswitch:
    def __init__(self, on_trigger=None):
        self._on_trigger = on_trigger
        self._listener = None
        self._thread = None

    def start(self):
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._thread = threading.Thread(target=self._listener.run, daemon=True)
        self._thread.start()
        logger.info("Killswitch listening for ESC or 'q'...")

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
            self._thread = None

    def _on_press(self, key):
        if key == keyboard.Key.esc:
            logger.info("Killswitch triggered: ESC pressed")
            if self._on_trigger:
                self._on_trigger()
            return False
        try:
            if key.char and key.char.lower() == 'q':
                logger.info("Killswitch triggered: 'q' pressed")
                if self._on_trigger:
                    self._on_trigger()
                return False
        except AttributeError:
            pass
