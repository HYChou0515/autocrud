import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { BinaryFieldDisplay } from './BinaryFieldDisplay';

vi.mock('../../../client', () => ({
  getBlobUrl: (id: string) => `/api/blob/${id}`,
}));

beforeEach(() => cleanup());

function renderDisplay(value: Record<string, unknown>) {
  return render(
    <MantineProvider>
      <BinaryFieldDisplay value={value} />
    </MantineProvider>,
  );
}

describe('BinaryFieldDisplay', () => {
  it('renders image preview for image content types', () => {
    const { container } = renderDisplay({
      file_id: 'img-1',
      content_type: 'image/png',
      size: 2048,
    });
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('src')).toBe('/api/blob/img-1');
    expect(screen.getByText('Download')).toBeTruthy();
    expect(screen.getByText(/2\.0 KB/)).toBeTruthy();
  });

  it('renders image preview for image/jpeg', () => {
    const { container } = renderDisplay({
      file_id: 'img-2',
      content_type: 'image/jpeg',
      size: 1000,
    });
    expect(container.querySelector('img')).not.toBeNull();
  });

  it('renders file download for non-image types', () => {
    const { container } = renderDisplay({
      file_id: 'doc-1',
      content_type: 'application/pdf',
      size: 1024 * 1024 * 3,
    });
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('Download')).toBeTruthy();
    expect(screen.getByText(/application\/pdf/)).toBeTruthy();
    expect(screen.getByText(/3\.0 MB/)).toBeTruthy();
  });

  it('renders "File" when content_type is undefined', () => {
    renderDisplay({
      file_id: 'unknown-1',
      content_type: undefined,
      size: 512,
    });
    expect(screen.getByText(/File/)).toBeTruthy();
    expect(screen.getByText(/512 B/)).toBeTruthy();
  });

  it('renders download anchor with correct href', () => {
    const { container } = renderDisplay({
      file_id: 'abc',
      content_type: 'text/plain',
      size: 100,
    });
    const anchor = container.querySelector('a');
    expect(anchor).not.toBeNull();
    expect(anchor?.getAttribute('href')).toBe('/api/blob/abc');
    expect(anchor?.getAttribute('target')).toBe('_blank');
  });
});
