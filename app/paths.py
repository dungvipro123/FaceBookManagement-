import os
import sys
import shutil
from pathlib import Path

APP_NAME = "FBMonitorHunter"

def get_app_dir() -> Path:
    """Returns %APPDATA%/FBMonitorHunter (or ~/.fbmonitorhunter on non-Windows)."""
    appdata = os.getenv("APPDATA")
    if appdata:
        base = Path(appdata) / APP_NAME
    else:
        base = Path.home() / f".{APP_NAME.lower()}"
    
    base.mkdir(parents=True, exist_ok=True)
    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    return base

def get_db_path() -> Path:
    """
    Returns path to SQLite database.
    If the database does not exist in %APPDATA%/FBMonitorHunter/data/,
    and exists in current workspace directory, copies it to preserve historical data.
    """
    app_dir = get_app_dir()
    target_db = app_dir / "data" / "facebook_posts.db"
    
    if not target_db.exists():
        workspace_db = Path.cwd() / "facebook_posts.db"
        if workspace_db.exists():
            try:
                shutil.copy2(workspace_db, target_db)
            except Exception:
                pass
    return target_db

def get_log_dir() -> Path:
    """Returns path to logs directory."""
    return get_app_dir() / "logs"

def get_static_dir() -> Path:
    """
    Returns path to static web assets.
    Supports PyInstaller bundle (sys._MEIPASS) and workspace development mode.
    """
    if hasattr(sys, "_MEIPASS"):
        meipass_static = Path(sys._MEIPASS) / "ui" / "static"
        if meipass_static.exists():
            return meipass_static

    # Workspace fallback
    workspace_static = Path(__file__).resolve().parent.parent / "ui" / "static"
    workspace_static.mkdir(parents=True, exist_ok=True)
    return workspace_static
