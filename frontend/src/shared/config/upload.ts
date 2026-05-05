const DEFAULT_MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024;

function parseUploadSizeLimit(value: string | undefined) {
  if (!value) {
    return DEFAULT_MAX_UPLOAD_SIZE_BYTES;
  }

  const parsedValue = Number(value);
  if (!Number.isFinite(parsedValue) || parsedValue <= 0) {
    return DEFAULT_MAX_UPLOAD_SIZE_BYTES;
  }

  return Math.floor(parsedValue);
}

export const MAX_UPLOAD_SIZE_BYTES = parseUploadSizeLimit(
  process.env.NEXT_PUBLIC_MAX_UPLOAD_SIZE_BYTES,
);
