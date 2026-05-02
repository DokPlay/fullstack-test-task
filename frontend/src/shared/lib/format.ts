export function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatFileSize(size: number) {
  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatShortId(value: string) {
  if (value.length <= 14) {
    return value;
  }

  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}

export function getMetadataSummary(metadata: Record<string, unknown> | null) {
  if (!metadata) {
    return [];
  }

  const summary: string[] = [];

  if (typeof metadata.extension === "string" && metadata.extension) {
    summary.push(metadata.extension.toUpperCase());
  }

  if (typeof metadata.line_count === "number") {
    summary.push(`${metadata.line_count} lines`);
  }

  if (typeof metadata.char_count === "number") {
    summary.push(`${metadata.char_count} chars`);
  }

  if (typeof metadata.approx_page_count === "number") {
    summary.push(`${metadata.approx_page_count} pages`);
  }

  return summary;
}
