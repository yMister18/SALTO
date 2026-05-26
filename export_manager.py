from __future__ import annotations

import csv
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable


class ExportManager:
    def export_rows_to_json(self, rows: list[dict], output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def export_rows_to_csv(self, rows: list[dict], output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        normalized_rows = [self._normalize_row(row) for row in rows]
        fieldnames = self._collect_fieldnames(normalized_rows)

        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in normalized_rows:
                writer.writerow(row)

        return path

    def build_export_filename(
        self,
        prefix: str,
        suffix: str,
        athlete_name: str | None = None,
        competition_name: str | None = None,
    ) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        parts = [prefix]

        if athlete_name:
            parts.append(self._slugify(athlete_name))
        if competition_name:
            parts.append(self._slugify(competition_name))

        parts.append(ts)
        return "_".join(parts) + suffix

    def export_attempt_package(self, attempt_dir: str | Path, output_zip_path: str | Path) -> Path:
        attempt_path = Path(attempt_dir)
        if not attempt_path.exists() or not attempt_path.is_dir():
            raise RuntimeError(f"Diretório de tentativa inválido: {attempt_path}")

        output_path = Path(output_zip_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in attempt_path.rglob("*"):
                if item.is_file():
                    zf.write(item, arcname=item.relative_to(attempt_path))

        return output_path

    def _normalize_row(self, row: dict) -> dict:
        normalized = {}
        for key, value in row.items():
            if isinstance(value, (list, tuple, dict)):
                normalized[key] = json.dumps(value, ensure_ascii=False)
            elif value is None:
                normalized[key] = ""
            else:
                normalized[key] = value
        return normalized

    def _collect_fieldnames(self, rows: Iterable[dict]) -> list[str]:
        keys: list[str] = []
        seen = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        return keys

    def _slugify(self, value: str) -> str:
        text = value.strip().lower()
        allowed = []
        for ch in text:
            if ch.isalnum():
                allowed.append(ch)
            elif ch in {" ", "-", "_"}:
                allowed.append("_")
        result = "".join(allowed)
        while "__" in result:
            result = result.replace("__", "_")
        return result.strip("_") or "item"