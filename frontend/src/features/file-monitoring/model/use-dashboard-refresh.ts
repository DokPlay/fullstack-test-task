"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  getAlertsSnapshot,
  getFilesSnapshot,
} from "@/features/file-monitoring/api/dashboard-api";

import type { DashboardStateController } from "./use-dashboard-state";

export type RefreshIntent = "initial" | "manual" | "poll";

export function useDashboardRefresh({
  applyRefreshResults,
  finishRefresh,
  realtimeRevisionRef,
  startRefresh,
}: DashboardStateController) {
  const requestInFlightRef = useRef(false);
  const queuedRefreshRef = useRef<RefreshIntent | null>(null);
  const refreshIntentRef = useRef<RefreshIntent>("initial");
  const [refreshTick, setRefreshTick] = useState(1);

  const refresh = useCallback((intent: RefreshIntent = "manual") => {
    if (requestInFlightRef.current) {
      queuedRefreshRef.current =
        intent === "manual" ? "manual" : queuedRefreshRef.current ?? intent;
      return;
    }

    refreshIntentRef.current = intent;
    setRefreshTick((value) => value + 1);
  }, []);

  const requestPollRefresh = useCallback(() => {
    if (requestInFlightRef.current) {
      queuedRefreshRef.current = queuedRefreshRef.current ?? "poll";
      return;
    }

    refreshIntentRef.current = "poll";
    setRefreshTick((value) => value + 1);
  }, []);

  useEffect(() => {
    let isActive = true;
    const intent = refreshIntentRef.current;
    const realtimeRevisionAtStart = realtimeRevisionRef.current;

    requestInFlightRef.current = true;
    startRefresh(intent);

    async function runRefresh() {
      try {
        const [filesResult, alertsResult] = await Promise.allSettled([
          getFilesSnapshot(),
          getAlertsSnapshot(),
        ]);

        if (!isActive) {
          return;
        }

        applyRefreshResults({
          alertsResult,
          filesResult,
          realtimeRevisionAtStart,
        });
      } finally {
        requestInFlightRef.current = false;

        if (!isActive) {
          return;
        }

        finishRefresh();

        const queuedIntent = queuedRefreshRef.current;
        queuedRefreshRef.current = null;

        if (queuedIntent) {
          refreshIntentRef.current = queuedIntent;
          setRefreshTick((value) => value + 1);
        }
      }
    }

    void runRefresh();

    return () => {
      isActive = false;
    };
  }, [
    applyRefreshResults,
    finishRefresh,
    realtimeRevisionRef,
    refreshTick,
    startRefresh,
  ]);

  return {
    refresh,
    requestPollRefresh,
  };
}
