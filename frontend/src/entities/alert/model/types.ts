export type AlertLevel = "critical" | "warning" | "info";

export type AlertItem = {
  id: number;
  file_id: string;
  level: AlertLevel;
  message: string;
  created_at: string;
};
