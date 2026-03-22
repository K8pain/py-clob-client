from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Mapping


class CsvStore:
    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write_rows(self, relative_path: str | Path, rows: Iterable[Mapping[str, object]]) -> Path:
        rows = list(rows)
        path = self.base_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.touch()
            return path
        fieldnames = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def append_rows(self, relative_path: str | Path, rows: Iterable[Mapping[str, object]], unique_by: tuple[str, ...] = ()) -> Path:
        incoming = list(rows)
        path = self.base_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.read_rows(relative_path) if path.exists() and path.stat().st_size else []
        if unique_by:
            seen = {tuple(row[key] for key in unique_by) for row in existing}
            filtered = []
            for row in incoming:
                key = tuple(row[key] for key in unique_by)
                if key not in seen:
                    filtered.append(row)
                    seen.add(key)
            incoming = filtered
        combined = existing + incoming
        if combined:
            self.write_rows(relative_path, combined)
        else:
            path.touch()
        return path

    def read_rows(self, relative_path: str | Path) -> list[dict[str, str]]:
        path = self.base_dir / relative_path
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
