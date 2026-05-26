from __future__ import annotations

from pathlib import Path


class IntegrityManager:
    def inspect_attempt_dir(self, attempt_dir: str | Path) -> dict:
        base = Path(attempt_dir)

        expected_files = {
            "measurement_json": base / "measurement.json",
            "manifest_json": base / "manifest.json",
            "attempt_report": base / "attempt_report.txt",
            "frame_original": base / "frame_original.png",
            "frame_annotated": base / "frame_annotated.png",
            "video_dir": base / "video",
        }

        result = {
            "attempt_dir": str(base),
            "exists": base.exists(),
            "is_dir": base.is_dir(),
            "files": {},
            "missing": [],
            "warnings": [],
        }

        if not base.exists():
            result["warnings"].append("Diretório da tentativa não existe.")
            return result

        if not base.is_dir():
            result["warnings"].append("O caminho da tentativa não é uma diretoria.")
            return result

        for key, path in expected_files.items():
            exists = path.exists()
            result["files"][key] = {
                "path": str(path),
                "exists": exists,
                "is_dir": path.is_dir() if exists else False,
            }
            if not exists:
                result["missing"].append(key)

        video_dir = expected_files["video_dir"]
        if video_dir.exists() and video_dir.is_dir():
            video_files = [str(p) for p in video_dir.glob("*") if p.is_file()]
            result["files"]["video_dir"]["entries"] = video_files
            if not video_files:
                result["warnings"].append("Diretório de vídeo existe mas não contém ficheiros.")
        else:
            result["warnings"].append("Diretório de vídeo indisponível.")

        return result