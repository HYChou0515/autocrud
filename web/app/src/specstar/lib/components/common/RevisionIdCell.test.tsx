/**
 * RevisionIdCell — unit tests.
 *
 * Covers:
 * - extractRevisionNumber (internal): with resourceId, without, no match
 * - RevisionIdCell component: renders "Rev #N", short ID, copy button
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { RevisionIdCell } from './RevisionIdCell';

// Mock clipboard
const mockWriteText = vi.fn().mockResolvedValue(undefined);
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: mockWriteText },
  writable: true,
  configurable: true,
});

beforeEach(() => {
  cleanup();
  mockWriteText.mockClear();
});

const wrap = (ui: React.ReactElement) => render(<MantineProvider>{ui}</MantineProvider>);

describe('RevisionIdCell', () => {
  it('displays Rev #N when resourceId matches prefix', () => {
    wrap(<RevisionIdCell revisionId="game-event:abc-123:3" resourceId="game-event:abc-123" />);
    expect(screen.getByText('Rev #3')).toBeDefined();
  });

  it('extracts revision number from trailing :N format', () => {
    wrap(<RevisionIdCell revisionId="some:prefix:uuid:42" />);
    expect(screen.getByText('Rev #42')).toBeDefined();
  });

  it('shows short ID when no revision number found', () => {
    wrap(<RevisionIdCell revisionId="abcdefghijklmnop" />);
    // 16 chars > 12, so truncated to first4...last4
    expect(screen.getByText('abcd...mnop')).toBeDefined();
  });

  it('shows full short ID', () => {
    wrap(<RevisionIdCell revisionId="short" />);
    expect(screen.getByText('short')).toBeDefined();
  });

  it('hides copy button when showCopy is false', () => {
    const { container } = wrap(<RevisionIdCell revisionId="rev:1" showCopy={false} />);
    const buttons = container.querySelectorAll('button');
    expect(buttons).toHaveLength(0);
  });

  it('copies revision ID on click', async () => {
    wrap(<RevisionIdCell revisionId="rev:1" />);
    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[0]);
    expect(mockWriteText).toHaveBeenCalledWith('rev:1');
  });
});
