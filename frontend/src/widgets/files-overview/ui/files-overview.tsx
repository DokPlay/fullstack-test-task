"use client";

import { useMemo, useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Pagination from "react-bootstrap/Pagination";
import Table from "react-bootstrap/Table";

import { FileStatusBadge, FileScanBadge } from "@/entities/file/ui/file-badges";
import { isFilePending } from "@/entities/file/lib/status";
import type { FileItem } from "@/entities/file/model/types";
import { apiRoutes } from "@/shared/config/api";
import {
  formatDate,
  formatFileSize,
  formatShortId,
  getMetadataSummary,
} from "@/shared/lib/format";
import { EmptyState } from "@/shared/ui/empty-state";
import { LoadingState } from "@/shared/ui/loading-state";
import { SectionCard } from "@/shared/ui/section-card";

import styles from "./files-overview.module.css";

type FilesOverviewProps = {
  files: FileItem[];
  isLoading: boolean;
  error: string | null;
};

const FILES_PAGE_SIZE = 25;
const PAGINATION_WINDOW_SIZE = 5;

function getPageNumbers(currentPage: number, totalPages: number) {
  const firstPage = Math.max(
    1,
    Math.min(
      currentPage - Math.floor(PAGINATION_WINDOW_SIZE / 2),
      totalPages - PAGINATION_WINDOW_SIZE + 1,
    ),
  );
  const lastPage = Math.min(totalPages, firstPage + PAGINATION_WINDOW_SIZE - 1);

  return Array.from(
    { length: lastPage - firstPage + 1 },
    (_, index) => firstPage + index,
  );
}

export function FilesOverview({ files, isLoading, error }: FilesOverviewProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const {
    pageEndIndex,
    pageNumbers,
    pageStartIndex,
    safeCurrentPage,
    shouldShowPagination,
    totalPages,
    visibleFiles,
  } = useMemo(() => {
    const nextTotalPages = Math.max(1, Math.ceil(files.length / FILES_PAGE_SIZE));
    const nextCurrentPage = Math.min(currentPage, nextTotalPages);
    const nextPageStartIndex = (nextCurrentPage - 1) * FILES_PAGE_SIZE;
    const nextPageEndIndex = Math.min(nextPageStartIndex + FILES_PAGE_SIZE, files.length);

    return {
      pageEndIndex: nextPageEndIndex,
      pageNumbers: getPageNumbers(nextCurrentPage, nextTotalPages),
      pageStartIndex: nextPageStartIndex,
      safeCurrentPage: nextCurrentPage,
      shouldShowPagination: files.length > FILES_PAGE_SIZE,
      totalPages: nextTotalPages,
      visibleFiles: files.slice(nextPageStartIndex, nextPageEndIndex),
    };
  }, [currentPage, files]);

  return (
    <SectionCard
      title="Файлы"
      description="Текущая очередь документов и статус фоновой обработки."
      value={files.length}
    >
      {error ? <Alert variant="warning">{error}</Alert> : null}

      {isLoading && files.length === 0 ? (
        <LoadingState label="Подтягиваем список файлов" />
      ) : files.length === 0 ? (
        <EmptyState
          title="Очередь пуста"
          description="Загрузите первый файл, чтобы увидеть статусы обработки и результаты проверки."
        />
      ) : (
        <>
          <div className={styles.tableWrap}>
            <Table hover className={`${styles.table} align-middle mb-0`}>
              <thead>
                <tr>
                  <th>Документ</th>
                  <th>Источник</th>
                  <th>Статусы</th>
                  <th>Метаданные</th>
                  <th>Обновлен</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visibleFiles.map((file) => {
                  const metadataSummary = getMetadataSummary(file.metadata_json);

                  return (
                    <tr
                      key={file.id}
                      className={file.requires_attention ? styles.rowAccent : undefined}
                    >
                      <td>
                        <div className={`${styles.documentTitle} fw-semibold`}>
                          {file.title}
                        </div>
                        <div className={`${styles.mono} small text-secondary mt-1`}>
                          {formatShortId(file.id)}
                        </div>
                      </td>
                      <td>
                        <div className="fw-medium">{file.original_name}</div>
                        <div className="small text-secondary mt-1">
                          {file.mime_type} • {formatFileSize(file.size)}
                        </div>
                      </td>
                      <td>
                        <div className={`${styles.statusStack} d-flex flex-column gap-2`}>
                          <div>
                            <FileStatusBadge status={file.processing_status} />
                          </div>
                          <div className="d-flex flex-column gap-1">
                            <div>
                              <FileScanBadge file={file} />
                            </div>
                            <span className="small text-secondary">
                              {file.scan_details ??
                                (isFilePending(file)
                                  ? "Ожидаем завершения фоновой обработки"
                                  : "Статус проверки скоро появится")}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td>
                        {metadataSummary.length > 0 ? (
                          <div className={styles.metaList}>
                            {metadataSummary.map((item) => (
                              <span key={item} className={styles.metaItem}>
                                {item}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="small text-secondary">
                            Появятся после обработки
                          </span>
                        )}
                      </td>
                      <td>
                        <div>{formatDate(file.updated_at)}</div>
                        <div className="small text-secondary mt-1">
                          Создан {formatDate(file.created_at)}
                        </div>
                      </td>
                      <td className="text-end">
                        <Button
                          as="a"
                          href={apiRoutes.fileDownload(file.id)}
                          variant="outline-primary"
                          size="sm"
                        >
                          Скачать
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </div>

          {shouldShowPagination ? (
            <div className={styles.paginationBar}>
              <span className="small text-secondary">
                Показаны {pageStartIndex + 1}-{pageEndIndex} из {files.length}
              </span>
              <Pagination className={`${styles.pagination} mb-0`} size="sm">
                <Pagination.First
                  disabled={safeCurrentPage === 1}
                  onClick={() => setCurrentPage(1)}
                />
                <Pagination.Prev
                  disabled={safeCurrentPage === 1}
                  onClick={() => setCurrentPage(Math.max(1, safeCurrentPage - 1))}
                />
                {pageNumbers.map((pageNumber) => (
                  <Pagination.Item
                    key={pageNumber}
                    active={pageNumber === safeCurrentPage}
                    onClick={() => setCurrentPage(pageNumber)}
                  >
                    {pageNumber}
                  </Pagination.Item>
                ))}
                <Pagination.Next
                  disabled={safeCurrentPage === totalPages}
                  onClick={() =>
                    setCurrentPage(Math.min(totalPages, safeCurrentPage + 1))
                  }
                />
                <Pagination.Last
                  disabled={safeCurrentPage === totalPages}
                  onClick={() => setCurrentPage(totalPages)}
                />
              </Pagination>
            </div>
          ) : null}
        </>
      )}
    </SectionCard>
  );
}
