import Badge from "react-bootstrap/Badge";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Spinner from "react-bootstrap/Spinner";

import styles from "./dashboard-hero.module.css";

type DashboardHeroProps = {
  totalFiles: number;
  processingCount: number;
  attentionCount: number;
  alertsCount: number;
  hasPendingFiles: boolean;
  isRealtimeConnected: boolean;
  isRefreshing: boolean;
  onRefresh: () => void;
  onUpload: () => void;
};

const metrics = [
  {
    key: "files",
    label: "Файлы",
  },
  {
    key: "processing",
    label: "В обработке",
  },
  {
    key: "attention",
    label: "Требуют внимания",
  },
  {
    key: "alerts",
    label: "Алерты",
  },
] as const;

export function DashboardHero({
  totalFiles,
  processingCount,
  attentionCount,
  alertsCount,
  hasPendingFiles,
  isRealtimeConnected,
  isRefreshing,
  onRefresh,
  onUpload,
}: DashboardHeroProps) {
  const values = {
    files: totalFiles,
    processing: processingCount,
    attention: attentionCount,
    alerts: alertsCount,
  };

  return (
    <Card className={`${styles.hero} border-0 shadow-sm mb-4`}>
      <Card.Body className="p-4 p-lg-5">
        <div className="d-flex flex-column flex-lg-row justify-content-between gap-4 mb-4">
          <div className="position-relative">
            <p
              className={`${styles.eyebrow} small fw-semibold text-uppercase text-primary mb-2`}
            >
              File control center
            </p>
            <h1 className="display-6 fw-semibold mb-3">Управление файлами</h1>
            <p className="lead text-secondary mb-0">
              Один экран для загрузки документов, отслеживания фоновой обработки и
              контроля алертов.
            </p>
          </div>

          <div className="d-flex flex-wrap align-items-start justify-content-lg-end gap-2">
            <Button
              variant="outline-secondary"
              onClick={onRefresh}
              disabled={isRefreshing}
            >
              {isRefreshing ? "Обновляем..." : "Обновить"}
            </Button>
            <Button variant="primary" onClick={onUpload}>
              Добавить файл
            </Button>
          </div>
        </div>

        <div className="d-flex flex-wrap align-items-center gap-3 mb-4">
          <Badge bg={isRealtimeConnected ? "primary" : hasPendingFiles ? "warning" : "success"}>
            {isRealtimeConnected
              ? "Live updates через SSE"
              : hasPendingFiles
                ? "Fallback polling активен"
                : "Все синхронизировано"}
          </Badge>
          <div className={`${styles.statusLine} small d-flex align-items-center gap-2`}>
            {isRefreshing ? <Spinner animation="border" size="sm" /> : null}
            {isRealtimeConnected
              ? "Дашборд получает события от backend почти мгновенно и не нагружает базу постоянным polling."
              : hasPendingFiles
                ? "Realtime-канал временно недоступен, поэтому включен осторожный fallback polling для активных файлов."
                : "Сейчас показан актуальный снимок данных. После новой загрузки панель снова синхронизируется автоматически."}
          </div>
        </div>

        <div className={styles.metricGrid}>
          {metrics.map((metric) => (
            <div key={metric.key} className={styles.metricCard}>
              <div className={styles.metricLabel}>{metric.label}</div>
              <div className={`${styles.metricValue} fw-semibold mt-2`}>
                {values[metric.key]}
              </div>
            </div>
          ))}
        </div>
      </Card.Body>
    </Card>
  );
}
