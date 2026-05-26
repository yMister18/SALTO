from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CompetitionRecord:
    id: int
    name: str
    location: str
    event_date: str
    created_at: str


@dataclass(frozen=True)
class AthleteRecord:
    id: int
    athlete_name: str
    bib_number: str
    created_at: str


@dataclass(frozen=True)
class AttemptRecord:
    id: int
    competition_id: Optional[int]
    athlete_id: int
    attempt_dir: str
    analysis_camera_id: int
    frame_index: Optional[int]
    frame_timestamp: Optional[float]
    is_archived: bool
    created_at: str


@dataclass(frozen=True)
class MeasurementRecordDB:
    id: int
    attempt_id: int
    distance_cm: float
    world_point_x_cm: float
    world_point_y_cm: float
    projection_x_cm: float
    projection_y_cm: float
    clicked_point_x_px: int
    clicked_point_y_px: int
    final_point_x_px: int
    final_point_y_px: int
    measurement_json_path: str
    annotated_frame_path: str
    created_at: str


class DatabaseManager:
    def __init__(self, db_path: str | Path = "output/lap2go.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _initialize_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS competitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '',
                    event_date TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS athletes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    athlete_name TEXT NOT NULL,
                    bib_number TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(athlete_name, bib_number)
                );

                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    competition_id INTEGER NULL,
                    athlete_id INTEGER NOT NULL,
                    attempt_dir TEXT NOT NULL,
                    analysis_camera_id INTEGER NOT NULL,
                    frame_index INTEGER NULL,
                    frame_timestamp REAL NULL,
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE SET NULL,
                    FOREIGN KEY (athlete_id) REFERENCES athletes(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempt_id INTEGER NOT NULL UNIQUE,
                    distance_cm REAL NOT NULL,
                    world_point_x_cm REAL NOT NULL,
                    world_point_y_cm REAL NOT NULL,
                    projection_x_cm REAL NOT NULL,
                    projection_y_cm REAL NOT NULL,
                    clicked_point_x_px INTEGER NOT NULL,
                    clicked_point_y_px INTEGER NOT NULL,
                    final_point_x_px INTEGER NOT NULL,
                    final_point_y_px INTEGER NOT NULL,
                    measurement_json_path TEXT NOT NULL,
                    annotated_frame_path TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (attempt_id) REFERENCES attempts(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_athletes_name_bib
                    ON athletes(athlete_name, bib_number);

                CREATE INDEX IF NOT EXISTS idx_attempts_athlete_id
                    ON attempts(athlete_id);

                CREATE INDEX IF NOT EXISTS idx_attempts_competition_id
                    ON attempts(competition_id);

                CREATE INDEX IF NOT EXISTS idx_attempts_archived
                    ON attempts(is_archived);

                CREATE INDEX IF NOT EXISTS idx_measurements_distance
                    ON measurements(distance_cm);
                """
            )

            columns = [row["name"] for row in conn.execute("PRAGMA table_info(attempts)").fetchall()]
            if "is_archived" not in columns:
                conn.execute("ALTER TABLE attempts ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0")

    def upsert_athlete(self, athlete_name: str, bib_number: str) -> AthleteRecord:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO athletes (athlete_name, bib_number)
                VALUES (?, ?)
                ON CONFLICT(athlete_name, bib_number) DO NOTHING
                """,
                (athlete_name, bib_number),
            )

            row = conn.execute(
                """
                SELECT id, athlete_name, bib_number, created_at
                FROM athletes
                WHERE athlete_name = ? AND bib_number = ?
                """,
                (athlete_name, bib_number),
            ).fetchone()

        if row is None:
            raise RuntimeError("Falha ao criar ou obter atleta.")

        return AthleteRecord(
            id=row["id"],
            athlete_name=row["athlete_name"],
            bib_number=row["bib_number"],
            created_at=row["created_at"],
        )

    def get_athlete_by_id(self, athlete_id: int) -> Optional[AthleteRecord]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, athlete_name, bib_number, created_at
                FROM athletes
                WHERE id = ?
                """,
                (athlete_id,),
            ).fetchone()

        if row is None:
            return None

        return AthleteRecord(
            id=row["id"],
            athlete_name=row["athlete_name"],
            bib_number=row["bib_number"],
            created_at=row["created_at"],
        )

    def create_competition(
        self,
        name: str,
        location: str = "",
        event_date: str = "",
    ) -> CompetitionRecord:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO competitions (name, location, event_date)
                VALUES (?, ?, ?)
                """,
                (name, location, event_date),
            )
            competition_id = int(cursor.lastrowid)

            row = conn.execute(
                """
                SELECT id, name, location, event_date, created_at
                FROM competitions
                WHERE id = ?
                """,
                (competition_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("Falha ao criar competição.")

        return CompetitionRecord(
            id=row["id"],
            name=row["name"],
            location=row["location"],
            event_date=row["event_date"],
            created_at=row["created_at"],
        )

    def get_competitions(self) -> list[CompetitionRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, location, event_date, created_at
                FROM competitions
                ORDER BY id DESC
                """
            ).fetchall()

        return [
            CompetitionRecord(
                id=row["id"],
                name=row["name"],
                location=row["location"],
                event_date=row["event_date"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_competition_by_id(self, competition_id: int) -> Optional[CompetitionRecord]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, location, event_date, created_at
                FROM competitions
                WHERE id = ?
                """,
                (competition_id,),
            ).fetchone()

        if row is None:
            return None

        return CompetitionRecord(
            id=row["id"],
            name=row["name"],
            location=row["location"],
            event_date=row["event_date"],
            created_at=row["created_at"],
        )

    def create_attempt(
        self,
        athlete_id: int,
        attempt_dir: str,
        analysis_camera_id: int,
        competition_id: int | None = None,
        frame_index: int | None = None,
        frame_timestamp: float | None = None,
    ) -> AttemptRecord:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO attempts (
                    competition_id,
                    athlete_id,
                    attempt_dir,
                    analysis_camera_id,
                    frame_index,
                    frame_timestamp,
                    is_archived
                )
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    competition_id,
                    athlete_id,
                    attempt_dir,
                    analysis_camera_id,
                    frame_index,
                    frame_timestamp,
                ),
            )
            attempt_id = int(cursor.lastrowid)

            row = conn.execute(
                """
                SELECT id, competition_id, athlete_id, attempt_dir, analysis_camera_id,
                       frame_index, frame_timestamp, is_archived, created_at
                FROM attempts
                WHERE id = ?
                """,
                (attempt_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("Falha ao criar tentativa.")

        return AttemptRecord(
            id=row["id"],
            competition_id=row["competition_id"],
            athlete_id=row["athlete_id"],
            attempt_dir=row["attempt_dir"],
            analysis_camera_id=row["analysis_camera_id"],
            frame_index=row["frame_index"],
            frame_timestamp=row["frame_timestamp"],
            is_archived=bool(row["is_archived"]),
            created_at=row["created_at"],
        )

    def update_attempt_frame_selection(self, attempt_id: int, frame_index: int, frame_timestamp: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE attempts
                SET frame_index = ?, frame_timestamp = ?
                WHERE id = ?
                """,
                (frame_index, frame_timestamp, attempt_id),
            )

    def archive_attempt(self, attempt_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE attempts
                SET is_archived = 1
                WHERE id = ?
                """,
                (attempt_id,),
            )

    def unarchive_attempt(self, attempt_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE attempts
                SET is_archived = 0
                WHERE id = ?
                """,
                (attempt_id,),
            )

    def delete_attempt(self, attempt_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM attempts WHERE id = ?", (attempt_id,))

    def upsert_measurement(
        self,
        attempt_id: int,
        distance_cm: float,
        world_point_cm: tuple[float, float],
        projection_cm: tuple[float, float],
        clicked_point_px: tuple[int, int],
        final_point_px: tuple[int, int],
        measurement_json_path: str,
        annotated_frame_path: str,
    ) -> MeasurementRecordDB:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO measurements (
                    attempt_id,
                    distance_cm,
                    world_point_x_cm,
                    world_point_y_cm,
                    projection_x_cm,
                    projection_y_cm,
                    clicked_point_x_px,
                    clicked_point_y_px,
                    final_point_x_px,
                    final_point_y_px,
                    measurement_json_path,
                    annotated_frame_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(attempt_id) DO UPDATE SET
                    distance_cm = excluded.distance_cm,
                    world_point_x_cm = excluded.world_point_x_cm,
                    world_point_y_cm = excluded.world_point_y_cm,
                    projection_x_cm = excluded.projection_x_cm,
                    projection_y_cm = excluded.projection_y_cm,
                    clicked_point_x_px = excluded.clicked_point_x_px,
                    clicked_point_y_px = excluded.clicked_point_y_px,
                    final_point_x_px = excluded.final_point_x_px,
                    final_point_y_px = excluded.final_point_y_px,
                    measurement_json_path = excluded.measurement_json_path,
                    annotated_frame_path = excluded.annotated_frame_path
                """,
                (
                    attempt_id,
                    distance_cm,
                    world_point_cm[0],
                    world_point_cm[1],
                    projection_cm[0],
                    projection_cm[1],
                    clicked_point_px[0],
                    clicked_point_px[1],
                    final_point_px[0],
                    final_point_px[1],
                    measurement_json_path,
                    annotated_frame_path,
                ),
            )

            row = conn.execute(
                """
                SELECT id, attempt_id, distance_cm,
                       world_point_x_cm, world_point_y_cm,
                       projection_x_cm, projection_y_cm,
                       clicked_point_x_px, clicked_point_y_px,
                       final_point_x_px, final_point_y_px,
                       measurement_json_path, annotated_frame_path,
                       created_at
                FROM measurements
                WHERE attempt_id = ?
                """,
                (attempt_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("Falha ao criar ou atualizar medição.")

        return MeasurementRecordDB(
            id=row["id"],
            attempt_id=row["attempt_id"],
            distance_cm=row["distance_cm"],
            world_point_x_cm=row["world_point_x_cm"],
            world_point_y_cm=row["world_point_y_cm"],
            projection_x_cm=row["projection_x_cm"],
            projection_y_cm=row["projection_y_cm"],
            clicked_point_x_px=row["clicked_point_x_px"],
            clicked_point_y_px=row["clicked_point_y_px"],
            final_point_x_px=row["final_point_x_px"],
            final_point_y_px=row["final_point_y_px"],
            measurement_json_path=row["measurement_json_path"],
            annotated_frame_path=row["annotated_frame_path"],
            created_at=row["created_at"],
        )

    def search_athletes(self, name_query: str = "") -> list[AthleteRecord]:
        query = f"%{name_query.strip()}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, athlete_name, bib_number, created_at
                FROM athletes
                WHERE athlete_name LIKE ? OR bib_number LIKE ?
                ORDER BY athlete_name ASC, bib_number ASC
                """,
                (query, query),
            ).fetchall()

        return [
            AthleteRecord(
                id=row["id"],
                athlete_name=row["athlete_name"],
                bib_number=row["bib_number"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_attempts_with_measurements(self, include_archived: bool = False) -> list[dict]:
        with self.connect() as conn:
            sql = """
                SELECT
                    a.id AS attempt_id,
                    a.attempt_dir,
                    a.analysis_camera_id,
                    a.frame_index,
                    a.frame_timestamp,
                    a.is_archived,
                    a.created_at AS attempt_created_at,
                    ath.id AS athlete_id,
                    ath.athlete_name,
                    ath.bib_number,
                    c.id AS competition_id,
                    c.name AS competition_name,
                    m.distance_cm,
                    m.measurement_json_path,
                    m.annotated_frame_path
                FROM attempts a
                JOIN athletes ath ON ath.id = a.athlete_id
                LEFT JOIN competitions c ON c.id = a.competition_id
                LEFT JOIN measurements m ON m.attempt_id = a.id
            """
            if not include_archived:
                sql += " WHERE a.is_archived = 0 "
            sql += " ORDER BY a.id DESC "

            rows = conn.execute(sql).fetchall()

        return [dict(row) for row in rows]

    def get_attempt_detail(self, attempt_id: int) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    a.id AS attempt_id,
                    a.attempt_dir,
                    a.analysis_camera_id,
                    a.frame_index,
                    a.frame_timestamp,
                    a.is_archived,
                    a.created_at AS attempt_created_at,
                    ath.id AS athlete_id,
                    ath.athlete_name,
                    ath.bib_number,
                    c.id AS competition_id,
                    c.name AS competition_name,
                    c.location AS competition_location,
                    c.event_date AS competition_event_date,
                    m.id AS measurement_id,
                    m.distance_cm,
                    m.world_point_x_cm,
                    m.world_point_y_cm,
                    m.projection_x_cm,
                    m.projection_y_cm,
                    m.clicked_point_x_px,
                    m.clicked_point_y_px,
                    m.final_point_x_px,
                    m.final_point_y_px,
                    m.measurement_json_path,
                    m.annotated_frame_path,
                    m.created_at AS measurement_created_at
                FROM attempts a
                JOIN athletes ath ON ath.id = a.athlete_id
                LEFT JOIN competitions c ON c.id = a.competition_id
                LEFT JOIN measurements m ON m.attempt_id = a.id
                WHERE a.id = ?
                """,
                (attempt_id,),
            ).fetchone()

        return dict(row) if row is not None else None

    def get_athlete_summary(self, athlete_id: int) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    ath.id AS athlete_id,
                    ath.athlete_name,
                    ath.bib_number,
                    COUNT(a.id) AS attempt_count,
                    MIN(m.distance_cm) AS best_distance_cm,
                    MAX(m.distance_cm) AS worst_distance_cm,
                    AVG(m.distance_cm) AS avg_distance_cm
                FROM athletes ath
                LEFT JOIN attempts a ON a.athlete_id = ath.id AND a.is_archived = 0
                LEFT JOIN measurements m ON m.attempt_id = a.id
                WHERE ath.id = ?
                GROUP BY ath.id, ath.athlete_name, ath.bib_number
                """,
                (athlete_id,),
            ).fetchone()

        return dict(row) if row is not None else None