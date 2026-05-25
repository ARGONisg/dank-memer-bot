import os
import json
import logging

logger = logging.getLogger("DankBot.Config")

DEFAULT_SETTINGS = {
    "command_prefix": "pls ",
    "discord_username": "Xenron",
    "emergency_key": "esc",
    "min_typing_delay": 0.5,
    "max_typing_delay": 0.9,
    
    # Fishing Settings
    "fish_enabled": True,
    "fish_command": "fish catch",
    "fish_bait": "None",
    "fish_equipment": "None",
    "fish_cooldown": 35.0,
    "min_rarity_to_keep": "Rare",  # Keep Common, Uncommon, Rare, Epic, Legendary, Exotic, etc.
    "sell_currency_pref": "Coins", # Coins or Fish Points
    
    # Blackjack Settings
    "bj_enabled": False,
    "bj_command": "bj 5k",
    "bj_cooldown": 45.0,
    
    # Slots Settings
    "slots_enabled": False,
    "slots_command": "slots 100",
    "slots_cooldown": 20.0,
    
    # Humanization & Break Settings
    "break_interval_mins": 60,
    "break_duration_min_sec": 300,
    "break_duration_max_sec": 600,
    "random_jitter_percent": 15,
    
    # Webhook Settings
    "webhook_enabled": False,
    "webhook_url": ""
}

class ConfigManager:
    PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")

    def __init__(self, profile_name="default"):
        self.profile_name = profile_name
        self.settings = DEFAULT_SETTINGS.copy()
        
        # Ensure profiles directory exists
        if not os.path.exists(self.PROFILES_DIR):
            os.makedirs(self.PROFILES_DIR, exist_ok=True)
            
        self.load_profile(profile_name)

    def get_profile_path(self, name):
        """Returns the absolute file path for a given profile name."""
        return os.path.join(self.PROFILES_DIR, f"{name}.json")

    def load_profile(self, name):
        """Loads a profile by name. Generates default if it does not exist."""
        self.profile_name = name
        path = self.get_profile_path(name)
        
        if not os.path.exists(path):
            logger.info(f"Profile '{name}' not found. Creating a default profile.")
            self.settings = DEFAULT_SETTINGS.copy()
            self.save_profile()
            return

        try:
            with open(path, "r") as f:
                loaded = json.load(f)
            
            # Merge with default settings to handle added parameters gracefully
            self.settings = DEFAULT_SETTINGS.copy()
            for k, v in loaded.items():
                if k in self.settings:
                    # Typecast to default's type if possible
                    expected_type = type(self.settings[k])
                    try:
                        if expected_type in (int, float) and type(v) in (int, float):
                            self.settings[k] = expected_type(v)
                        else:
                            self.settings[k] = v
                    except Exception:
                        self.settings[k] = v
                else:
                    self.settings[k] = v
            logger.info(f"Loaded profile '{name}' from {path}")
        except Exception as e:
            logger.error(f"Failed to load profile '{name}' from {path}: {e}")
            self.settings = DEFAULT_SETTINGS.copy()

    def save_profile(self, name=None):
        """Saves current settings to the active or specified profile."""
        if name:
            self.profile_name = name
        path = self.get_profile_path(self.profile_name)
        
        try:
            with open(path, "w") as f:
                json.dump(self.settings, f, indent=2)
            logger.info(f"Saved profile '{self.profile_name}' to {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save profile '{self.profile_name}' to {path}: {e}")
            return False

    def get(self, key, default=None):
        """Safely gets a setting value."""
        return self.settings.get(key, default)

    def set(self, key, value):
        """Sets a setting value."""
        self.settings[key] = value

    def get_all_profiles(self):
        """Returns a list of all saved profile names in the profiles folder."""
        try:
            files = os.listdir(self.PROFILES_DIR)
            profiles = [os.path.splitext(f)[0] for f in files if f.endswith(".json")]
            return profiles if profiles else ["default"]
        except Exception as e:
            logger.error(f"Failed to list profiles: {e}")
            return ["default"]
