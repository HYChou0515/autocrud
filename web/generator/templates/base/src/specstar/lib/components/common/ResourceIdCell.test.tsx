/**
 * ResourceIdCell — unit tests.
 *
 * Covers:
 * - Renders short ID for long IDs
 * - Renders full ID for short IDs
 * - Copy button works
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { ResourceIdCell } from './ResourceIdCell';

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

describe('ResourceIdCell', () => {
  it('truncates long ID to first4...last4', () => {
    wrap(<ResourceIdCell rid="abcdefghijklmnop" />);
    expect(screen.getByText('abcd...mnop')).toBeDefined();
  });

  it('shows full short ID', () => {
    wrap(<ResourceIdCell rid="short-id" />);
    expect(screen.getByText('short-id')).toBeDefined();
  });

  it('renders copy button and copies on click', () => {
    wrap(<ResourceIdCell rid="test-id-1234567890" />);
    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[0]);
    expect(mockWriteText).toHaveBeenCalledWith('test-id-1234567890');
  });
});
