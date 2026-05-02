"use client";

import type { FileItem } from "@/entities/file/model/types";
import { isFilePending } from "@/entities/file/lib/status";

import { useDashboardPolling } from "./use-dashboard-polling";
import { useDashboardRefresh } from "./use-dashboard-refresh";
import { useDashboardSSE } from "./use-dashboard-sse";
import { useDashboardState } from "./use-dashboard-state";

export function useFileDashboard() {
  const dashboardState = useDashboardState();
  const { refresh, requestPollRefresh } = useDashboardRefresh(dashboardState);
  const isRealtimeConnected = useDashboardSSE({
    onPatches: dashboardState.applyPatches,
    onSnapshot: dashboardState.applySnapshot,
  });

  const files = dashboardState.dashboard.files;
  const alerts = dashboardState.dashboard.alerts;
  const hasPendingFiles = files.some(isFilePending);

  useDashboardPolling({
    enabled: hasPendingFiles && !isRealtimeConnected,
    requestPollRefresh,
  });

  function applyUploadedFile(file: FileItem) {
    dashboardState.applyUploadedFile(file);

    if (!isRealtimeConnected) {
      refresh("manual");
    }
  }

  return {
    files,
    alerts,
    hasPendingFiles,
    isInitialLoading: dashboardState.isInitialLoading,
    isRefreshing: dashboardState.isRefreshing,
    isRealtimeConnected,
    filesError: dashboardState.filesError,
    alertsError: dashboardState.alertsError,
    refresh,
    applyUploadedFile,
  };
}
