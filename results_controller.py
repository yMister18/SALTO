from __future__ import annotations

from typing import Callable, Optional

from database import DatabaseManager
from export_manager import ExportManager


class ResultsController:
    """
    Orquestra pesquisa/abertura/arquivo/desarquivação/eliminação/exportação de resultados de tentativas.
    Chama callbacks para notificar MainWindow/UI.
    """

    def __init__(
        self,
        database_manager: DatabaseManager,
        export_manager: ExportManager,
        state_updated_cb: Optional[Callable[[list[dict]], None]] = None,
    ):
        self.database_manager = database_manager
        self.export_manager = export_manager
        self.state_updated_cb = state_updated_cb  # Chamada com lista dos resultados filtrados
        self._filtered_rows: list[dict] = []

    def refresh_results(
        self,
        query: str = "",
        competition_filter_id: Optional[int] = None,
        sort_mode: str = "recent_desc",
        include_archived: bool = False,
    ) -> list[dict]:
        rows = self.database_manager.get_attempts_with_measurements(include_archived=include_archived)

        if query:
            query = query.lower()
            rows = [
                row for row in rows
                if query in str(row.get("athlete_name", "")).lower() or
                   query in str(row.get("bib_number", "")).lower()
            ]
        if competition_filter_id is not None:
            rows = [row for row in rows if row.get("competition_id") == competition_filter_id]

        def distance_key(row: dict) -> float:
            value = row.get("distance_cm")
            return float(value) if value is not None else -1.0

        if sort_mode == "recent_desc":
            rows.sort(key=lambda r: str(r.get("attempt_created_at", "")), reverse=True)
        elif sort_mode == "recent_asc":
            rows.sort(key=lambda r: str(r.get("attempt_created_at", "")))
        elif sort_mode == "distance_desc":
            rows.sort(key=distance_key, reverse=True)
        elif sort_mode == "distance_asc":
            rows.sort(key=lambda r: (distance_key(r) if r.get("distance_cm") is not None else 10**12))
        elif sort_mode == "athlete_asc":
            rows.sort(key=lambda r: (str(r.get("athlete_name", "")).lower(), str(r.get("bib_number", "")).lower()))

        self._filtered_rows = rows
        if self.state_updated_cb:
            self.state_updated_cb(rows)
        return rows

    def open_attempt(self, attempt_id: int) -> Optional[dict]:
        """
        Busca os detalhes da tentativa na BD.
        """
        return self.database_manager.get_attempt_detail(attempt_id)

    def archive_attempt(self, attempt_id: int) -> None:
        self.database_manager.archive_attempt(attempt_id)

    def unarchive_attempt(self, attempt_id: int) -> None:
        self.database_manager.unarchive_attempt(attempt_id)

    def delete_attempt(self, attempt_id: int) -> None:
        self.database_manager.delete_attempt(attempt_id)

    def get_filtered_attempts(self) -> list[dict]:
        return list(self._filtered_rows)

    def export_filtered_to_csv(self, output_path) -> None:
        rows = self.get_filtered_attempts()
        self.export_manager.export_rows_to_csv(rows, output_path)

    def export_filtered_to_json(self, output_path) -> None:
        rows = self.get_filtered_attempts()
        self.export_manager.export_rows_to_json(rows, output_path)