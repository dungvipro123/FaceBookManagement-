import hmac
import time
import secrets
from typing import Dict, Set, Tuple
from app.config import get_setting, set_setting

# In-memory revocable session tokens: {token: created_timestamp}
ACTIVE_SESSIONS: Dict[str, float] = {}
SESSION_MAX_AGE_SECONDS = 30 * 86400  # 30 days

# Failed login attempts per IP: {ip: [(timestamp, count)]}
FAILED_ATTEMPTS: Dict[str, list] = {}
LOCKED_IPS: Dict[str, float] = {}  # {ip: unlock_timestamp}

def is_loopback(host: str) -> bool:
    """Checks if the given client host is a local loopback interface."""
    return host in ("127.0.0.1", "::1", "localhost", "testclient")

def is_ip_locked(client_ip: str) -> bool:
    """Checks if IP is currently locked due to too many failed attempts."""
    now = time.time()
    unlock_time = LOCKED_IPS.get(client_ip)
    if unlock_time:
        if now < unlock_time:
            return True
        else:
            del LOCKED_IPS[client_ip]
            FAILED_ATTEMPTS.pop(client_ip, None)
    return False

def record_failed_attempt(client_ip: str) -> None:
    """Records a failed attempt; locks IP for 15m if 5 attempts within 5m."""
    now = time.time()
    history = FAILED_ATTEMPTS.get(client_ip, [])
    # Keep attempts from last 5 minutes (300 seconds)
    history = [t for t in history if now - t < 300]
    history.append(now)
    FAILED_ATTEMPTS[client_ip] = history
    if len(history) >= 5:
        LOCKED_IPS[client_ip] = now + 900  # 15 minutes lock

def verify_pin(input_pin: str, client_ip: str) -> bool:
    """
    Verifies input PIN against stored lan_pin using constant-time comparison.
    Never logs the PIN.
    """
    current_pin = get_setting("lan_pin", "")
    if not current_pin:
        # Default fallback PIN if not set
        current_pin = "123456"
        set_setting("lan_pin", current_pin)
    
    is_valid = hmac.compare_digest(str(input_pin).strip(), str(current_pin).strip())
    if is_valid:
        FAILED_ATTEMPTS.pop(client_ip, None)
        LOCKED_IPS.pop(client_ip, None)
    else:
        record_failed_attempt(client_ip)
    return is_valid

def create_session() -> str:
    """Generates a secure random session token and stores it in the active store."""
    token = secrets.token_hex(32)
    ACTIVE_SESSIONS[token] = time.time()
    return token

def is_valid_session(token: str) -> bool:
    """Validates if a session token is active and not expired."""
    if not token or token not in ACTIVE_SESSIONS:
        return False
    created = ACTIVE_SESSIONS[token]
    if time.time() - created > SESSION_MAX_AGE_SECONDS:
        del ACTIVE_SESSIONS[token]
        return False
    return True

def revoke_session(token: str) -> None:
    """Revokes a single session token."""
    ACTIVE_SESSIONS.pop(token, None)

def revoke_all_sessions() -> None:
    """Invalidates all currently active sessions."""
    ACTIVE_SESSIONS.clear()

def rotate_pin() -> str:
    """
    Generates a new random 6-digit PIN, saves it to system_settings,
    and invalidates all existing sessions. Returns the new PIN once.
    TUYỆT ĐỐI KHÔNG GHI PIN VÀO LOG.
    """
    new_pin = f"{secrets.randbelow(900000) + 100000}"
    set_setting("lan_pin", new_pin)
    revoke_all_sessions()
    return new_pin
