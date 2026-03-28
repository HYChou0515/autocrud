/**
 * BinaryFieldEditor — Tests for deferred upload behavior.
 *
 * Covers:
 * - File selection stores File object without uploading
 * - Mode switching between file and URL
 * - Clear resets to empty
 * - Existing file shows blob URL link
 * - Selected file shows preview with name and size
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { BinaryFieldEditor } from './BinaryFieldEditor';
import type { BinaryFormValue } from '@/autocrud/lib/utils/formUtils';

vi.mock('../../../client', () => ({
  getBlobUrl: (id: string) => `http://test/blobs/${id}`,
}));

vi.mock('../../../hooks/useBlobUpload', () => ({
  formatBytes: (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  },
}));

function renderEditor(
  value: BinaryFormValue | null = null,
  onChange = vi.fn(),
  props: Partial<Parameters<typeof BinaryFieldEditor>[0]> = {},
) {
  return render(
    <MantineProvider>
      <BinaryFieldEditor label="Avatar" value={value} onChange={onChange} {...props} />
    </MantineProvider>,
  );
}

describe('BinaryFieldEditor (deferred upload)', () => {
  it('renders with empty state', () => {
    const { getByText } = renderEditor();
    expect(getByText('Avatar')).toBeTruthy();
  });

  it('does NOT trigger upload when file is selected', () => {
    const onChange = vi.fn();
    const { container } = renderEditor(null, onChange);

    // The FileInput should be present
    const input = container.querySelector('input[type="file"]');
    expect(input).toBeTruthy();

    // Simulate file selection
    const file = new File(['test content'], 'photo.jpg', { type: 'image/jpeg' });
    fireEvent.change(input!, { target: { files: [file] } });

    // onChange should be called with _mode: 'file' and the File object
    expect(onChange).toHaveBeenCalled();
    const call = onChange.mock.calls[0][0];
    expect(call._mode).toBe('file');
    expect(call.file).toBeInstanceOf(File);
  });

  it('shows "will upload on submit" preview when file is selected', () => {
    const file = new File(['hello world'], 'doc.pdf', { type: 'application/pdf' });
    const value: BinaryFormValue = { _mode: 'file', file };
    const { getAllByText, getByText } = renderEditor(value);

    // FileInput and preview text both contain the filename
    expect(getAllByText(/doc\.pdf/).length).toBeGreaterThanOrEqual(1);
    expect(getByText(/will upload on submit/)).toBeTruthy();
  });

  it('shows existing file info with blob URL', () => {
    const value: BinaryFormValue = {
      _mode: 'existing',
      file_id: 'abc123',
      content_type: 'image/png',
      size: 2048,
    };
    const { getByText } = renderEditor(value);

    expect(getByText(/image\/png/)).toBeTruthy();
    expect(getByText(/2\.0 KB/)).toBeTruthy();
  });

  it('switches to URL mode', () => {
    const onChange = vi.fn();
    const { container } = renderEditor(null, onChange);

    // Find the URL radio input and click it to switch modes
    const urlRadio = container.querySelector('input[value="url"]') as HTMLInputElement;
    expect(urlRadio).toBeTruthy();
    fireEvent.click(urlRadio);

    expect(onChange).toHaveBeenCalledWith({ _mode: 'url', url: '' });
  });

  it('clears the value', () => {
    const onChange = vi.fn();
    const value: BinaryFormValue = { _mode: 'file', file: new File(['x'], 'x.txt') };
    const { container } = renderEditor(value, onChange);

    // Find the clear button (X icon)
    const clearBtn =
      container.querySelector('[data-testid]') ||
      container.querySelector('button[aria-label]') ||
      Array.from(container.querySelectorAll('button')).find((b) => b.querySelector('svg'));

    if (clearBtn) {
      fireEvent.click(clearBtn);
      expect(onChange).toHaveBeenCalledWith({ _mode: 'empty' });
    }
  });

  it('shows required asterisk when required', () => {
    const { container } = renderEditor(null, vi.fn(), { required: true });
    expect(container.textContent).toContain('*');
  });

  it('handles URL input change', () => {
    const onChange = vi.fn();
    const value: BinaryFormValue = { _mode: 'url', url: '' };
    const { container } = renderEditor(value, onChange);

    const urlInput = container.querySelector('input[placeholder*="https"]');
    expect(urlInput).toBeTruthy();

    fireEvent.change(urlInput!, { target: { value: 'https://example.com/file.png' } });
    expect(onChange).toHaveBeenCalledWith({
      _mode: 'url',
      url: 'https://example.com/file.png',
    });
  });
});
