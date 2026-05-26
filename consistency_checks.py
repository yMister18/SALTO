from __future__ import annotations

from pathlib import Path


def validate_attempt_state_payload(state) -> list[str]:
    issues: list[str] = []

    if state.attempt_db_id is None and state.attempt_dir is not None:
        issues.append("attempt_dir definido sem attempt_db_id")

    if state.selected_frame_bgr is None:
        if state.selected_frame_index is not None or state.selected_frame_timestamp is not None:
            issues.append("metadados de frame definidos sem frame selecionado")

    if (state.clicked_point_px is None) != (state.final_point_px is None):
        issues.append("pontos inconsistentes: clicked/final não estão alinhados")

    if state.distance_cm is not None and state.final_point_px is None:
        issues.append("medição definida sem ponto final")

    return issues


def validate_attempt_dir_minimal(attempt_dir: str | Path | None) -> list[str]:
    issues: list[str] = []
    if attempt_dir is None:
        return issues

    path = Path(attempt_dir)
    if not path.exists():
        issues.append(f"attempt_dir inexistente: {path}")
        return issues

    if not path.is_dir():
        issues.append(f"attempt_dir não é diretoria: {path}")
        return issues

    return issues