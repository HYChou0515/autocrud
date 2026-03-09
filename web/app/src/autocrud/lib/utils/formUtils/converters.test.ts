import { describe, expect, it, vi, beforeEach } from 'vitest';
import { toLabel, fileToBase64, binaryFormValueToApi, uploadBlob } from './converters';
import type { BinaryFormValue } from './types';

// Mock the client module
vi.mock('../../client', () => ({
  client: {
    post: vi.fn(),
  },
}));

import { client } from '../../client';
const mockPost = vi.mocked(client.post);

describe('toLabel', () => {
  it('should convert snake_case to Title Case', () => {
    expect(toLabel('user_name')).toBe('User Name');
    expect(toLabel('api_key')).toBe('Api Key');
    expect(toLabel('created_at')).toBe('Created At');
  });

  it('should convert kebab-case to Title Case', () => {
    expect(toLabel('first-name')).toBe('First Name');
    expect(toLabel('last-name')).toBe('Last Name');
  });

  it('should handle mixed delimiters', () => {
    expect(toLabel('user_name-id')).toBe('User Name Id');
  });

  it('should handle single word', () => {
    expect(toLabel('name')).toBe('Name');
  });

  it('should handle already capitalized word', () => {
    expect(toLabel('User')).toBe('User');
  });

  it('should handle empty string', () => {
    expect(toLabel('')).toBe('');
  });

  it('should handle multiple underscores', () => {
    // Multiple consecutive underscores are treated as a single delimiter
    expect(toLabel('user__name')).toBe('User Name');
  });
});

describe('fileToBase64', () => {
  beforeEach(() => {
    // Reset FileReader mocks before each test
    vi.resetAllMocks();
  });

  it('should convert file to base64 string', async () => {
    const file = new File(['hello world'], 'test.txt', { type: 'text/plain' });
    const base64 = await fileToBase64(file);

    // Expected base64: 'aGVsbG8gd29ybGQ=' (base64 of 'hello world')
    expect(base64).toBe('aGVsbG8gd29ybGQ=');
  });

  it('should strip data URL prefix', async () => {
    const file = new File(['test'], 'test.txt', { type: 'text/plain' });
    const base64 = await fileToBase64(file);

    // Should not contain 'data:' prefix
    expect(base64).not.toContain('data:');
    expect(base64).not.toContain('base64,');
  });

  it('should handle empty file', async () => {
    const file = new File([], 'empty.txt', { type: 'text/plain' });
    const base64 = await fileToBase64(file);

    // Empty file should return empty base64 or small string
    expect(typeof base64).toBe('string');
  });

  it('should handle binary file', async () => {
    const buffer = new Uint8Array([0x89, 0x50, 0x4e, 0x47]); // PNG header
    const file = new File([buffer], 'image.png', { type: 'image/png' });
    const base64 = await fileToBase64(file);

    expect(typeof base64).toBe('string');
    expect(base64.length).toBeGreaterThan(0);
  });

  it('should reject on FileReader error', async () => {
    const file = new File(['test'], 'test.txt', { type: 'text/plain' });

    // Mock FileReader to simulate error
    const originalFileReader = global.FileReader;
    global.FileReader = vi.fn().mockImplementation(() => ({
      readAsDataURL: function () {
        setTimeout(() => this.onerror(new Error('Read error')), 0);
      },
      onerror: null,
      onload: null,
      result: null,
    })) as any;

    await expect(fileToBase64(file)).rejects.toThrow();

    // Restore original FileReader
    global.FileReader = originalFileReader;
  });
});

describe('binaryFormValueToApi', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('should return null for empty mode', async () => {
    const val: BinaryFormValue = { _mode: 'empty' };
    const result = await binaryFormValueToApi(val);
    expect(result).toBeNull();
  });

  it('should return null for null input', async () => {
    const result = await binaryFormValueToApi(null);
    expect(result).toBeNull();
  });

  it('should return null for undefined input', async () => {
    const result = await binaryFormValueToApi(undefined);
    expect(result).toBeNull();
  });

  it('should preserve file_id for existing mode', async () => {
    const val: BinaryFormValue = {
      _mode: 'existing',
      file_id: 'abc123',
      content_type: 'image/png',
      size: 1024,
    };
    const result = await binaryFormValueToApi(val);
    expect(result).toEqual({ file_id: 'abc123' });
  });

  it('should upload file and return file_id for file mode', async () => {
    const file = new File(['test content'], 'test.txt', { type: 'text/plain' });
    const val: BinaryFormValue = { _mode: 'file', file };

    mockPost.mockResolvedValue({
      data: { file_id: 'uploaded-abc', size: 12, content_type: 'text/plain' },
    });

    const result = await binaryFormValueToApi(val);

    expect(mockPost).toHaveBeenCalledWith('/blobs/upload', expect.any(FormData), {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    expect(result).toHaveProperty('file_id', 'uploaded-abc');
    expect(result).toHaveProperty('content_type', 'text/plain');
    expect(result).toHaveProperty('size', 12);
  });

  it('should use default content_type for file without type', async () => {
    const file = new File(['test'], 'test.bin', { type: '' });
    const val: BinaryFormValue = { _mode: 'file', file };

    mockPost.mockResolvedValue({
      data: { file_id: 'uploaded-def', size: 4, content_type: 'application/octet-stream' },
    });

    const result = await binaryFormValueToApi(val);

    expect(result?.content_type).toBe('application/octet-stream');
  });

  it('should return null for file mode without file', async () => {
    const val: BinaryFormValue = { _mode: 'file', file: null };
    const result = await binaryFormValueToApi(val);
    expect(result).toBeNull();
  });

  it('should fetch URL and upload for url mode', async () => {
    const mockBlob = new Blob(['url content'], { type: 'text/html' });
    global.fetch = vi.fn().mockResolvedValue({
      blob: () => Promise.resolve(mockBlob),
    });

    mockPost.mockResolvedValue({
      data: { file_id: 'url-uploaded-abc', size: 11, content_type: 'text/html' },
    });

    const val: BinaryFormValue = { _mode: 'url', url: 'https://example.com/file.html' };
    const result = await binaryFormValueToApi(val);

    expect(global.fetch).toHaveBeenCalledWith('https://example.com/file.html');
    expect(mockPost).toHaveBeenCalledWith('/blobs/upload', expect.any(FormData), {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    expect(result).toHaveProperty('file_id', 'url-uploaded-abc');
    expect(result).toHaveProperty('content_type', 'text/html');
  });

  it('should use default content_type for URL with unknown type', async () => {
    const mockBlob = new Blob(['content'], { type: '' });
    global.fetch = vi.fn().mockResolvedValue({
      blob: () => Promise.resolve(mockBlob),
    });

    mockPost.mockResolvedValue({
      data: { file_id: 'url-uploaded-def', size: 7, content_type: 'application/octet-stream' },
    });

    const val: BinaryFormValue = { _mode: 'url', url: 'https://example.com/file' };
    const result = await binaryFormValueToApi(val);

    expect(result?.content_type).toBe('application/octet-stream');
  });

  it('should return null for url mode on fetch failure', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

    const val: BinaryFormValue = { _mode: 'url', url: 'https://invalid.com/file' };
    const result = await binaryFormValueToApi(val);

    expect(result).toBeNull();
  });

  it('should return null for url mode without url', async () => {
    const val: BinaryFormValue = { _mode: 'url', url: '' };
    const result = await binaryFormValueToApi(val);
    expect(result).toBeNull();
  });

  it('should throw on upload failure for file mode', async () => {
    const file = new File(['test'], 'test.txt', { type: 'text/plain' });
    const val: BinaryFormValue = { _mode: 'file', file };

    mockPost.mockRejectedValue(new Error('Upload failed'));

    await expect(binaryFormValueToApi(val)).rejects.toThrow('Upload failed');
  });
});

describe('uploadBlob', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('should POST file as FormData to /blobs/upload', async () => {
    const file = new File(['hello'], 'hello.txt', { type: 'text/plain' });

    mockPost.mockResolvedValue({
      data: { file_id: 'blob-123', size: 5, content_type: 'text/plain' },
    });

    const result = await uploadBlob(file);

    expect(mockPost).toHaveBeenCalledWith('/blobs/upload', expect.any(FormData), {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    expect(result).toEqual({
      file_id: 'blob-123',
      size: 5,
      content_type: 'text/plain',
    });
  });

  it('should propagate upload errors', async () => {
    const file = new File(['data'], 'data.bin', { type: 'application/octet-stream' });

    mockPost.mockRejectedValue(new Error('Network error'));

    await expect(uploadBlob(file)).rejects.toThrow('Network error');
  });
});
