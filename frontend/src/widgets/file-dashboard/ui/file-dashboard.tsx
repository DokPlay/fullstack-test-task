"use client";

import { useMemo, useState } from "react";
import Col from "react-bootstrap/Col";
import Container from "react-bootstrap/Container";
import Row from "react-bootstrap/Row";

import { isFilePending } from "@/entities/file/lib/status";
import { useFileDashboard } from "@/features/file-monitoring/model/use-file-dashboard";
import { UploadFileModal } from "@/features/upload-file/ui/upload-file-modal";
import { AlertsOverview } from "@/widgets/alerts-overview/ui/alerts-overview";
import { DashboardHero } from "@/widgets/dashboard-hero/ui/dashboard-hero";
import { FilesOverview } from "@/widgets/files-overview/ui/files-overview";

import styles from "./file-dashboard.module.css";

export function FileDashboard() {
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const {
    files,
    alerts,
    hasPendingFiles,
    isInitialLoading,
    isRefreshing,
    isRealtimeConnected,
    filesError,
    alertsError,
    refresh,
    applyUploadedFile,
  } = useFileDashboard();

  const processingCount = useMemo(
    () => files.filter(isFilePending).length,
    [files],
  );
  const attentionCount = useMemo(
    () => files.filter((file) => file.requires_attention).length,
    [files],
  );

  return (
    <Container fluid className={styles.page}>
      <div className={styles.canvas}>
        <DashboardHero
          totalFiles={files.length}
          processingCount={processingCount}
          attentionCount={attentionCount}
          alertsCount={alerts.length}
          hasPendingFiles={hasPendingFiles}
          isRealtimeConnected={isRealtimeConnected}
          isRefreshing={isRefreshing}
          onRefresh={() => void refresh()}
          onUpload={() => setIsUploadOpen(true)}
        />
        <Row className="g-4">
          <Col xl={8}>
            <FilesOverview
              files={files}
              isLoading={isInitialLoading}
              error={filesError}
            />
          </Col>
          <Col xl={4}>
            <AlertsOverview
              alerts={alerts}
              isLoading={isInitialLoading}
              error={alertsError}
            />
          </Col>
        </Row>
      </div>

      <UploadFileModal
        show={isUploadOpen}
        onHide={() => setIsUploadOpen(false)}
        onUploaded={applyUploadedFile}
      />
    </Container>
  );
}
