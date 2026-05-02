"use client";

import { useEffect } from "react";

const FALLBACK_POLLING_INTERVAL_MS = 8000;

type DashboardPollingOptions = {
  enabled: boolean;
  requestPollRefresh: () => void;
};

export function useDashboardPolling({
  enabled,
  requestPollRefresh,
}: DashboardPollingOptions) {
  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      requestPollRefresh();
    }, FALLBACK_POLLING_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [enabled, requestPollRefresh]);
}
