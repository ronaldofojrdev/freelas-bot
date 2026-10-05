import json
import os
from datetime import datetime

import config


def load_seen():
    if not os.path.exists(config.STATE_FILE):
        return {}
    with open(config.STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_seen(seen):
    os.makedirs(os.path.dirname(config.STATE_FILE), exist_ok=True)
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def mark_seen(seen, project_id, status, reason=""):
    seen[str(project_id)] = {
        "status": status,
        "reason": reason,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
