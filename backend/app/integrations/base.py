from typing import Optional, Any
from app.config import settings


class BaseIntegration:
    """Base class for all external API integrations."""
    
    name: str = "base"
    requires_api_key: bool = False
    api_key_setting: str = ""
    fallback_enabled: bool = True

    @classmethod
    def is_available(cls) -> bool:
        if not cls.requires_api_key:
            return True
        key = getattr(settings, cls.api_key_setting, "")
        return bool(key)

    @classmethod
    def get_status(cls) -> dict:
        return {
            "name": cls.name,
            "available": cls.is_available(),
            "requires_api_key": cls.requires_api_key,
            "fallback_enabled": cls.fallback_enabled,
        }
