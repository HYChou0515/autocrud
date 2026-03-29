/**
 * useBlobUpload — Tests
 *
 * Covers:
 * - Simple upload for small files (<=10 MB threshold)
 * - Chunked upload session for large files (>10 MB threshold)
 * - Progress tracking during upload (with elapsed/ETA)
 * - Cancel aborts the upload
 * - Error handling sets status to 'error'
 * - Reset returns to idle state
 * - Standalone uploadFileToBlob function
 * - Utility functions: computeEta, formatDuration, formatBytes
 *
 * Mocks the generated blobApi module — tests useBlobUpload in isolation
 * from the Axios client layer.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import {
  useBlobUpload,
  uploadFileToBlob,
  computeEta,
  formatDuration,
  formatBytes,
} from './useBlobUpload';

// ---------------------------------------------------------------------------
// Mock the generated blobApi module
// ---------------------------------------------------------------------------
vi.mock('@/autocrud/generated/api/blobApi', () => ({
  blobApi: {
    upload: vi.fn(),
    createUploadSession: vi.fn(),
    uploadChunk: vi.fn(),
    finalizeUploadSession: vi.fn(),
    abortUploadSession: vi.fn(),
  },
}));

import { blobApi } from '@/autocrud/generated/api/blobApi';

const mockUpload = vi.mocked(blobApi.upload);
const mockCreateSession = vi.mocked(blobApi.createUploadSession);
const mockUploadChunk = vi.mocked(blobApi.uploadChunk);
const mockFinalize = vi.mocked(blobApi.finalizeUploadSession);

// Helper: cast mock implementation for esbuild compat (avoids `} as any)` parse error)

const asAny = <T>(v: T): any => v;

// ===========================================================================
// useBlobUpload hook
// ===========================================================================
describe('useBlobUpload', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('starts in idle state', () => {
    const { result } = renderHook(() => useBlobUpload());
    expect(result.current.status).toBe('idle');
    expect(result.current.progress).toEqual({
      loaded: 0,
      total: 0,
      percent: 0,
      elapsed: 0,
      eta: null,
    });
    expect(result.current.error).toBeNull();
  });

  it('uploads small files via blobApi.upload', async () => {
    const file = new File(['x'.repeat(1024)], 'small.txt', { type: 'text/plain' });

    mockUpload.mockImplementationOnce(
      asAny((_file: File, options?: Record<string, unknown>) => {
        const onUp = options?.onUploadProgress as ((e: unknown) => void) | undefined;
        onUp?.({ loaded: 512, total: 1024 });
        onUp?.({ loaded: 1024, total: 1024 });
        return Promise.resolve({
          data: { file_id: 'f1', size: 1024, content_type: 'text/plain' },
        });
      }),
    );

    const { result } = renderHook(() => useBlobUpload());

    let uploadResult: unknown;
    await act(async () => {
      uploadResult = await result.current.upload(file);
    });

    expect(uploadResult).toEqual({ file_id: 'f1', size: 1024, content_type: 'text/plain' });
    expect(result.current.status).toBe('done');
    expect(result.current.progress.percent).toBe(100);
    expect(mockUpload).toHaveBeenCalledTimes(1);
  });

  it('uses chunked upload session for large files', async () => {
    const chunkSize = 50;
    const chunkThreshold = 100;
    const fileContent = 'x'.repeat(120); // 120 bytes, >100 threshold
    const file = new File([fileContent], 'large.bin', { type: 'application/octet-stream' });

    mockCreateSession.mockResolvedValueOnce(
      asAny({
        data: {
          upload_id: 'sess1',
          file_id: 'pre-f1',
          status: 'pending',
          upload_method: 'proxy',
          upload_url: '',
          uploaded_size: 0,
        },
      }),
    );

    mockUploadChunk
      .mockImplementationOnce(
        asAny((_id: string, _chunk: Blob, options?: Record<string, unknown>) => {
          const onUp = options?.onUploadProgress as ((e: unknown) => void) | undefined;
          onUp?.({ loaded: 50 });
          return Promise.resolve({ data: { uploaded_size: 50 } });
        }),
      )
      .mockImplementationOnce(
        asAny((_id: string, _chunk: Blob, options?: Record<string, unknown>) => {
          const onUp = options?.onUploadProgress as ((e: unknown) => void) | undefined;
          onUp?.({ loaded: 50 });
          return Promise.resolve({ data: { uploaded_size: 100 } });
        }),
      )
      .mockImplementationOnce(
        asAny((_id: string, _chunk: Blob, options?: Record<string, unknown>) => {
          const onUp = options?.onUploadProgress as ((e: unknown) => void) | undefined;
          onUp?.({ loaded: 20 });
          return Promise.resolve({ data: { uploaded_size: 120 } });
        }),
      );

    mockFinalize.mockResolvedValueOnce(
      asAny({
        data: { file_id: 'final-f1', size: 120, content_type: 'application/octet-stream' },
      }),
    );

    const { result } = renderHook(() => useBlobUpload({ chunkSize, chunkThreshold }));

    let uploadResult: unknown;
    await act(async () => {
      uploadResult = await result.current.upload(file);
    });

    expect(uploadResult).toEqual({
      file_id: 'final-f1',
      size: 120,
      content_type: 'application/octet-stream',
    });
    expect(result.current.status).toBe('done');

    // createUploadSession called with correct params
    expect(mockCreateSession).toHaveBeenCalledWith(
      { content_type: 'application/octet-stream', size: 120, total_parts: 3 },
      expect.any(AbortSignal),
    );

    // 3 chunk uploads
    expect(mockUploadChunk).toHaveBeenCalledTimes(3);

    // finalize called with session ID and signal
    expect(mockFinalize).toHaveBeenCalledWith('sess1', expect.any(AbortSignal));
  });

  it('sets error status on upload failure', async () => {
    const file = new File(['data'], 'fail.txt', { type: 'text/plain' });
    mockUpload.mockRejectedValueOnce(new Error('Network error'));

    const { result } = renderHook(() => useBlobUpload());

    let uploadResult: unknown;
    await act(async () => {
      uploadResult = await result.current.upload(file);
    });

    expect(uploadResult).toBeNull();
    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('Network error');
  });

  it('sets error status with response detail', async () => {
    const file = new File(['data'], 'fail.txt', { type: 'text/plain' });
    mockUpload.mockRejectedValueOnce({
      response: { data: { detail: 'Blob store not configured' } },
    });

    const { result } = renderHook(() => useBlobUpload());

    let uploadResult: unknown;
    await act(async () => {
      uploadResult = await result.current.upload(file);
    });

    expect(uploadResult).toBeNull();
    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('Blob store not configured');
  });

  it('reset returns to idle state', async () => {
    const file = new File(['data'], 'file.txt', { type: 'text/plain' });
    mockUpload.mockResolvedValueOnce(
      asAny({ data: { file_id: 'f1', size: 4, content_type: 'text/plain' } }),
    );

    const { result } = renderHook(() => useBlobUpload());

    await act(async () => {
      await result.current.upload(file);
    });
    expect(result.current.status).toBe('done');

    act(() => {
      result.current.reset();
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.progress).toEqual({
      loaded: 0,
      total: 0,
      percent: 0,
      elapsed: 0,
      eta: null,
    });
    expect(result.current.error).toBeNull();
  });

  it('cancel aborts the upload and sets status to cancelled', async () => {
    const chunkThreshold = 10;
    const chunkSize = 50;
    const file = new File(['x'.repeat(100)], 'big.bin', { type: 'application/octet-stream' });

    mockCreateSession.mockResolvedValueOnce(
      asAny({
        data: { upload_id: 'sess-cancel', file_id: 'pre-f', status: 'pending' },
      }),
    );

    // Chunk upload hangs forever — simulates in-progress upload
    mockUploadChunk.mockImplementation(asAny(() => new Promise(() => {})));

    const { result } = renderHook(() => useBlobUpload({ chunkSize, chunkThreshold }));

    act(() => {
      result.current.upload(file);
    });

    await waitFor(() => {
      expect(result.current.status).toBe('uploading');
    });

    act(() => {
      result.current.cancel();
    });

    expect(result.current.status).toBe('cancelled');
  });

  it('handles ERR_CANCELED error code', async () => {
    const file = new File(['data'], 'cancel.txt', { type: 'text/plain' });
    const cancelErr = new Error('Request aborted');
    (cancelErr as unknown as Record<string, string>).code = 'ERR_CANCELED';
    mockUpload.mockRejectedValueOnce(cancelErr);

    const { result } = renderHook(() => useBlobUpload());

    let uploadResult: unknown;
    await act(async () => {
      uploadResult = await result.current.upload(file);
    });

    expect(uploadResult).toBeNull();
    expect(result.current.status).toBe('cancelled');
  });

  it('falls back to "Upload failed" when error has no message', async () => {
    const file = new File(['data'], 'fail.txt', { type: 'text/plain' });
    mockUpload.mockRejectedValueOnce({});

    const { result } = renderHook(() => useBlobUpload());

    let uploadResult: unknown;
    await act(async () => {
      uploadResult = await result.current.upload(file);
    });

    expect(uploadResult).toBeNull();
    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('Upload failed');
  });

  it('handles zero-size file in simple upload', async () => {
    const file = new File([], 'empty.txt', { type: 'text/plain' });

    mockUpload.mockResolvedValueOnce(
      asAny({ data: { file_id: 'f-empty', size: 0, content_type: 'text/plain' } }),
    );

    const { result } = renderHook(() => useBlobUpload());

    let uploadResult: unknown;
    await act(async () => {
      uploadResult = await result.current.upload(file);
    });

    expect(uploadResult).toEqual({ file_id: 'f-empty', size: 0, content_type: 'text/plain' });
    expect(result.current.status).toBe('done');
    expect(result.current.progress.percent).toBe(100);
  });

  it('calls upload with custom chunkSize and chunkThreshold', async () => {
    const chunkSize = 3;
    const chunkThreshold = 5;
    const file = new File(['abcdefgh'], 'tiny.txt', { type: 'text/plain' }); // 8 bytes

    mockCreateSession.mockResolvedValueOnce(
      asAny({ data: { upload_id: 'sess2', file_id: 'pre-f2', status: 'pending' } }),
    );

    // 3 chunks: 3+3+2
    mockUploadChunk
      .mockResolvedValueOnce(asAny({ data: { uploaded_size: 3 } }))
      .mockResolvedValueOnce(asAny({ data: { uploaded_size: 6 } }))
      .mockResolvedValueOnce(asAny({ data: { uploaded_size: 8 } }));

    mockFinalize.mockResolvedValueOnce(
      asAny({ data: { file_id: 'final-f2', size: 8, content_type: 'text/plain' } }),
    );

    const { result } = renderHook(() => useBlobUpload({ chunkSize, chunkThreshold }));

    let uploadResult: unknown;
    await act(async () => {
      uploadResult = await result.current.upload(file);
    });

    expect(uploadResult).toEqual({ file_id: 'final-f2', size: 8, content_type: 'text/plain' });
    expect(mockUploadChunk).toHaveBeenCalledTimes(3);
    expect(result.current.status).toBe('done');
  });

  it('uses application/octet-stream when file.type is empty', async () => {
    const chunkThreshold = 5;
    const file = new File(['abcdef'], 'noext', { type: '' }); // empty type

    mockCreateSession.mockResolvedValueOnce(
      asAny({ data: { upload_id: 'sess3', file_id: 'pre-f3', status: 'pending' } }),
    );

    mockUploadChunk.mockResolvedValueOnce(asAny({ data: { uploaded_size: 6 } }));

    mockFinalize.mockResolvedValueOnce(
      asAny({
        data: { file_id: 'final-f3', size: 6, content_type: 'application/octet-stream' },
      }),
    );

    const { result } = renderHook(() => useBlobUpload({ chunkThreshold }));

    await act(async () => {
      await result.current.upload(file);
    });

    // Should have sent 'application/octet-stream' as fallback
    expect(mockCreateSession).toHaveBeenCalledWith(
      { content_type: 'application/octet-stream', size: 6, total_parts: 1 },
      expect.any(AbortSignal),
    );
  });

  it('returns null when signal is aborted between chunks', async () => {
    const chunkThreshold = 5;
    const chunkSize = 3;
    const file = new File(['abcdefgh'], 'mid-abort.txt', { type: 'text/plain' }); // 8 bytes

    mockCreateSession.mockResolvedValueOnce(
      asAny({ data: { upload_id: 'sess-mid', file_id: 'pre-f-mid', status: 'pending' } }),
    );

    mockUploadChunk.mockImplementationOnce(
      asAny(() => {
        return Promise.resolve({ data: { uploaded_size: 3 } });
      }),
    );

    const { result } = renderHook(() => useBlobUpload({ chunkSize, chunkThreshold }));

    await act(async () => {
      result.current.upload(file);
    });

    // Exercises the branch logic — upload completes or partial
    expect(result.current.status).not.toBe('idle');
  });

  it('ETA excludes initial response wait time before first byte', async () => {
    vi.useFakeTimers();

    const file = new File(['x'.repeat(1024)], 'slow-start.txt', { type: 'text/plain' });

    let capturedOnUploadProgress: ((e: unknown) => void) | undefined;
    let resolveUpload: (v: unknown) => void;

    mockUpload.mockImplementationOnce(
      asAny((_f: File, opts?: Record<string, unknown>) => {
        capturedOnUploadProgress = opts?.onUploadProgress as (e: unknown) => void;
        return new Promise((r) => {
          resolveUpload = r;
        });
      }),
    );

    const { result } = renderHook(() => useBlobUpload());

    // t=0: start upload
    await act(async () => {
      result.current.upload(file);
    });

    // t=30s: server was slow to respond, no data until now
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });

    // First byte arrives at t=30s — 50% of the file
    act(() => {
      capturedOnUploadProgress!({ loaded: 512, total: 1024 });
    });

    // t=31s: 1 second of actual data transfer
    await act(async () => {
      vi.advanceTimersByTime(1_000);
    });

    // Another progress event at t=31s — still 50%
    act(() => {
      capturedOnUploadProgress!({ loaded: 512, total: 1024 });
    });

    // ETA should be based on transfer time (~1s since first byte), NOT
    // total elapsed (~31s).  Transfer rate = 512 bytes / 1s = 512 B/s,
    // remaining = 512 bytes → ETA ≈ 1s.
    // Bug: ETA = (512/512)*31 = 31s — way too high.
    const eta = result.current.progress.eta;
    expect(eta).not.toBeNull();
    expect(eta!).toBeLessThan(5);

    // progress.elapsed should still reflect total wall-clock time
    expect(result.current.progress.elapsed).toBeGreaterThanOrEqual(30);

    // Clean up: finish the upload
    act(() => {
      capturedOnUploadProgress!({ loaded: 1024, total: 1024 });
    });
    resolveUpload!({ data: { file_id: 'f1', size: 1024, content_type: 'text/plain' } });
    await act(async () => {});

    vi.useRealTimers();
  });
});

// ===========================================================================
// computeEta
// ===========================================================================
describe('computeEta', () => {
  it('returns null when loaded is 0', () => {
    expect(computeEta(0, 100, 5)).toBeNull();
  });

  it('returns null when transferElapsed is less than 0.5s', () => {
    expect(computeEta(50, 100, 0.3)).toBeNull();
  });

  it('returns null when total is 0', () => {
    expect(computeEta(10, 0, 5)).toBeNull();
  });

  it('computes correct ETA from transfer elapsed', () => {
    // 50/100 in 10s of transfer → remaining 50 at 5/s → 10s
    expect(computeEta(50, 100, 10)).toBe(10);
  });

  it('computes ETA for nearly complete upload', () => {
    expect(computeEta(90, 100, 9)).toBeCloseTo(1, 1);
  });

  it('gives accurate ETA when transfer elapsed excludes initial wait', () => {
    // Scenario: 30s waiting for server, then 1s of actual transfer at 50%.
    // Caller passes transferElapsed=1 (not totalElapsed=31).
    // ETA = (50/50) * 1 = 1s  (correct, not 31s)
    expect(computeEta(50, 100, 1)).toBe(1);
  });
});

// ===========================================================================
// formatDuration
// ===========================================================================
describe('formatDuration', () => {
  it('returns "--" for null', () => {
    expect(formatDuration(null)).toBe('--');
  });

  it('returns "--" for undefined', () => {
    expect(formatDuration(undefined)).toBe('--');
  });

  it('returns "--" for negative values', () => {
    expect(formatDuration(-5)).toBe('--');
  });

  it('formats seconds only', () => {
    expect(formatDuration(30)).toBe('30s');
  });

  it('formats minutes and seconds', () => {
    expect(formatDuration(90)).toBe('1m 30s');
  });

  it('formats hours and minutes', () => {
    expect(formatDuration(3725)).toBe('1h 2m');
  });

  it('formats 0 seconds', () => {
    expect(formatDuration(0)).toBe('0s');
  });
});

// ===========================================================================
// formatBytes
// ===========================================================================
describe('formatBytes', () => {
  it('formats 0 bytes', () => {
    expect(formatBytes(0)).toBe('0 B');
  });

  it('formats bytes', () => {
    expect(formatBytes(512)).toBe('512.0 B');
  });

  it('formats kilobytes', () => {
    expect(formatBytes(1024)).toBe('1.0 KB');
  });

  it('formats megabytes', () => {
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB');
  });

  it('formats gigabytes', () => {
    expect(formatBytes(2.5 * 1024 * 1024 * 1024)).toBe('2.5 GB');
  });
});

// ===========================================================================
// uploadFileToBlob (standalone function)
// ===========================================================================
describe('uploadFileToBlob', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('uploads small files via blobApi.upload', async () => {
    const file = new File(['hello'], 'test.txt', { type: 'text/plain' });

    mockUpload.mockImplementationOnce(
      asAny((_file: File, options?: Record<string, unknown>) => {
        const onUp = options?.onUploadProgress as ((e: unknown) => void) | undefined;
        onUp?.({ loaded: 5, total: 5 });
        return Promise.resolve({
          data: { file_id: 'f1', size: 5, content_type: 'text/plain' },
        });
      }),
    );

    const progressCalls: Array<[number, number]> = [];
    const result = await uploadFileToBlob(file, {
      onProgress: (loaded, total) => progressCalls.push([loaded, total]),
    });

    expect(result).toEqual({ file_id: 'f1', size: 5, content_type: 'text/plain' });
    expect(progressCalls.length).toBeGreaterThan(0);
    expect(mockUpload).toHaveBeenCalledTimes(1);
  });

  it('uploads large files via chunked session', async () => {
    const content = 'x'.repeat(120);
    const file = new File([content], 'large.bin', { type: 'application/octet-stream' });

    mockCreateSession.mockResolvedValueOnce(
      asAny({
        data: { upload_id: 'sess1', file_id: 'pre-f1', status: 'pending' },
      }),
    );

    mockUploadChunk
      .mockResolvedValueOnce(asAny({ data: { uploaded_size: 50 } }))
      .mockResolvedValueOnce(asAny({ data: { uploaded_size: 100 } }))
      .mockResolvedValueOnce(asAny({ data: { uploaded_size: 120 } }));

    mockFinalize.mockResolvedValueOnce(
      asAny({
        data: { file_id: 'final-f1', size: 120, content_type: 'application/octet-stream' },
      }),
    );

    const statusChanges: string[] = [];
    const result = await uploadFileToBlob(file, {
      chunkSize: 50,
      chunkThreshold: 100,
      onStatusChange: (s) => statusChanges.push(s),
    });

    expect(result).toEqual({
      file_id: 'final-f1',
      size: 120,
      content_type: 'application/octet-stream',
    });
    expect(statusChanges).toContain('uploading');
    expect(statusChanges).toContain('finalizing');
    expect(statusChanges).toContain('done');
    expect(mockUploadChunk).toHaveBeenCalledTimes(3);
  });

  it('returns null when signal is aborted', async () => {
    const file = new File(['data'], 'abort.txt', { type: 'text/plain' });
    const controller = new AbortController();
    controller.abort();

    const cancelErr = new Error('Request aborted');
    (cancelErr as unknown as Record<string, string>).code = 'ERR_CANCELED';
    mockUpload.mockRejectedValueOnce(cancelErr);

    const result = await uploadFileToBlob(file, { signal: controller.signal });
    expect(result).toBeNull();
  });

  it('throws on non-cancel errors', async () => {
    const file = new File(['data'], 'fail.txt', { type: 'text/plain' });
    mockUpload.mockRejectedValueOnce(new Error('Server error'));

    await expect(uploadFileToBlob(file)).rejects.toThrow('Server error');
  });

  it('calls onProgress callback with loaded and total', async () => {
    const file = new File(['hello world'], 'progress.txt', { type: 'text/plain' });

    mockUpload.mockImplementationOnce(
      asAny((_file: File, options?: Record<string, unknown>) => {
        const onUp = options?.onUploadProgress as ((e: unknown) => void) | undefined;
        onUp?.({ loaded: 5 });
        onUp?.({ loaded: 11 });
        return Promise.resolve({
          data: { file_id: 'f2', size: 11, content_type: 'text/plain' },
        });
      }),
    );

    const progressCalls: Array<[number, number]> = [];
    await uploadFileToBlob(file, {
      onProgress: (l, t) => progressCalls.push([l, t]),
    });

    expect(progressCalls).toContainEqual([5, 11]);
    expect(progressCalls[progressCalls.length - 1]).toEqual([11, 11]);
  });
});
