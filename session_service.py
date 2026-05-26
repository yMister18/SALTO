from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

class SessionService:
    """
    Serviço para persistir e restaurar o estado da sessão da app
    (e.g., tentativa aberta, atleta, diretório, informações mínimas).
    """

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.state_path = self.base_dir / "session_state.json"

    def save_state(self, state: dict) -> Path:
        """
        Guarda o dicionário de estado para restauro posterior.
        """
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return self.state_path

    def load_state(self) -> Optional[dict]:
        """
        Lê e devolve o dicionário do último estado, ou None.
        """
        if not self.state_path.exists():
            return None
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def clear_state(self) -> None:
        if self.state_path.exists():
            self.state_path.unlink()

    def try_restore_attempt(
        self,
        detail_loader: Callable[[int], Optional[dict]],
        on_restore: Callable[[dict], None],
        on_ignore: Optional[Callable[[], None]] = None,
        ask_restore: Optional[Callable[[int], bool]] = None,
        log: Optional[Callable[[str], None]] = None,
    ):
        """
        detail_loader: função detail_loader(attempt_id) → dict ou None (deve devolver o attempt_detail)
        on_restore: callback com detail se restauro
        on_ignore: callback se utilizador recusar
        ask_restore: função(LastAttemptId) → bool, se None assume sempre "Yes"
        log: função de logging se existir
        """
        payload = self.load_state()
        if not payload:
            if log: log("Sem sessão anterior para restaurar.")
            return

        last_attempt_id = payload.get("last_attempt_id")
        if last_attempt_id is None:
            if log: log("Sessão anterior sem tentativa associada.")
            return

        aceitar = True
        if ask_restore:
            aceitar = ask_restore(last_attempt_id)
        if not aceitar:
            if log: log("Restauro de sessão ignorado pelo utilizador.")
            if on_ignore:
                on_ignore()
            return

        detail = detail_loader(int(last_attempt_id))
        if detail is None:
            if log: log(f"Tentativa anterior não encontrada na BD: {last_attempt_id}")
            return
        on_restore(detail)
        if log: log(f"Sessão restaurada: {last_attempt_id}")
