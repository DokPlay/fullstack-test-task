from __future__ import annotations

from pathlib import Path

import pytest

from src.core.storage import LocalFileStorage


def test_storage_rejects_paths_outside_root(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "storage")

    with pytest.raises(ValueError, match="outside storage root"):
        storage.resolve("../outside.txt")


@pytest.mark.asyncio
async def test_text_metadata_replaces_invalid_utf8_bytes(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "storage")
    storage.root_dir.mkdir(parents=True)
    stored_path = storage.root_dir / "broken.txt"
    stored_path.write_bytes(b"a\xffb\n")

    metadata = await storage.collect_metadata(
        stored_name="broken.txt",
        original_name="broken.txt",
        mime_type="text/plain",
        size=4,
    )

    assert metadata["line_count"] == 1
    assert metadata["char_count"] == 4
