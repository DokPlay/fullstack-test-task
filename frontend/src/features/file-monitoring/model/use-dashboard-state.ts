"use client";

import { startTransition, useCallback, useRef, useState } from "react";

import type { AlertItem } from "@/entities/alert/model/types";
import type { FileItem } from "@/entities/file/model/types";

import {
  applyDashboardPatches,
  applyDashboardSnapshot,
  createEmptyDashboardState,
  normalizeDashboardState,
  type DashboardPatchEvent,
  type DashboardSnapshotEvent,
  type DashboardState,
} from "./dashboard-events";
import type { RefreshIntent } from "./use-dashboard-refresh";

export type RefreshResults = {
  alertsResult: PromiseSettledResult<AlertItem[]>;
  filesResult: PromiseSettledResult<FileItem[]>;
  realtimeRevisionAtStart: number;
};

export type DashboardStateController = ReturnType<typeof useDashboardState>;

export function useDashboardState() {
  const [dashboard, setDashboard] = useState<DashboardState>(() =>
    createEmptyDashboardState(),
  );
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [filesError, setFilesError] = useState<string | null>(null);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const dashboardRef = useRef(dashboard);
  const realtimeRevisionRef = useRef(0);

  const applyDashboardState = useCallback((nextState: DashboardState) => {
    dashboardRef.current = nextState;
    startTransition(() => {
      setDashboard(nextState);
    });
  }, []);

  const clearErrors = useCallback(() => {
    setFilesError(null);
    setAlertsError(null);
  }, []);

  const startRefresh = useCallback((intent: RefreshIntent) => {
    if (intent === "initial") {
      setIsInitialLoading(true);
      return;
    }

    setIsRefreshing(true);
  }, []);

  const finishRefresh = useCallback(() => {
    setIsInitialLoading(false);
    setIsRefreshing(false);
  }, []);

  const applyRefreshResults = useCallback(
    ({
      alertsResult,
      filesResult,
      realtimeRevisionAtStart,
    }: RefreshResults) => {
      if (realtimeRevisionRef.current !== realtimeRevisionAtStart) {
        return;
      }

      const nextState = normalizeDashboardState({
        files:
          filesResult.status === "fulfilled"
            ? filesResult.value
            : dashboardRef.current.files,
        alerts:
          alertsResult.status === "fulfilled"
            ? alertsResult.value
            : dashboardRef.current.alerts,
      });

      applyDashboardState(nextState);

      startTransition(() => {
        if (filesResult.status === "fulfilled") {
          setFilesError(null);
        } else {
          setFilesError(toErrorMessage(filesResult.reason, "Не удалось загрузить список файлов"));
        }

        if (alertsResult.status === "fulfilled") {
          setAlertsError(null);
        } else {
          setAlertsError(toErrorMessage(alertsResult.reason, "Не удалось загрузить список алертов"));
        }
      });
    },
    [applyDashboardState],
  );

  const applySnapshot = useCallback(
    (snapshot: DashboardSnapshotEvent) => {
      realtimeRevisionRef.current += 1;
      applyDashboardState(applyDashboardSnapshot(snapshot));
      clearErrors();
      setIsInitialLoading(false);
    },
    [applyDashboardState, clearErrors],
  );

  const applyPatches = useCallback(
    (patches: DashboardPatchEvent[]) => {
      if (patches.length === 0) {
        return;
      }

      realtimeRevisionRef.current += 1;
      applyDashboardState(applyDashboardPatches(dashboardRef.current, patches));
      clearErrors();
      setIsInitialLoading(false);
    },
    [applyDashboardState, clearErrors],
  );

  const applyUploadedFile = useCallback(
    (file: FileItem) => {
      applyPatches([
        {
          kind: "patch",
          event_id: `local-upload-${file.id}`,
          event_type: "file.created",
          occurred_at: new Date().toISOString(),
          file,
          alert: null,
          removed_file_id: null,
          removed_alerts_for_file_id: null,
        },
      ]);
      setFilesError(null);
    },
    [applyPatches],
  );

  return {
    dashboard,
    dashboardRef,
    realtimeRevisionRef,
    isInitialLoading,
    isRefreshing,
    filesError,
    alertsError,
    applyPatches,
    applyRefreshResults,
    applySnapshot,
    applyUploadedFile,
    finishRefresh,
    startRefresh,
  };
}

function toErrorMessage(reason: unknown, fallbackMessage: string) {
  return reason instanceof Error ? reason.message : fallbackMessage;
}
