import logging

logger = logging.getLogger("DankBot.Killswitch")

class Killswitch:
    def __init__(self, on_trigger=None):
        self._on_trigger = on_trigger
        self._active = False

    def start(self):
        self._active = True
        logger.info("Killswitch active (ESC/q via GUI)")

    def stop(self):
        self._active = False

    def trigger(self):
        if self._active and self._on_trigger:
            logger.info("Killswitch triggered")
            self._on_trigger()
