"use client";

import { useEffect, useRef, useState } from "react";

import { getDashboardEventsUrl } from "@/features/file-monitoring/api/dashboard-api";
import {
  parseDashboardPatchEvent,
  parseDashboardSnapshotEvent,
  type DashboardPatchEvent,
  type DashboardSnapshotEvent,
} from "./dashboard-events";

const PATCH_BATCH_WINDOW_MS = 150;
const MAX_SEEN_EVENT_IDS = 512;
const SSE_RECONNECT_DELAY_MS = 3000;

type DashboardSSEOptions = {
  onPatches: (patches: DashboardPatchEvent[]) => void;
  onSnapshot: (snapshot: DashboardSnapshotEvent) => void;
};

export function useDashboardSSE({
  onPatches,
  onSnapshot,
}: DashboardSSEOptions) {
  const [isRealtimeConnected, setIsRealtimeConnected] = useState(false);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const onPatchesRef = useRef(onPatches);
  const onSnapshotRef = useRef(onSnapshot);
  const pendingPatchesRef = useRef<DashboardPatchEvent[]>([]);
  const patchFlushTimerRef = useRef<number | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const seenEventIdsRef = useRef(new Set<string>());
  const seenEventOrderRef = useRef<string[]>([]);

  useEffect(() => {
    onPatchesRef.current = onPatches;
  }, [onPatches]);

  useEffect(() => {
    onSnapshotRef.current = onSnapshot;
  }, [onSnapshot]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return undefined;
    }

    const eventSource = new EventSource(getDashboardEventsUrl());

    const rememberEventId = (eventId: string): boolean => {
      if (seenEventIdsRef.current.has(eventId)) {
        return false;
      }

      seenEventIdsRef.current.add(eventId);
      seenEventOrderRef.current.push(eventId);

      if (seenEventOrderRef.current.length > MAX_SEEN_EVENT_IDS) {
        const oldestEventId = seenEventOrderRef.current.shift();
        if (oldestEventId) {
          seenEventIdsRef.current.delete(oldestEventId);
        }
      }

      return true;
    };

    const flushPendingPatches = () => {
      patchFlushTimerRef.current = null;

      if (pendingPatchesRef.current.length === 0) {
        return;
      }

      const patches = pendingPatchesRef.current;
      pendingPatchesRef.current = [];
      onPatchesRef.current(patches);
    };

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current === null) {
        return;
      }

      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    };

    const scheduleReconnect = () => {
      if (reconnectTimerRef.current !== null) {
        return;
      }

      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null;
        setConnectionAttempt((currentAttempt) => currentAttempt + 1);
      }, SSE_RECONNECT_DELAY_MS);
    };

    const closeMalformedStream = () => {
      setIsRealtimeConnected(false);
      flushPendingPatches();
      eventSource.close();
      scheduleReconnect();
    };

    const queuePatch = (patch: DashboardPatchEvent) => {
      if (!rememberEventId(patch.event_id)) {
        return;
      }

      pendingPatchesRef.current.push(patch);

      if (patchFlushTimerRef.current !== null) {
        return;
      }

      patchFlushTimerRef.current = window.setTimeout(() => {
        flushPendingPatches();
      }, PATCH_BATCH_WINDOW_MS);
    };

    const handleSnapshot = (event: MessageEvent<string>) => {
      try {
        onSnapshotRef.current(parseDashboardSnapshotEvent(event.data));
      } catch {
        closeMalformedStream();
      }
    };

    const handlePatch = (event: MessageEvent<string>) => {
      try {
        queuePatch(parseDashboardPatchEvent(event.data));
      } catch {
        closeMalformedStream();
      }
    };

    eventSource.onopen = () => {
      setIsRealtimeConnected(true);
    };

    eventSource.onerror = () => {
      setIsRealtimeConnected(false);
      flushPendingPatches();
    };

    eventSource.addEventListener(
      "dashboard-snapshot",
      handleSnapshot as EventListener,
    );
    eventSource.addEventListener(
      "dashboard-update",
      handlePatch as EventListener,
    );

    return () => {
      if (patchFlushTimerRef.current !== null) {
        window.clearTimeout(patchFlushTimerRef.current);
        patchFlushTimerRef.current = null;
      }

      pendingPatchesRef.current = [];
      clearReconnectTimer();
      eventSource.removeEventListener(
        "dashboard-snapshot",
        handleSnapshot as EventListener,
      );
      eventSource.removeEventListener(
        "dashboard-update",
        handlePatch as EventListener,
      );
      eventSource.close();
    };
  }, [connectionAttempt]);

  return isRealtimeConnected;
}
