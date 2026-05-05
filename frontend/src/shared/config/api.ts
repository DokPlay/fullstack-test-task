const DEFAULT_API_URL = "http://localhost:8000";

type PageQueryParams = {
  offset?: number;
  limit?: number;
};

function normalizeBaseUrl(value: string) {
  return value.replace(/\/+$/, "");
}

function withQueryParams(url: string, params: Record<string, number | undefined>) {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) {
      searchParams.set(key, String(value));
    }
  });

  const query = searchParams.toString();
  return query ? `${url}?${query}` : url;
}

export const API_BASE_URL = normalizeBaseUrl(
  process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL,
);

const filesUrl = `${API_BASE_URL}/files`;
const alertsUrl = `${API_BASE_URL}/alerts`;
const eventsUrl = `${API_BASE_URL}/events`;

export const apiRoutes = {
  files: filesUrl,
  alerts: alertsUrl,
  events: eventsUrl,
  filesPage(params: PageQueryParams) {
    return withQueryParams(filesUrl, params);
  },
  alertsPage(params: PageQueryParams) {
    return withQueryParams(alertsUrl, params);
  },
  eventsPage(params: PageQueryParams) {
    return withQueryParams(eventsUrl, params);
  },
  fileDownload(fileId: string) {
    return `${API_BASE_URL}/files/${encodeURIComponent(fileId)}/download`;
  },
};
