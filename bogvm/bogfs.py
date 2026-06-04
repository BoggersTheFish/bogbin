from __future__ import annotations

from pathlib import Path

from .archive import ArchiveError, read_archive_file, read_archive_manifest


class BogFS:
    """Read-only filesystem-like view over a BOG directory archive."""

    def __init__(self, archive_dir: str | Path) -> None:
        self.archive_dir = Path(archive_dir)
        self.manifest = read_archive_manifest(self.archive_dir)
        self._entries = {entry["path"]: entry for entry in self.manifest["files"]}

    def listdir(self, prefix: str = "") -> list[str]:
        prefix = prefix.strip("/")
        if prefix:
            prefix = f"{prefix}/"
        names = set()
        for path in self._entries:
            if not path.startswith(prefix):
                continue
            rest = path[len(prefix):]
            names.add(rest.split("/", 1)[0])
        return sorted(names)

    def stat(self, path: str) -> dict:
        path = path.strip("/")
        entry = self._entries.get(path)
        if entry is None:
            raise ArchiveError(f"file not found in archive: {path}")
        return {
            "path": entry["path"],
            "size": entry["size"],
            "sha256": entry["sha256"],
        }

    def read_bytes(self, path: str) -> bytes:
        return read_archive_file(self.archive_dir, path.strip("/"), manifest=self.manifest)

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding)
