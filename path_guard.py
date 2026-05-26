from __future__ import annotations

from pathlib import Path


class PathGuard:
    def to_path(self, value: str | Path | None, label: str) -> Path:
        if value is None:
            raise RuntimeError(f"{label}: caminho não definido.")
        text = str(value).strip()
        if not text:
            raise RuntimeError(f"{label}: caminho vazio.")
        return Path(text)

    def require_exists(self, path: str | Path, label: str) -> Path:
        p = Path(path)
        if not p.exists():
            raise RuntimeError(f"{label}: caminho não existe: {p}")
        return p

    def require_dir(self, path: str | Path, label: str) -> Path:
        p = self.require_exists(path, label)
        if not p.is_dir():
            raise RuntimeError(f"{label}: esperado diretório, recebido: {p}")
        return p

    def require_file(self, path: str | Path, label: str) -> Path:
        p = self.require_exists(path, label)
        if not p.is_file():
            raise RuntimeError(f"{label}: esperado ficheiro, recebido: {p}")
        return p

    def ensure_parent_dir(self, path: str | Path, label: str) -> Path:
        p = self.to_path(path, label)
        parent = p.parent
        parent.mkdir(parents=True, exist_ok=True)
        return p