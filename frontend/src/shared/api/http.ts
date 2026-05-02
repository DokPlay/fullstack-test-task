type ApiErrorPayload = {
  detail?: string;
};

function isJsonContentType(contentType: string | null) {
  const normalizedContentType = contentType?.toLowerCase();

  return Boolean(
    normalizedContentType?.includes("application/json") ||
      normalizedContentType?.includes("+json"),
  );
}

function getApiErrorMessage(payload: ApiErrorPayload, fallbackMessage: string) {
  if (typeof payload.detail === "string" && payload.detail.trim()) {
    return payload.detail;
  }

  return fallbackMessage;
}

export function readApiErrorText(
  responseText: string,
  contentType: string | null,
  fallbackMessage: string,
) {
  if (!isJsonContentType(contentType)) {
    return fallbackMessage;
  }

  try {
    return getApiErrorMessage(
      JSON.parse(responseText) as ApiErrorPayload,
      fallbackMessage,
    );
  } catch {
    return fallbackMessage;
  }
}

export async function readApiError(
  response: Response,
  fallbackMessage: string,
) {
  if (!isJsonContentType(response.headers.get("content-type"))) {
    return fallbackMessage;
  }

  try {
    const payload = (await response.json()) as ApiErrorPayload;
    return getApiErrorMessage(payload, fallbackMessage);
  } catch {
    return fallbackMessage;
  }
}

export async function fetchJson<T>(
  input: RequestInfo | URL,
  init: RequestInit = {},
  fallbackMessage = "Не удалось выполнить запрос",
) {
  const response = await fetch(input, {
    ...init,
    cache: init.cache ?? "no-store",
  });

  if (!response.ok) {
    throw new Error(await readApiError(response, fallbackMessage));
  }

  return (await response.json()) as T;
}
