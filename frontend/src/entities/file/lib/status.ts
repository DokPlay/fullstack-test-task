import {
  PROCESSING_STATUSES,
  SCAN_STATUSES,
  type FileItem,
  type ProcessingStatus,
} from "@/entities/file/model/types";

const pendingStatuses = new Set<ProcessingStatus>([
  PROCESSING_STATUSES.UPLOADED,
  PROCESSING_STATUSES.PROCESSING,
]);

export function isFilePending(file: FileItem) {
  return pendingStatuses.has(file.processing_status);
}

export function getFileStatusMeta(status: ProcessingStatus) {
  if (status === PROCESSING_STATUSES.FAILED) {
    return { label: "Ошибка", variant: "danger" };
  }

  if (status === PROCESSING_STATUSES.PROCESSING) {
    return { label: "В обработке", variant: "warning" };
  }

  if (status === PROCESSING_STATUSES.PROCESSED) {
    return { label: "Готово", variant: "success" };
  }

  if (status === PROCESSING_STATUSES.UPLOADED) {
    return { label: "В очереди", variant: "secondary" };
  }

  const unreachableStatus: never = status;

  return { label: unreachableStatus, variant: "secondary" };
}

export function getScanStatusMeta(file: FileItem) {
  if (file.scan_status === SCAN_STATUSES.FAILED) {
    return { label: "Ошибка", variant: "danger" };
  }

  if (file.scan_status === SCAN_STATUSES.SUSPICIOUS || file.requires_attention) {
    return { label: "Требует внимания", variant: "warning" };
  }

  if (file.scan_status === SCAN_STATUSES.CLEAN) {
    return { label: "Чисто", variant: "success" };
  }

  return { label: "Ожидает проверки", variant: "secondary" };
}
