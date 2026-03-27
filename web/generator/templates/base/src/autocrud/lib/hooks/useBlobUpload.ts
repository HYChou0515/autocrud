/**
 * useBlobUpload — React hook for uploading files to the blob store.
 *
 * Files smaller than `CHUNK_THRESHOLD` (default 10 MB) are uploaded via
 * simple `POST /blobs/upload`.  Larger files use the upload-session API
 * with **parallel** chunked uploads for maximum bandwidth utilisation.
 *
 * Each chunk is sent with a `?part_number=N` query parameter so the
 * back-end can reassemble them in the correct order even when they
 * arrive out of sequence.  The `concurrency` option controls how many
 * chunks upload in parallel (default 4).
 *
 * @example
 * ```tsx
 * const { upload, cancel, progress, status, error } = useBlobUpload();
 *
 * const handleFile = async (file: File) => {
 *   const result = await upload(file);
 *   if (result) console.log('Uploaded:', result.file_id);
 * };
 * ```
 */

import { useCallback, useRef, useState } from 'react';
import { client, getApiBasePath } from '../client';
import type { BlobFinalizeResult } from '@/autocrud/types/api';
import type { AxiosProgressEvent } from 'axios';

/** Default chunk size: 10 MB */
const CHUNK_SIZE = 10 * 1024 * 1024;

/** Files larger than this use chunked upload sessions */
const CHUNK_THRESHOLD = 10 * 1024 * 1024;

/** Default number of concurrent chunk uploads */
const DEFAULT_CONCURRENCY = 4;

export type BlobUploadStatus = 'idle' | 'uploading' | 'finalizing' | 'done' | 'error' | 'cancelled';

export interface BlobUploadProgress {
  /** Bytes sent so far */
  loaded: number;
  /** Total file size */
  total: number;
  /** 0–100 percentage */
  percent: number;
}

export interface BlobUploadResult {
  file_id: string;
  size: number;
  content_type: string;
}

export interface UseBlobUploadReturn {
  /** Start uploading a file. Returns result or null on error/cancel. */
  upload: (file: File) => Promise<BlobUploadResult | null>;
  /** Cancel the current upload. */
  cancel: () => void;
  /** Current upload status. */
  status: BlobUploadStatus;
  /** Upload progress (bytes loaded, total, percent). */
  progress: BlobUploadProgress;
  /** Error message if status is 'error'. */
  error: string | null;
  /** Reset to idle state. */
  reset: () => void;
}

/**
 * Hook for uploading files with automatic parallel chunked upload for large files.
 *
 * @param options.chunkSize - Chunk size in bytes (default 10 MB)
 * @param options.chunkThreshold - File size threshold for chunked upload (default 10 MB)
 * @param options.concurrency - Max concurrent chunk uploads (default 4)
 */
export function useBlobUpload(options?: {
  chunkSize?: number;
  chunkThreshold?: number;
  concurrency?: number;
}): UseBlobUploadReturn {
  const chunkSize = options?.chunkSize ?? CHUNK_SIZE;
  const chunkThreshold = options?.chunkThreshold ?? CHUNK_THRESHOLD;
  const concurrency = options?.concurrency ?? DEFAULT_CONCURRENCY;

  const [status, setStatus] = useState<BlobUploadStatus>('idle');
  const [progress, setProgress] = useState<BlobUploadProgress>({ loaded: 0, total: 0, percent: 0 });
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const uploadIdRef = useRef<string | null>(null);

  const reset = useCallback(() => {
    setStatus('idle');
    setProgress({ loaded: 0, total: 0, percent: 0 });
    setError(null);
    uploadIdRef.current = null;
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;

    // Best-effort abort the upload session
    const uid = uploadIdRef.current;
    if (uid) {
      const bp = getApiBasePath();
      client.post(`${bp}/blobs/upload-sessions/${uid}/abort`).catch(() => {});
      uploadIdRef.current = null;
    }

    setStatus('cancelled');
  }, []);

  const upload = useCallback(
    async (file: File): Promise<BlobUploadResult | null> => {
      // Reset state
      setStatus('uploading');
      setProgress({ loaded: 0, total: file.size, percent: 0 });
      setError(null);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        let result: BlobUploadResult;

        if (file.size <= chunkThreshold) {
          // ---------- Simple upload ----------
          result = await simpleUpload(file, controller.signal, (loaded) => {
            const percent = file.size > 0 ? Math.round((loaded / file.size) * 100) : 100;
            setProgress({ loaded, total: file.size, percent });
          });
        } else {
          // ---------- Parallel chunked upload session ----------
          const bp = getApiBasePath();
          const totalChunks = Math.ceil(file.size / chunkSize);

          // 1. Create session with total_parts
          const sessionResp = await client.post(
            `${bp}/blobs/upload-sessions`,
            {
              content_type: file.type || 'application/octet-stream',
              size: file.size,
              total_parts: totalChunks,
            },
            { signal: controller.signal },
          );
          const uploadId: string = sessionResp.data.upload_id;
          uploadIdRef.current = uploadId;

          // 2. Upload chunks in parallel with concurrency pool
          // Track per-part in-flight progress for accurate overall progress
          const partProgress = new Map<number, number>();

          const updateProgress = () => {
            let loaded = 0;
            for (const bytes of partProgress.values()) {
              loaded += bytes;
            }
            const percent = file.size > 0 ? Math.round((loaded / file.size) * 100) : 100;
            setProgress({ loaded, total: file.size, percent: Math.min(percent, 99) });
          };

          // Build list of chunk tasks
          const chunkTasks: Array<{ partNumber: number; start: number; end: number }> = [];
          for (let i = 0; i < totalChunks; i++) {
            const start = i * chunkSize;
            const end = Math.min(start + chunkSize, file.size);
            chunkTasks.push({ partNumber: i + 1, start, end });
          }

          // Concurrency pool: run at most `concurrency` uploads at once
          let taskIndex = 0;
          let firstError: Error | null = null;

          const runWorker = async () => {
            while (taskIndex < chunkTasks.length && !firstError) {
              if (controller.signal.aborted) return;
              const idx = taskIndex++;
              if (idx >= chunkTasks.length) break;

              const { partNumber, start, end } = chunkTasks[idx];
              const chunk = file.slice(start, end);
              const chunkBytes = end - start;

              const form = new FormData();
              form.append('file', chunk, file.name);

              try {
                await client.put(
                  `${bp}/blobs/upload-sessions/${uploadId}/content`,
                  form,
                  {
                    params: { part_number: partNumber },
                    headers: { 'Content-Type': 'multipart/form-data' },
                    signal: controller.signal,
                    onUploadProgress: (e: AxiosProgressEvent) => {
                      partProgress.set(partNumber, Math.min(e.loaded ?? 0, chunkBytes));
                      updateProgress();
                    },
                  },
                );
                // Mark part as fully uploaded
                partProgress.set(partNumber, chunkBytes);
                updateProgress();
              } catch (err) {
                if (!firstError) firstError = err as Error;
                return;
              }
            }
          };

          // Launch `concurrency` workers
          const workers = Array.from({ length: Math.min(concurrency, totalChunks) }, () => runWorker());
          await Promise.all(workers);

          // Check for errors or cancellation
          if (controller.signal.aborted) {
            setStatus('cancelled');
            return null;
          }
          if (firstError) {
            throw firstError;
          }

          // 3. Finalize
          setStatus('finalizing');
          const finalResp = await client.post<BlobFinalizeResult>(
            `${bp}/blobs/upload-sessions/${uploadId}/finalize`,
            null,
            { signal: controller.signal },
          );
          result = finalResp.data;
          uploadIdRef.current = null;
        }

        setProgress({ loaded: file.size, total: file.size, percent: 100 });
        setStatus('done');
        return result;
      } catch (err: any) {
        if (controller.signal.aborted || err?.code === 'ERR_CANCELED') {
          setStatus('cancelled');
          return null;
        }
        const msg = err?.response?.data?.detail || err?.message || 'Upload failed';
        setError(msg);
        setStatus('error');
        return null;
      } finally {
        abortRef.current = null;
      }
    },
    [chunkSize, chunkThreshold, concurrency],
  );

  return { upload, cancel, progress, status, error, reset };
}

/**
 * Simple (non-chunked) upload via POST /blobs/upload.
 */
async function simpleUpload(
  file: File,
  signal: AbortSignal,
  onProgress: (loaded: number) => void,
): Promise<BlobUploadResult> {
  const bp = getApiBasePath();
  const form = new FormData();
  form.append('file', file);

  const resp = await client.post<BlobUploadResult>(`${bp}/blobs/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    signal,
    onUploadProgress: (e: AxiosProgressEvent) => {
      onProgress(e.loaded ?? 0);
    },
  });
  return resp.data;
}
