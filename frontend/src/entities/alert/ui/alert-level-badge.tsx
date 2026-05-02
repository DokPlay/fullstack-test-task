import Badge from "react-bootstrap/Badge";

import { getAlertLevelMeta } from "@/entities/alert/lib/status";
import type { AlertLevel } from "@/entities/alert/model/types";

type AlertLevelBadgeProps = {
  level: AlertLevel;
};

export function AlertLevelBadge({ level }: AlertLevelBadgeProps) {
  const meta = getAlertLevelMeta(level);

  return (
    <Badge
      bg={meta.variant}
      className={meta.variant === "warning" ? "text-dark" : undefined}
    >
      {meta.label}
    </Badge>
  );
}
