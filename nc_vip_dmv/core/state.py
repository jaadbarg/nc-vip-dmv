from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Set


class StateStore:
    def __init__(self, path: str | Path, ttl_hours: int = 12) -> None:
        self.path = Path(path)
        self.ttl_seconds = ttl_hours * 3600
        self._data = {
            "seen": {},  # office_name -> {signature: last_time}
        }
        self._loaded_at = time.time()
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                # Corrupt or unreadable; start fresh
                self._data = {"seen": {}}
        else:
            self._data = {"seen": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def purge_expired(self) -> None:
        now = time.time()
        seen = self._data.get("seen", {})
        for office, sig_to_ts in list(seen.items()):
            filtered = {sig: ts for sig, ts in sig_to_ts.items() if now - ts <= self.ttl_seconds}
            if filtered:
                seen[office] = filtered
            else:
                seen.pop(office, None)
        self._data["seen"] = seen
        self._save()

    def was_seen(self, office_name: str, signature: str) -> bool:
        sigs: Dict[str, float] = self._data["seen"].get(office_name, {})
        return signature in sigs

    def mark_seen(self, office_name: str, signature: str) -> None:
        now = time.time()
        sigs: Dict[str, float] = self._data["seen"].setdefault(office_name, {})
        sigs[signature] = now
        self._save()
