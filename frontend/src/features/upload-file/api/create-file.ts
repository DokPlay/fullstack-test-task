import type { FileItem } from "@/entities/file/model/types";
import { readApiErrorText } from "@/shared/api/http";
import { apiRoutes } from "@/shared/config/api";
import { MAX_UPLOAD_SIZE_BYTES } from "@/shared/config/upload";
import { formatFileSize } from "@/shared/lib/format";

export type UploadProgress = {
  loadedBytes: number;
  totalBytes: number;
  percentage: number;
};

type CreateFilePayload = {
  title: string;
  file: File;
  signal?: AbortSignal;
  onProgress?: (progress: UploadProgress) => void;
};

export async function createFile({
  title,
  file,
  signal,
  onProgress,
}: CreateFilePayload) {
  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    throw new Error(
      `Файл слишком большой. Максимальный размер загрузки: ${formatFileSize(MAX_UPLOAD_SIZE_BYTES)}.`,
    );
  }

  const formData = new FormData();
  formData.append("title", title);
  formData.append("file", file);

  return new Promise<FileItem>((resolve, reject) => {
    const request = new XMLHttpRequest();
    let isSettled = false;

    function cleanup() {
      request.upload.onprogress = null;
      request.onload = null;
      request.onerror = null;
      request.onabort = null;
      signal?.removeEventListener("abort", abortUpload);
    }

    function resolveOnce(fileItem: FileItem) {
      if (isSettled) {
        return;
      }

      isSettled = true;
      cleanup();
      resolve(fileItem);
    }

    function rejectOnce(error: unknown) {
      if (isSettled) {
        return;
      }

      isSettled = true;
      cleanup();
      reject(error);
    }

    function abortUpload() {
      request.abort();
    }

    if (signal?.aborted) {
      rejectOnce(createAbortError());
      return;
    }

    signal?.addEventListener("abort", abortUpload, { once: true });
    reportProgress(onProgress, 0, file.size);

    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        return;
      }

      reportProgress(onProgress, event.loaded, event.total);
    };

    request.onload = () => {
      if (request.status < 200 || request.status >= 300) {
        rejectOnce(
          new Error(
            readApiErrorText(
              request.responseText,
              request.getResponseHeader("content-type"),
              "Не удалось загрузить файл",
            ),
          ),
        );
        return;
      }

      try {
        reportProgress(onProgress, file.size, file.size);
        resolveOnce(JSON.parse(request.responseText) as FileItem);
      } catch {
        rejectOnce(new Error("Не удалось прочитать ответ сервера"));
      }
    };

    request.onerror = () => {
      rejectOnce(new Error("Не удалось загрузить файл"));
    };

    request.onabort = () => {
      rejectOnce(createAbortError());
    };

    request.open("POST", apiRoutes.files);
    request.send(formData);
  });
}

function reportProgress(
  onProgress: CreateFilePayload["onProgress"],
  loadedBytes: number,
  totalBytes: number,
) {
  if (!onProgress) {
    return;
  }

  const safeTotalBytes = Math.max(totalBytes, 1);
  const percentage = Math.min(
    100,
    Math.max(0, Math.round((loadedBytes / safeTotalBytes) * 100)),
  );

  onProgress({
    loadedBytes,
    totalBytes,
    percentage,
  });
}

function createAbortError() {
  return new DOMException("Upload aborted", "AbortError");
}
