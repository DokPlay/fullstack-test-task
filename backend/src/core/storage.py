from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

import aiofiles
import aiofiles.os
import aiofiles.ospath
from fastapi import UploadFile


COPY_CHUNK_SIZE = 1024 * 1024
PDF_PAGE_MARKER = b"/Type /Page"


@dataclass(frozen=True, slots=True)
class StoredUpload:
    original_name: str
    stored_name: str
    mime_type: str
    size: int


class UploadSizeLimitExceededError(ValueError):
    def __init__(self, max_size_bytes: int):
        super().__init__(f"Upload exceeds maximum size of {max_size_bytes} bytes")
        self.max_size_bytes = max_size_bytes


class LocalFileStorage:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(
        self,
        upload_file: UploadFile,
        file_id: str,
        *,
        max_size_bytes: int,
    ) -> StoredUpload:
        original_name = Path(upload_file.filename or "").name or file_id
        stored_name = f"{file_id}{Path(original_name).suffix}"
        destination = self.resolve(stored_name)

        try:
            size = await self._copy_upload_file(
                upload_file,
                destination,
                max_size_bytes=max_size_bytes,
            )
        except Exception:
            if await aiofiles.ospath.exists(destination):
                await aiofiles.os.remove(destination)
            raise

        mime_type = upload_file.content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        return StoredUpload(
            original_name=original_name,
            stored_name=stored_name,
            mime_type=mime_type,
            size=size,
        )

    async def delete(self, stored_name: str) -> None:
        path = self.resolve(stored_name)
        if not await aiofiles.ospath.exists(path):
            return
        await aiofiles.os.remove(path)

    async def exists(self, stored_name: str) -> bool:
        return await aiofiles.ospath.exists(self.resolve(stored_name))

    async def stage_for_deletion(self, stored_name: str) -> Path | None:
        original_path = self.resolve(stored_name)
        if not await aiofiles.ospath.exists(original_path):
            return None

        staged_path = original_path.with_name(f".{original_path.name}.deleting")
        await aiofiles.os.rename(original_path, staged_path)
        return staged_path

    async def restore_after_failed_delete(self, staged_path: Path, stored_name: str) -> None:
        await aiofiles.os.rename(staged_path, self.resolve(stored_name))

    async def finalize_staged_delete(self, staged_path: Path | None) -> None:
        if staged_path is None or not await aiofiles.ospath.exists(staged_path):
            return
        await aiofiles.os.remove(staged_path)

    async def collect_metadata(
        self,
        *,
        stored_name: str,
        original_name: str,
        mime_type: str,
        size: int,
    ) -> dict[str, int | str]:
        path = self.resolve(stored_name)
        if not await aiofiles.ospath.exists(path):
            raise FileNotFoundError(stored_name)

        metadata: dict[str, int | str] = {
            "extension": Path(original_name).suffix.lower(),
            "size_bytes": size,
            "mime_type": mime_type,
        }

        if mime_type.startswith("text/"):
            metadata.update(await self._collect_text_statistics(path))
        elif mime_type == "application/pdf":
            metadata["approx_page_count"] = await self._estimate_pdf_pages(path)

        return metadata

    def resolve(self, stored_name: str) -> Path:
        resolved_path = (self.root_dir / stored_name).resolve()
        try:
            resolved_path.relative_to(self.root_dir)
        except ValueError as exc:
            raise ValueError(f"Resolved file path is outside storage root: {stored_name}") from exc
        return resolved_path

    @staticmethod
    async def _copy_upload_file(
        upload_file: UploadFile,
        destination: Path,
        *,
        max_size_bytes: int,
    ) -> int:
        await upload_file.seek(0)
        size = 0

        async with aiofiles.open(destination, "wb") as handle:
            while chunk := await upload_file.read(COPY_CHUNK_SIZE):
                next_size = size + len(chunk)
                if next_size > max_size_bytes:
                    raise UploadSizeLimitExceededError(max_size_bytes)
                await handle.write(chunk)
                size = next_size

        await upload_file.seek(0)
        return size

    @staticmethod
    async def _collect_text_statistics(path: Path) -> dict[str, int]:
        line_count = 0
        char_count = 0

        async with aiofiles.open(path, "r", encoding="utf-8", errors="replace") as handle:
            while line := await handle.readline():
                line_count += 1
                char_count += len(line)

        return {
            "line_count": line_count,
            "char_count": char_count,
        }

    @staticmethod
    async def _estimate_pdf_pages(path: Path) -> int:
        count = 0
        overlap = b""
        overlap_size = len(PDF_PAGE_MARKER) - 1

        async with aiofiles.open(path, "rb") as handle:
            while chunk := await handle.read(COPY_CHUNK_SIZE):
                payload = overlap + chunk
                count += payload.count(PDF_PAGE_MARKER)
                overlap = payload[-overlap_size:]

        return max(count, 1)
