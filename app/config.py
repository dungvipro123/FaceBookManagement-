import os
import re
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from app.db import get_connection

# Load .env file at startup
ENV_PATH = Path(".env")
if not ENV_PATH.exists():
    ENV_PATH = Path.cwd() / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Validation Regular Expressions
REGEX_DISCORD_WEBHOOK = re.compile(r"^https://(?:ptb\.|canary\.)?discord\.com/api/webhooks/\d+/[A-Za-z0-9_-]+$")
REGEX_FB_GROUP_URL = re.compile(r"^https://(?:www\.)?facebook\.com/groups/[A-Za-z0-9._-]+/?$")
REGEX_MENTION_TAG = re.compile(r"^(|@everyone|@here|<@&\d+>|<@\d+>)$")
REGEX_GEMINI_MODEL = re.compile(r"^[a-zA-Z0-9._-]+$")

# Metadata dictionary for system settings
CONFIG_METADATA = {
    "scan_interval_minutes": {
        "type": int,
        "default": 15,
        "min": 10,
        "max": 1440,
        "requires_restart": False,
    },
    "headless": {
        "type": bool,
        "default": True,
        "requires_restart": False,
    },
    "gemini_model": {
        "type": str,
        "default": "gemini-3.1-flash-lite",
        "requires_restart": False,
    },
    "lan_access_enabled": {
        "type": bool,
        "default": False,
        "requires_restart": True,
    },
    "web_port": {
        "type": int,
        "default": 8080,
        "min": 1024,
        "max": 65535,
        "requires_restart": True,
    },
    "autostart": {
        "type": bool,
        "default": False,
        "requires_restart": False,
    },
}

def mask_secret(value: Optional[str]) -> str:
    """
    Masking rule according to CONTRACTS v2.1:
    - If length <= 8: fixed '••••••••'
    - If length > 8: last 4 chars, previous chars replaced with '••••••••'
    """
    if not value:
        return ""
    val_str = str(value)
    if len(val_str) <= 8:
        return "••••••••"
    return "••••••••" + val_str[-4:]

def get_setting(key: str, default: Any = None) -> Any:
    """Retrieves a configuration value from SQLite system_settings."""
    conn = get_connection()
    row = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        if key in CONFIG_METADATA:
            return CONFIG_METADATA[key]["default"]
        return default
    
    val_str = row["value"]
    meta = CONFIG_METADATA.get(key)
    if meta:
        target_type = meta["type"]
        if target_type == bool:
            return val_str.lower() in ("true", "1", "yes")
        elif target_type == int:
            try:
                return int(val_str)
            except ValueError:
                return meta["default"]
    return val_str

def set_setting(key: str, value: Any) -> None:
    """Stores a configuration value into SQLite system_settings."""
    conn = get_connection()
    val_str = str(value).lower() if isinstance(value, bool) else str(value)
    conn.execute("""
    INSERT INTO system_settings (key, value)
    VALUES (?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value;
    """, (key, val_str))
    conn.commit()

def get_all_settings() -> Dict[str, Any]:
    """Returns all settings with their values and requires_restart flags."""
    settings = {}
    for key, meta in CONFIG_METADATA.items():
        settings[key] = {
            "value": get_setting(key),
            "requires_restart": meta["requires_restart"],
            "type": meta["type"].__name__
        }
    
    # Check if LAN PIN is set without exposing its value
    pin = get_setting("lan_pin", "")
    settings["lan_pin_set"] = bool(pin and len(pin) >= 4)
    return settings

def update_env_file(updates: Dict[str, str]) -> None:
    """Updates key-value pairs in .env safely preserving comments and existing keys."""
    env_lines = []
    found_keys = set()
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    if key in updates:
                        env_lines.append(f"{key}={updates[key]}\n")
                        found_keys.add(key)
                        continue
                env_lines.append(line)
    
    for key, val in updates.items():
        if key not in found_keys:
            env_lines.append(f"{key}={val}\n")
            
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(env_lines)
        
    # Reload environment in current process
    for key, val in updates.items():
        os.environ[key] = val
