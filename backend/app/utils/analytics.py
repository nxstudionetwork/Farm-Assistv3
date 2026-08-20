import json
import os
from datetime import datetime
from typing import Optional
from pathlib import Path


class AnalyticsTracker:
    def __init__(self, log_dir: str = "analytics_logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _log(self, event_type: str, data: dict):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            **data,
        }
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = self.log_dir / f"{date_str}.jsonl"
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def track_login(self, user_id: str, method: str, success: bool):
        self._log("login", {"user_id": user_id, "method": method, "success": success})

    def track_api_call(self, user_id: Optional[str], endpoint: str, method: str, status_code: int):
        self._log("api_call", {"user_id": user_id or "anonymous", "endpoint": endpoint, "method": method, "status": status_code})

    def track_ai_usage(self, user_id: str, model: str, tokens: Optional[int] = None):
        self._log("ai_usage", {"user_id": user_id, "model": model, "tokens": tokens})

    def track_error(self, user_id: Optional[str], error_type: str, endpoint: str, detail: str):
        self._log("error", {"user_id": user_id or "anonymous", "error_type": error_type, "endpoint": endpoint, "detail": detail[:200]})

    def track_booking(self, user_id: str, booking_type: str, booking_id: str, amount: float):
        self._log("booking", {"user_id": user_id, "type": booking_type, "booking_id": booking_id, "amount": amount})


analytics = AnalyticsTracker()
