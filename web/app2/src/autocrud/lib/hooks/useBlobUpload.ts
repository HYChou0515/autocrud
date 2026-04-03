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
import { blobApi } from '@/autocrud/generated/api/blobApi';
import type { AxiosProgressEvent } from 'axios';

/** Default chunk size: 1 MB */
const CHUNK_SIZE = 1000 * 1024 * 1024;

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
  /** Elapsed time in seconds since upload started */
  elapsed: number;
  /** Estimated time remaining in seconds, null if not enough data */
  eta: number | null;
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
  /** Upload progress (bytes loaded, total, percent, elapsed, eta). */
  progress: BlobUploadProgress;
  /** Error message if status is 'error'. */
  error: string | null;
  /** Reset to idle state. */
  reset: () => void;
}

/** Options for the standalone uploadFileToBlob function */
export interface UploadFileToBlobOptions {
  chunkSize?: number;
  chunkThreshold?: number;
  concurrency?: number;
  signal?: AbortSignal;
  /** Called whenever upload progress changes */
  onProgress?: (loaded: number, total: number) => void;
  /** Called when status changes (e.g. 'uploading' → 'finalizing') */
  onStatusChange?: (status: BlobUploadStatus) => void;
}

/**
 * Standalone (non-hook) function to upload a file to the blob store.
 *
 * Supports both simple and chunked uploads, with progress callbacks.
 * Use this when you need to upload files outside of React component
 * lifecycle (e.g. during form submission).
 *
 * @param file - File to upload
 * @param options - Upload options including progress callback and abort signal
 * @returns Promise resolving to upload result, or null if cancelled
 */
export async function uploadFileToBlob(
  file: File,
  options?: UploadFileToBlobOptions,
): Promise<BlobUploadResult | null> {
  const chunkSize = options?.chunkSize ?? CHUNK_SIZE;
  const chunkThreshold = options?.chunkThreshold ?? CHUNK_THRESHOLD;
  const concurrency = options?.concurrency ?? DEFAULT_CONCURRENCY;
  const signal = options?.signal;
  const onProgress = options?.onProgress;
  const onStatusChange = options?.onStatusChange;

  onStatusChange?.('uploading');

  try {
    let result: BlobUploadResult;

    if (file.size <= chunkThreshold) {
      // ---------- Simple upload via blobApi ----------
      const resp = await blobApi.upload(file, {
        onUploadProgress: (e: AxiosProgressEvent) => {
          onProgress?.(e.loaded ?? 0, file.size);
        },
        signal,
      });
      result = resp.data;
    } else {
      // ---------- Parallel chunked upload session via blobApi ----------
      const contentType = file.type || 'application/octet-stream';
      const totalChunks = Math.ceil(file.size / chunkSize);

      const sessionResp = await blobApi.createUploadSession(
        { content_type: contentType, size: file.size, total_parts: totalChunks },
        signal,
      );
      const uploadId: string = sessionResp.data.upload_id;

      const partProgress = new Map<number, number>();
      const updateProgress = () => {
        let loaded = 0;
        for (const bytes of partProgress.values()) loaded += bytes;
        onProgress?.(loaded, file.size);
      };

      const chunkTasks: Array<{ partNumber: number; start: number; end: number }> = [];
      for (let i = 0; i < totalChunks; i++) {
        const start = i * chunkSize;
        const end = Math.min(start + chunkSize, file.size);
        chunkTasks.push({ partNumber: i + 1, start, end });
      }

      let taskIndex = 0;
      let firstError: Error | null = null;

      const runWorker = async () => {
        while (taskIndex < chunkTasks.length && !firstError) {
          if (signal?.aborted) return;
          const idx = taskIndex++;
          if (idx >= chunkTasks.length) break;

          const { partNumber, start, end } = chunkTasks[idx];
          const chunk = file.slice(start, end);
          const chunkBytes = end - start;

          try {
            await blobApi.uploadChunk(uploadId, chunk, {
              fileName: file.name,
              partNumber,
              onUploadProgress: (e: AxiosProgressEvent) => {
                partProgress.set(partNumber, Math.min(e.loaded ?? 0, chunkBytes));
                updateProgress();
              },
              signal,
            });
            partProgress.set(partNumber, chunkBytes);
            updateProgress();
          } catch (err) {
            if (!firstError) firstError = err as Error;
            return;
          }
        }
      };

      const workers = Array.from({ length: Math.min(concurrency, totalChunks) }, () => runWorker());
      await Promise.all(workers);

      if (signal?.aborted) return null;
      if (firstError) throw firstError;

      onStatusChange?.('finalizing');
      const finalResp = await blobApi.finalizeUploadSession(uploadId, signal);
      result = finalResp.data;
    }

    onProgress?.(file.size, file.size);
    onStatusChange?.('done');
    return result;
  } catch (err: any) {
    if (signal?.aborted || err?.code === 'ERR_CANCELED') {
      onStatusChange?.('cancelled');
      return null;
    }
    onStatusChange?.('error');
    throw err;
  }
}

/**
 * Hook for uploading files with automatic parallel chunked upload for large files.
 * Tracks elapsed time and estimated time remaining (ETA).
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
  const [progress, setProgress] = useState<BlobUploadProgress>({
    loaded: 0,
    total: 0,
    percent: 0,
    elapsed: 0,
    eta: null,
  });
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const startTimeRef = useRef<number>(0);
  /** Timestamp when the first progress byte was received (0 = not yet). */
  const firstByteTimeRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressRef = useRef<{ loaded: number; total: number }>({ loaded: 0, total: 0 });

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    stopTimer();
    setStatus('idle');
    setProgress({ loaded: 0, total: 0, percent: 0, elapsed: 0, eta: null });
    setError(null);
    progressRef.current = { loaded: 0, total: 0 };
    firstByteTimeRef.current = 0;
  }, [stopTimer]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    stopTimer();
    setStatus('cancelled');
  }, [stopTimer]);

  const upload = useCallback(
    async (file: File): Promise<BlobUploadResult | null> => {
      // Reset state
      setStatus('uploading');
      setProgress({ loaded: 0, total: file.size, percent: 0, elapsed: 0, eta: null });
      setError(null);
      progressRef.current = { loaded: 0, total: file.size };
      startTimeRef.current = Date.now();
      firstByteTimeRef.current = 0;

      const controller = new AbortController();
      abortRef.current = controller;

      // Start a 1-second interval timer for elapsed/ETA updates
      stopTimer();
      timerRef.current = setInterval(() => {
        const now = Date.now();
        const elapsed = (now - startTimeRef.current) / 1000;
        const { loaded, total } = progressRef.current;
        const percent = total > 0 ? Math.round((loaded / total) * 100) : 0;
        const fbt = firstByteTimeRef.current;
        const transferElapsed = fbt > 0 ? (now - fbt) / 1000 : 0;
        const eta =
          loaded > 0 && transferElapsed > 0.5
            ? ((total - loaded) / loaded) * transferElapsed
            : null;
        setProgress({ loaded, total, percent: Math.min(percent, 99), elapsed, eta });
      }, 1000);

      try {
        const result = await uploadFileToBlob(file, {
          chunkSize,
          chunkThreshold,
          concurrency,
          signal: controller.signal,
          onProgress: (loaded, total) => {
            progressRef.current = { loaded, total };
            const now = Date.now();
            if (loaded > 0 && firstByteTimeRef.current === 0) {
              firstByteTimeRef.current = now;
            }
            const elapsed = (now - startTimeRef.current) / 1000;
            const percent = total > 0 ? Math.round((loaded / total) * 100) : 100;
            const fbt = firstByteTimeRef.current;
            const transferElapsed = fbt > 0 ? (now - fbt) / 1000 : 0;
            const eta =
              loaded > 0 && transferElapsed > 0.5
                ? ((total - loaded) / loaded) * transferElapsed
                : null;
            setProgress({ loaded, total, percent: Math.min(percent, 99), elapsed, eta });
          },
          onStatusChange: (s) => {
            if (s === 'finalizing') setStatus('finalizing');
          },
        });

        stopTimer();
        if (!result) {
          setStatus('cancelled');
          return null;
        }

        const elapsed = (Date.now() - startTimeRef.current) / 1000;
        setProgress({ loaded: file.size, total: file.size, percent: 100, elapsed, eta: 0 });
        setStatus('done');
        return result;
      } catch (err: any) {
        stopTimer();
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
    [chunkSize, chunkThreshold, concurrency, stopTimer],
  );

  return { upload, cancel, progress, status, error, reset };
}

/**
 * Compute estimated time remaining based on transfer elapsed time and progress.
 *
 * **Important:** `transferElapsed` should be the time since the first byte
 * was received — *not* total wall-clock time since upload started.  If total
 * elapsed time is used, long initial response waits (server processing,
 * connection setup) will inflate the ETA dramatically.
 *
 * Returns null if not enough data to estimate (< 0.5 s of transfer or no progress).
 */
export function computeEta(loaded: number, total: number, transferElapsed: number): number | null {
  if (loaded <= 0 || transferElapsed < 0.5 || total <= 0) return null;
  return ((total - loaded) / loaded) * transferElapsed;
}

/**
 * Format seconds into human-readable duration string.
 * Examples: "3s", "1m 25s", "2h 5m"
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return '--';
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const remainS = s % 60;
  if (m < 60) return `${m}m ${remainS}s`;
  const h = Math.floor(m / 60);
  const remainM = m % 60;
  return `${h}h ${remainM}m`;
}

/**
 * Format bytes into human-readable string.
 * Examples: "0 B", "1.5 KB", "2.3 MB", "1.0 GB"
 */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}
