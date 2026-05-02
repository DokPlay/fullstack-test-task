import type { AlertItem } from "@/entities/alert/model/types";
import type { FileItem } from "@/entities/file/model/types";

export type DashboardState = {
  files: FileItem[];
  alerts: AlertItem[];
};

export type DashboardSnapshotEvent = {
  kind: "snapshot";
  occurred_at: string;
  files: FileItem[];
  alerts: AlertItem[];
};

export type DashboardPatchEvent = {
  kind: "patch";
  event_id: string;
  event_type: string;
  occurred_at: string;
  file: FileItem | null;
  alert: AlertItem | null;
  removed_file_id: string | null;
  removed_alerts_for_file_id: string | null;
};

export function createEmptyDashboardState(): DashboardState {
  return { files: [], alerts: [] };
}

export function normalizeDashboardState(state: DashboardState): DashboardState {
  return {
    files: sortFiles(state.files),
    alerts: sortAlerts(state.alerts),
  };
}

export function applyDashboardSnapshot(
  event: DashboardSnapshotEvent,
): DashboardState {
  return normalizeDashboardState({
    files: event.files,
    alerts: event.alerts,
  });
}

export function applyDashboardPatches(
  state: DashboardState,
  patches: DashboardPatchEvent[],
): DashboardState {
  return patches.reduce(applyDashboardPatch, state);
}

export function parseDashboardSnapshotEvent(
  payload: string,
): DashboardSnapshotEvent {
  return JSON.parse(payload) as DashboardSnapshotEvent;
}

export function parseDashboardPatchEvent(payload: string): DashboardPatchEvent {
  return JSON.parse(payload) as DashboardPatchEvent;
}

function applyDashboardPatch(
  state: DashboardState,
  patch: DashboardPatchEvent,
): DashboardState {
  let files = state.files;
  let alerts = state.alerts;
  let filesChanged = false;
  let alertsChanged = false;

  if (patch.removed_file_id) {
    const nextFiles = files.filter((fileItem) => fileItem.id !== patch.removed_file_id);
    filesChanged = nextFiles.length !== files.length;
    files = nextFiles;
  }

  if (patch.file) {
    files = upsertFile(files, patch.file);
    filesChanged = true;
  }

  if (patch.removed_alerts_for_file_id) {
    const nextAlerts = alerts.filter(
      (alertItem) => alertItem.file_id !== patch.removed_alerts_for_file_id,
    );
    alertsChanged = nextAlerts.length !== alerts.length;
    alerts = nextAlerts;
  }

  if (patch.alert) {
    alerts = upsertAlert(alerts, patch.alert);
    alertsChanged = true;
  }

  if (!filesChanged && !alertsChanged) {
    return state;
  }

  return normalizeDashboardState({ files, alerts });
}

function upsertFile(files: FileItem[], nextFile: FileItem): FileItem[] {
  return [
    nextFile,
    ...files.filter((fileItem) => fileItem.id !== nextFile.id),
  ];
}

function upsertAlert(alerts: AlertItem[], nextAlert: AlertItem): AlertItem[] {
  return [
    nextAlert,
    ...alerts.filter((alertItem) => alertItem.id !== nextAlert.id),
  ];
}

function sortFiles(files: FileItem[]): FileItem[] {
  return [...files].sort((left, right) => {
    const byCreatedAt = compareIsoDates(right.created_at, left.created_at);
    if (byCreatedAt !== 0) {
      return byCreatedAt;
    }

    return right.id.localeCompare(left.id);
  });
}

function sortAlerts(alerts: AlertItem[]): AlertItem[] {
  return [...alerts].sort((left, right) => {
    const byCreatedAt = compareIsoDates(right.created_at, left.created_at);
    if (byCreatedAt !== 0) {
      return byCreatedAt;
    }

    return right.id - left.id;
  });
}

function compareIsoDates(left: string, right: string): number {
  return Date.parse(left) - Date.parse(right);
}
