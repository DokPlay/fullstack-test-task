"use client";

import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";
import Modal from "react-bootstrap/Modal";
import ProgressBar from "react-bootstrap/ProgressBar";

import type { FileItem } from "@/entities/file/model/types";
import { createFile } from "@/features/upload-file/api/create-file";
import { MAX_UPLOAD_SIZE_BYTES } from "@/shared/config/upload";
import { formatFileSize } from "@/shared/lib/format";

import styles from "./upload-file-modal.module.css";

type UploadFileModalProps = {
  show: boolean;
  onHide: () => void;
  onUploaded: (file: FileItem) => Promise<void> | void;
};

export function UploadFileModal({
  show,
  onHide,
  onUploaded,
}: UploadFileModalProps) {
  const titleId = useId();
  const fileId = useId();
  const [title, setTitle] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fileInputKey, setFileInputKey] = useState(0);
  const activeUploadControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);
  const selectedFileError = getSelectedFileError(selectedFile);

  useEffect(() => {
    isMountedRef.current = true;

    return () => {
      isMountedRef.current = false;
      activeUploadControllerRef.current?.abort();
      activeUploadControllerRef.current = null;
    };
  }, []);

  function abortActiveUpload() {
    activeUploadControllerRef.current?.abort();
    activeUploadControllerRef.current = null;
  }

  function resetForm() {
    setTitle("");
    setSelectedFile(null);
    setFormError(null);
    setUploadError(null);
    setUploadProgress(0);
    setIsSubmitting(false);
    setFileInputKey((value) => value + 1);
  }

  function handleHide() {
    abortActiveUpload();
    resetForm();
    onHide();
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const normalizedTitle = title.trim();

    if (!normalizedTitle && !selectedFile) {
      setFormError("Укажите название и выберите файл.");
      return;
    }

    if (!normalizedTitle) {
      setFormError("Укажите понятное название для документа.");
      return;
    }

    if (!selectedFile) {
      setFormError("Выберите файл для загрузки.");
      return;
    }

    if (selectedFileError) {
      setFormError(selectedFileError);
      return;
    }

    setFormError(null);
    setUploadError(null);
    setUploadProgress(0);
    setIsSubmitting(true);
    abortActiveUpload();
    const uploadController = new AbortController();
    activeUploadControllerRef.current = uploadController;

    try {
      const uploadedFile = await createFile({
        title: normalizedTitle,
        file: selectedFile,
        signal: uploadController.signal,
        onProgress: (progress) => {
          if (isMountedRef.current) {
            setUploadProgress(progress.percentage);
          }
        },
      });
      await onUploaded(uploadedFile);
      handleHide();
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }

      if (!isMountedRef.current) {
        return;
      }

      setUploadError(
        error instanceof Error ? error.message : "Не удалось загрузить файл",
      );
    } finally {
      if (activeUploadControllerRef.current === uploadController) {
        activeUploadControllerRef.current = null;
      }

      if (isMountedRef.current) {
        setIsSubmitting(false);
      }
    }
  }

  return (
    <Modal show={show} onHide={handleHide} centered>
      <Form onSubmit={handleSubmit}>
        <Modal.Header closeButton>
          <Modal.Title>Добавить файл</Modal.Title>
        </Modal.Header>
        <Modal.Body className="px-4 pb-4">
          <div className={`${styles.note} p-3 mb-4 small`}>
            После загрузки документ автоматически уйдет в фоновую проверку и
            карточки на дашборде обновятся без ручного refresh.
          </div>

          {formError ? (
            <Alert variant="warning" className="mb-3">
              {formError}
            </Alert>
          ) : null}

          {uploadError ? (
            <Alert variant="danger" className="mb-3">
              {uploadError}
            </Alert>
          ) : null}

          <Form.Group className="mb-3" controlId={titleId}>
            <Form.Label>Название</Form.Label>
            <Form.Control
              value={title}
              isInvalid={Boolean(formError) && !title.trim()}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Например, Договор с подрядчиком"
            />
          </Form.Group>

          <Form.Group controlId={fileId}>
            <Form.Label>Файл</Form.Label>
            <Form.Control
              key={fileInputKey}
              type="file"
              isInvalid={
                Boolean(formError) && (!selectedFile || Boolean(selectedFileError))
              }
              onChange={(event) => {
                const nextFile =
                  (event.target as HTMLInputElement).files?.[0] ?? null;
                setSelectedFile(nextFile);
                setUploadError(null);
                setFormError(getSelectedFileError(nextFile));
              }}
            />
            <Form.Text muted>
              Максимальный размер: {formatFileSize(MAX_UPLOAD_SIZE_BYTES)}.
            </Form.Text>
          </Form.Group>

          {isSubmitting ? (
            <div className="mt-3">
              <div className="d-flex justify-content-between small text-muted mb-1">
                <span>Загрузка файла</span>
                <span>{uploadProgress}%</span>
              </div>
              <ProgressBar
                now={uploadProgress}
                min={0}
                max={100}
                animated={uploadProgress < 100}
                striped={uploadProgress < 100}
                aria-label="Прогресс загрузки файла"
              />
            </div>
          ) : null}
        </Modal.Body>
        <Modal.Footer>
          <Button
            variant="outline-secondary"
            onClick={handleHide}
          >
            Отмена
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={isSubmitting || Boolean(selectedFileError)}
          >
            {isSubmitting ? "Загрузка..." : "Сохранить"}
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  );
}

function getSelectedFileError(file: File | null) {
  if (!file || file.size <= MAX_UPLOAD_SIZE_BYTES) {
    return null;
  }

  return `Файл слишком большой. Максимальный размер загрузки: ${formatFileSize(MAX_UPLOAD_SIZE_BYTES)}.`;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}
