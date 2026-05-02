export const PROCESSING_STATUSES = {
  UPLOADED: "uploaded",
  PROCESSING: "processing",
  PROCESSED: "processed",
  FAILED: "failed",
} as const;

export type ProcessingStatus =
  (typeof PROCESSING_STATUSES)[keyof typeof PROCESSING_STATUSES];

export const SCAN_STATUSES = {
  CLEAN: "clean",
  SUSPICIOUS: "suspicious",
  FAILED: "failed",
} as const;

export type ScanStatus =
  | (typeof SCAN_STATUSES)[keyof typeof SCAN_STATUSES]
  | null;

export type FileItem = {
  id: string;
  title: string;
  original_name: string;
  mime_type: string;
  size: number;
  processing_status: ProcessingStatus;
  scan_status: ScanStatus;
  scan_details: string | null;
  metadata_json: Record<string, unknown> | null;
  requires_attention: boolean;
  created_at: string;
  updated_at: string;
};
