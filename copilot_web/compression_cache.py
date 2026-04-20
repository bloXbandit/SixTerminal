"""
Compression cache module — stores user-uploaded compression PDF analysis.
Encrypted JSON-based persistent storage in a cache directory.
Uses crypto.py (Fernet/AES-128-CBC) when ENCRYPTION_KEY env var is set;
falls back to plain JSON in pass-through mode (local dev without a key).
"""
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Cache directory — same level as projects folder
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")


def _ensure_cache_dir():
    """Ensure cache directory exists."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)


def _get_cache_path(project_slug: str) -> str:
    """Get path to cache file for a project."""
    _ensure_cache_dir()
    return os.path.join(CACHE_DIR, f"{project_slug}_compression.json")


def _read_cache(cache_path: str) -> dict:
    """Read cache file, decrypting if ENCRYPTION_KEY is set. Returns {} on any error."""
    if not os.path.exists(cache_path):
        return {}
    try:
        from crypto import read_encrypted_json
        return read_encrypted_json(cache_path)
    except Exception as e:
        logger.error(f"[compression_cache] Failed to read cache {cache_path}: {e}")
        return {}


def _write_cache(cache_path: str, data: dict) -> None:
    """Write cache file, encrypting if ENCRYPTION_KEY is set."""
    from crypto import write_encrypted_json
    write_encrypted_json(cache_path, data)


def save_compression_data(project_slug: str, update_num: int, data: dict) -> bool:
    """
    Save compression data for a specific project update.
    
    Args:
        project_slug: e.g. 'anaheim_ca'
        update_num: e.g. 3
        data: dict with compression_pct, earlier_finish, later_finish, etc.
    
    Returns:
        True if saved successfully
    """
    try:
        cache_path = _get_cache_path(project_slug)
        
        # Load existing cache
        cache = _read_cache(cache_path)
        
        # Add/update this update's data
        cache[str(update_num)] = {
            "compression_pct": data.get("compression_pct"),
            "earlier_finish": data.get("earlier_finish"),
            "later_finish": data.get("later_finish"),
            "earlier_data_date": data.get("earlier_data_date"),
            "later_data_date": data.get("later_data_date"),
            "monthly": data.get("monthly", []),
            "raw_lines": data.get("raw_lines", [])[:50],  # Limit stored lines
            "filename": data.get("filename"),
            "uploaded_at": data.get("uploaded_at")
        }
        
        # Save back (encrypted)
        _write_cache(cache_path, cache)
        
        logger.info(f"[compression_cache] Saved update {update_num} for {project_slug}")
        return True
        
    except Exception as e:
        logger.error(f"[compression_cache] Failed to save: {e}")
        return False


def get_compression_for_update(project_slug: str, update_num: int) -> Optional[dict]:
    """
    Get cached compression data for a specific update.
    
    Args:
        project_slug: e.g. 'anaheim_ca'
        update_num: e.g. 3
    
    Returns:
        dict with compression data or None
    """
    try:
        cache_path = _get_cache_path(project_slug)
        
        cache = _read_cache(cache_path)
        return cache.get(str(update_num))
        
    except Exception as e:
        logger.error(f"[compression_cache] Failed to load: {e}")
        return None


def get_all_compression_for_project(project_slug: str) -> Dict[int, dict]:
    """
    Get all cached compression data for a project.
    
    Returns:
        Dict mapping update_num -> compression data
    """
    try:
        cache_path = _get_cache_path(project_slug)
        
        cache = _read_cache(cache_path)
        # Convert keys to int
        return {int(k): v for k, v in cache.items()}
        
    except Exception as e:
        logger.error(f"[compression_cache] Failed to load all: {e}")
        return {}


def has_compression_data(project_slug: str, update_num: int) -> bool:
    """Check if compression data exists for a specific update."""
    return get_compression_for_update(project_slug, update_num) is not None


def extract_update_number_from_filename(filename: str) -> Optional[int]:
    """
    Try to extract update number from filename like 'compression_update3.pdf'
    
    Returns:
        update number or None
    """
    import re
    patterns = [
        r'update[_\-]?(\d+)',
        r'compression[_\-]?(\d+)',
        r'(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None
