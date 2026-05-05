from __future__ import annotations

from prometheus_client import Counter, Gauge


file_upload_total = Counter(
    "file_upload_total",
    "Number of files accepted by the upload endpoint.",
)
file_scan_total = Counter(
    "file_scan_total",
    "Number of files successfully scanned during processing.",
)
file_scan_suspicious_total = Counter(
    "file_scan_suspicious_total",
    "Number of files marked suspicious.",
)
active_processing_files = Gauge(
    "file_processing_active",
    "Number of files currently in processing.",
)


def count_uploaded_file() -> None:
    file_upload_total.inc()


def count_scanned_file() -> None:
    file_scan_total.inc()


def count_suspicious_file() -> None:
    file_scan_suspicious_total.inc()


def add_active_processing(delta: int) -> None:
    active_processing_files.inc(delta)
