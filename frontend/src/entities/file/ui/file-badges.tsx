import Badge from "react-bootstrap/Badge";

import type {
  FileItem,
  ProcessingStatus,
} from "@/entities/file/model/types";
import {
  getFileStatusMeta,
  getScanStatusMeta,
} from "@/entities/file/lib/status";

function getTextClass(variant: string) {
  return variant === "warning" ? "text-dark" : undefined;
}

type FileStatusBadgeProps = {
  status: ProcessingStatus;
};

export function FileStatusBadge({ status }: FileStatusBadgeProps) {
  const meta = getFileStatusMeta(status);

  return (
    <Badge bg={meta.variant} className={getTextClass(meta.variant)}>
      {meta.label}
    </Badge>
  );
}

type FileScanBadgeProps = {
  file: FileItem;
};

export function FileScanBadge({ file }: FileScanBadgeProps) {
  const meta = getScanStatusMeta(file);

  return (
    <Badge bg={meta.variant} className={getTextClass(meta.variant)}>
      {meta.label}
    </Badge>
  );
}
