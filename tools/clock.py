from datetime import datetime
from zoneinfo import ZoneInfo

from tools.registry import tool


@tool
def current_time(timezone: str = "UTC") -> str:
    """Get the current date and time in an IANA timezone.

    Args:
        timezone: IANA timezone name, such as Asia/Kolkata.
    """
    return datetime.now(ZoneInfo(timezone)).isoformat()
