import type { AlertLevel } from "@/entities/alert/model/types";

type AlertLevelMeta = {
  label: string;
  variant: "danger" | "warning" | "info";
};

const ALERT_LEVEL_META: Record<AlertLevel, AlertLevelMeta> = {
  critical: { label: "Критичный", variant: "danger" },
  warning: { label: "Предупреждение", variant: "warning" },
  info: { label: "Инфо", variant: "info" },
};

export function getAlertLevelMeta(level: AlertLevel) {
  return ALERT_LEVEL_META[level];
}
