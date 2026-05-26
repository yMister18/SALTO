from __future__ import annotations

from pathlib import Path

from consistency_checks import validate_attempt_dir_minimal, validate_attempt_state_payload
from ui.models import AttemptRuntimeState


def test_attempt_state_valid_empty():
    state = AttemptRuntimeState()
    issues = validate_attempt_state_payload(state)
    assert issues == []


def test_attempt_state_invalid_dir_without_db():
    state = AttemptRuntimeState(attempt_dir=Path("/tmp/fake_attempt"))
    issues = validate_attempt_state_payload(state)
    assert "attempt_dir definido sem attempt_db_id" in issues


def test_attempt_state_invalid_frame_metadata_without_frame():
    state = AttemptRuntimeState(selected_frame_index=10, selected_frame_timestamp=1.23)
    issues = validate_attempt_state_payload(state)
    assert "metadados de frame definidos sem frame selecionado" in issues


def test_attempt_state_invalid_partial_points():
    state = AttemptRuntimeState(clicked_point_px=(10, 20), final_point_px=None)
    issues = validate_attempt_state_payload(state)
    assert "pontos inconsistentes: clicked/final não estão alinhados" in issues


def test_attempt_state_invalid_measurement_without_final_point():
    state = AttemptRuntimeState(distance_cm=123.4, final_point_px=None)
    issues = validate_attempt_state_payload(state)
    assert "medição definida sem ponto final" in issues


def test_validate_attempt_dir_none():
    issues = validate_attempt_dir_minimal(None)
    assert issues == []


def test_validate_attempt_dir_missing(tmp_path: Path):
    missing = tmp_path / "missing_attempt"
    issues = validate_attempt_dir_minimal(missing)
    assert len(issues) == 1
    assert "attempt_dir inexistente" in issues[0]


def test_validate_attempt_dir_not_directory(tmp_path: Path):
    file_path = tmp_path / "attempt.txt"
    file_path.write_text("x", encoding="utf-8")
    issues = validate_attempt_dir_minimal(file_path)
    assert len(issues) == 1
    assert "attempt_dir não é diretoria" in issues[0]


def test_validate_attempt_dir_ok(tmp_path: Path):
    attempt_dir = tmp_path / "attempt_001"
    attempt_dir.mkdir()
    issues = validate_attempt_dir_minimal(attempt_dir)
    assert issues == []