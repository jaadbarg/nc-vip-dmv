from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class Subscription:
    email: str
    offices: List[str]


class SubscriptionsStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._data: Dict[str, List[str]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))

    def list_emails(self) -> List[str]:
        return sorted(self._data.keys())

    def get_offices_for(self, email: str) -> List[str]:
        return self._data.get(email, [])

    def set_subscription(self, email: str, offices: List[str]) -> None:
        self._data[email] = sorted(set(offices))
        self._save()

    def remove(self, email: str) -> None:
        if email in self._data:
            self._data.pop(email)
            self._save()
