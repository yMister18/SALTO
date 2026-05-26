from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SessionStateManager:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.base_dir / "session_state.json"

    def save(self, payload: dict[str, Any]) -> Path:
        self.state_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return self.state_path

    def load(self) -> dict[str, Any] | None:
        if not self.state_path.exists():
            return None
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def clear(self) -> None:
        if self.state_path.exists():
            self.state_path.unlink()