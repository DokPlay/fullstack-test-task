import type { AlertItem } from "@/entities/alert/model/types";
import type { FileItem } from "@/entities/file/model/types";
import { fetchJson } from "@/shared/api/http";
import { apiRoutes } from "@/shared/config/api";

const DASHBOARD_SNAPSHOT_PAGE = {
  offset: 0,
  limit: 500,
} as const;

export function getFilesSnapshot() {
  return fetchJson<FileItem[]>(
    apiRoutes.filesPage(DASHBOARD_SNAPSHOT_PAGE),
    {},
    "Не удалось загрузить список файлов",
  );
}

export function getAlertsSnapshot() {
  return fetchJson<AlertItem[]>(
    apiRoutes.alertsPage(DASHBOARD_SNAPSHOT_PAGE),
    {},
    "Не удалось загрузить список алертов",
  );
}

export function getDashboardEventsUrl() {
  return apiRoutes.eventsPage(DASHBOARD_SNAPSHOT_PAGE);
}
