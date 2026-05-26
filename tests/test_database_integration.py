from __future__ import annotations

from pathlib import Path

from database import DatabaseManager


def test_database_attempt_measurement_flow(tmp_path: Path):
    db_path = tmp_path / "lap2go_test.db"
    db = DatabaseManager(db_path)

    athlete = db.upsert_athlete("Ana Costa", "207")
    assert athlete.id > 0
    assert athlete.athlete_name == "Ana Costa"
    assert athlete.bib_number == "207"

    competition = db.create_competition(
        name="Torneio Porto",
        location="Porto",
        event_date="2026-05-15",
    )
    assert competition.id > 0
    assert competition.name == "Torneio Porto"

    attempt = db.create_attempt(
        athlete_id=athlete.id,
        competition_id=competition.id,
        attempt_dir=str(tmp_path / "attempt_001"),
        analysis_camera_id=0,
    )
    assert attempt.id > 0
    assert attempt.athlete_id == athlete.id
    assert attempt.competition_id == competition.id

    db.update_attempt_frame_selection(
        attempt_id=attempt.id,
        frame_index=18,
        frame_timestamp=1715780000.45,
    )

    measurement = db.upsert_measurement(
        attempt_id=attempt.id,
        distance_cm=512.73,
        world_point_cm=(101.2, 512.73),
        projection_cm=(101.2, 0.0),
        clicked_point_px=(944, 530),
        final_point_px=(950, 536),
        measurement_json_path=str(tmp_path / "measurement.json"),
        annotated_frame_path=str(tmp_path / "frame_annotated.png"),
    )

    assert measurement.id > 0
    assert measurement.attempt_id == attempt.id
    assert abs(measurement.distance_cm - 512.73) < 1e-9
    assert measurement.final_point_x_px == 950
    assert measurement.final_point_y_px == 536

    detail = db.get_attempt_detail(attempt.id)
    assert detail is not None
    assert detail["attempt_id"] == attempt.id
    assert detail["athlete_name"] == "Ana Costa"
    assert detail["bib_number"] == "207"
    assert detail["competition_name"] == "Torneio Porto"
    assert detail["frame_index"] == 18
    assert abs(detail["frame_timestamp"] - 1715780000.45) < 1e-9
    assert abs(detail["distance_cm"] - 512.73) < 1e-9

    rows = db.get_attempts_with_measurements()
    assert len(rows) == 1
    assert rows[0]["attempt_id"] == attempt.id
    assert rows[0]["athlete_name"] == "Ana Costa"
    assert abs(rows[0]["distance_cm"] - 512.73) < 1e-9


def test_database_upsert_athlete_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "lap2go_test.db"
    db = DatabaseManager(db_path)

    athlete1 = db.upsert_athlete("João Silva", "123")
    athlete2 = db.upsert_athlete("João Silva", "123")

    assert athlete1.id == athlete2.id
    assert athlete1.athlete_name == athlete2.athlete_name
    assert athlete1.bib_number == athlete2.bib_number

    athletes = db.search_athletes("João")
    assert len(athletes) == 1
    assert athletes[0].id == athlete1.id


def test_database_measurement_upsert_updates_existing_attempt(tmp_path: Path):
    db_path = tmp_path / "lap2go_test.db"
    db = DatabaseManager(db_path)

    athlete = db.upsert_athlete("Maria Lopes", "88")
    attempt = db.create_attempt(
        athlete_id=athlete.id,
        competition_id=None,
        attempt_dir=str(tmp_path / "attempt_002"),
        analysis_camera_id=1,
    )

    m1 = db.upsert_measurement(
        attempt_id=attempt.id,
        distance_cm=400.0,
        world_point_cm=(50.0, 400.0),
        projection_cm=(50.0, 0.0),
        clicked_point_px=(100, 200),
        final_point_px=(105, 205),
        measurement_json_path=str(tmp_path / "m1.json"),
        annotated_frame_path=str(tmp_path / "a1.png"),
    )

    m2 = db.upsert_measurement(
        attempt_id=attempt.id,
        distance_cm=405.5,
        world_point_cm=(55.0, 405.5),
        projection_cm=(55.0, 0.0),
        clicked_point_px=(110, 210),
        final_point_px=(112, 214),
        measurement_json_path=str(tmp_path / "m2.json"),
        annotated_frame_path=str(tmp_path / "a2.png"),
    )

    assert m1.id == m2.id
    assert abs(m2.distance_cm - 405.5) < 1e-9
    assert m2.clicked_point_x_px == 110
    assert m2.clicked_point_y_px == 210
    assert m2.final_point_x_px == 112
    assert m2.final_point_y_px == 214
    assert m2.measurement_json_path.endswith("m2.json")
    assert m2.annotated_frame_path.endswith("a2.png")

    detail = db.get_attempt_detail(attempt.id)
    assert detail is not None
    assert abs(detail["distance_cm"] - 405.5) < 1e-9
    assert detail["clicked_point_x_px"] == 110
    assert detail["final_point_x_px"] == 112


def test_database_athlete_summary(tmp_path: Path):
    db_path = tmp_path / "lap2go_test.db"
    db = DatabaseManager(db_path)

    athlete = db.upsert_athlete("Carlos Neto", "44")

    attempt1 = db.create_attempt(
        athlete_id=athlete.id,
        competition_id=None,
        attempt_dir=str(tmp_path / "a1"),
        analysis_camera_id=0,
    )
    attempt2 = db.create_attempt(
        athlete_id=athlete.id,
        competition_id=None,
        attempt_dir=str(tmp_path / "a2"),
        analysis_camera_id=0,
    )

    db.upsert_measurement(
        attempt_id=attempt1.id,
        distance_cm=600.0,
        world_point_cm=(120.0, 600.0),
        projection_cm=(120.0, 0.0),
        clicked_point_px=(10, 20),
        final_point_px=(11, 21),
        measurement_json_path=str(tmp_path / "m1.json"),
        annotated_frame_path=str(tmp_path / "f1.png"),
    )
    db.upsert_measurement(
        attempt_id=attempt2.id,
        distance_cm=650.0,
        world_point_cm=(125.0, 650.0),
        projection_cm=(125.0, 0.0),
        clicked_point_px=(12, 22),
        final_point_px=(13, 23),
        measurement_json_path=str(tmp_path / "m2.json"),
        annotated_frame_path=str(tmp_path / "f2.png"),
    )

    summary = db.get_athlete_summary(athlete.id)
    assert summary is not None
    assert summary["athlete_id"] == athlete.id
    assert summary["athlete_name"] == "Carlos Neto"
    assert summary["bib_number"] == "44"
    assert summary["attempt_count"] == 2
    assert abs(summary["best_distance_cm"] - 600.0) < 1e-9
    assert abs(summary["worst_distance_cm"] - 650.0) < 1e-9
    assert abs(summary["avg_distance_cm"] - 625.0) < 1e-9