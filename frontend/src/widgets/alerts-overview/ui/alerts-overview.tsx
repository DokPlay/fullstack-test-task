import Alert from "react-bootstrap/Alert";
import Table from "react-bootstrap/Table";

import { AlertLevelBadge } from "@/entities/alert/ui/alert-level-badge";
import type { AlertItem } from "@/entities/alert/model/types";
import { formatDate, formatShortId } from "@/shared/lib/format";
import { EmptyState } from "@/shared/ui/empty-state";
import { LoadingState } from "@/shared/ui/loading-state";
import { SectionCard } from "@/shared/ui/section-card";

import styles from "./alerts-overview.module.css";

type AlertsOverviewProps = {
  alerts: AlertItem[];
  isLoading: boolean;
  error: string | null;
};

export function AlertsOverview({ alerts, isLoading, error }: AlertsOverviewProps) {
  return (
    <SectionCard
      title="Алерты"
      description="Финальные результаты обработки и сигналы, требующие внимания."
      value={alerts.length}
    >
      {error ? <Alert variant="warning">{error}</Alert> : null}

      {isLoading && alerts.length === 0 ? (
        <LoadingState label="Подтягиваем ленту алертов" />
      ) : alerts.length === 0 ? (
        <EmptyState
          title="Пока тихо"
          description="Как только backend завершит обработку документов, здесь появятся информационные и warning-алерты."
        />
      ) : (
        <div className={styles.tableWrap}>
          <Table hover responsive="md" className="align-middle mb-0">
            <thead>
              <tr>
                <th>Уровень</th>
                <th>Сообщение</th>
                <th>Файл</th>
                <th>Создан</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.id}>
                  <td>
                    <AlertLevelBadge level={alert.level} />
                  </td>
                  <td className={styles.message}>{alert.message}</td>
                  <td className={`${styles.mono} small`}>
                    {formatShortId(alert.file_id)}
                  </td>
                  <td>{formatDate(alert.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </SectionCard>
  );
}
