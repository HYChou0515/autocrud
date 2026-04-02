/**
 * RefLink — unit tests.
 *
 * Covers:
 * - parseRevisionRef: pure function tests
 * - RefLink: renders link or N/A
 * - RefLinkList: renders list, expand/collapse
 * - RefRevisionLink: renders with revisionId parsing
 * - RefRevisionLinkList: renders list
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';

// Mock router
vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to, params, search, ...rest }: any) => (
    <a href={to} data-params={JSON.stringify(params)} data-search={JSON.stringify(search)} {...rest}>
      {children}
    </a>
  ),
}));

// Mock generated resources
vi.mock('../../../generated/resources', () => ({
  getResourceDetailRoute: (name: string) => `/autocrud-admin/${name}/$resourceId`,
}));

// Mock clipboard
const mockWriteText = vi.fn().mockResolvedValue(undefined);
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: mockWriteText },
  writable: true,
  configurable: true,
});

import {
  RefLink,
  RefLinkList,
  RefRevisionLink,
  RefRevisionLinkList,
  parseRevisionRef,
} from './RefLink';
import type { FieldRef } from '../../resources';

beforeEach(() => {
  cleanup();
  mockWriteText.mockClear();
});

const wrap = (ui: React.ReactElement) => render(<MantineProvider>{ui}</MantineProvider>);
const fieldRef: FieldRef = { resource: 'character', type: 'resource_id' };
const revRef: FieldRef = { resource: 'character', type: 'revision_id' };

// ---------------------------------------------------------------------------
// parseRevisionRef (pure function)
// ---------------------------------------------------------------------------

describe('parseRevisionRef', () => {
  it('parses revision_id format (ends with :number)', () => {
    const result = parseRevisionRef('prefix:uuid:3');
    expect(result.resourceId).toBe('prefix:uuid');
    expect(result.revisionId).toBe('prefix:uuid:3');
  });

  it('treats plain resource_id (no trailing number)', () => {
    const result = parseRevisionRef('prefix:uuid-value');
    expect(result.resourceId).toBe('prefix:uuid-value');
    expect(result.revisionId).toBeNull();
  });

  it('handles single-segment value', () => {
    const result = parseRevisionRef('simple-id');
    expect(result.resourceId).toBe('simple-id');
    expect(result.revisionId).toBeNull();
  });

  it('handles multi-digit revision number', () => {
    const result = parseRevisionRef('a:b:12345');
    expect(result.resourceId).toBe('a:b');
    expect(result.revisionId).toBe('a:b:12345');
  });

  it('handles zero revision number', () => {
    const result = parseRevisionRef('a:0');
    expect(result.resourceId).toBe('a');
    expect(result.revisionId).toBe('a:0');
  });
});

// ---------------------------------------------------------------------------
// RefLink
// ---------------------------------------------------------------------------

describe('RefLink', () => {
  it('renders N/A for null value', () => {
    wrap(<RefLink value={null} fieldRef={fieldRef} />);
    expect(screen.getByText('N/A')).toBeDefined();
  });

  it('renders N/A for undefined value', () => {
    wrap(<RefLink value={undefined} fieldRef={fieldRef} />);
    expect(screen.getByText('N/A')).toBeDefined();
  });

  it('renders short ID with link', () => {
    wrap(<RefLink value="abcdefghijklmnop" fieldRef={fieldRef} />);
    expect(screen.getByText('abcd...mnop')).toBeDefined();
  });

  it('renders full short ID', () => {
    wrap(<RefLink value="short" fieldRef={fieldRef} />);
    expect(screen.getByText('short')).toBeDefined();
  });

  it('has copy button that copies value', () => {
    wrap(<RefLink value="test-id" fieldRef={fieldRef} />);
    const buttons = screen.getAllByRole('button');
    // The last button is the copy button
    fireEvent.click(buttons[buttons.length - 1]);
    expect(mockWriteText).toHaveBeenCalledWith('test-id');
  });

  it('link click/pointerDown handlers call stopPropagation', () => {
    const { container } = wrap(<RefLink value="abc123" fieldRef={fieldRef} />);
    const link = container.querySelector('a')!;
    const clickEvent = new MouseEvent('click', { bubbles: true });
    const stopSpy = vi.spyOn(clickEvent, 'stopPropagation');
    link.dispatchEvent(clickEvent);
    expect(stopSpy).toHaveBeenCalled();
  });

  it('copy button resets after timeout', () => {
    vi.useFakeTimers();
    wrap(<RefLink value="timer-id" fieldRef={fieldRef} />);
    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[buttons.length - 1]);
    vi.advanceTimersByTime(2000);
    vi.useRealTimers();
    // Just ensure no error — the setTimeout callback ran
    expect(mockWriteText).toHaveBeenCalledWith('timer-id');
  });
});

// ---------------------------------------------------------------------------
// RefLinkList
// ---------------------------------------------------------------------------

describe('RefLinkList', () => {
  it('renders empty text for null values', () => {
    wrap(<RefLinkList values={null} fieldRef={fieldRef} />);
    expect(screen.getByText('（空）')).toBeDefined();
  });

  it('renders empty text for empty array', () => {
    wrap(<RefLinkList values={[]} fieldRef={fieldRef} />);
    expect(screen.getByText('（空）')).toBeDefined();
  });

  it('renders list of links', () => {
    wrap(<RefLinkList values={['id-1', 'id-2']} fieldRef={fieldRef} />);
    expect(screen.getByText('id-1')).toBeDefined();
    expect(screen.getByText('id-2')).toBeDefined();
  });

  it('shows expand link when more than maxVisible', () => {
    const values = ['a', 'b', 'c', 'd', 'e', 'f'];
    wrap(<RefLinkList values={values} fieldRef={fieldRef} maxVisible={3} />);
    expect(screen.getByText('+3 more...')).toBeDefined();
  });

  it('expands and collapses', () => {
    const values = ['a', 'b', 'c', 'd'];
    wrap(<RefLinkList values={values} fieldRef={fieldRef} maxVisible={2} />);

    fireEvent.click(screen.getByText('+2 more...'));
    expect(screen.getByText('收起')).toBeDefined();

    fireEvent.click(screen.getByText('收起'));
    expect(screen.getByText('+2 more...')).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// RefRevisionLink
// ---------------------------------------------------------------------------

describe('RefRevisionLink', () => {
  it('renders N/A for null value', () => {
    wrap(<RefRevisionLink value={null} fieldRef={revRef} />);
    expect(screen.getByText('N/A')).toBeDefined();
  });

  it('renders link for revision ID', () => {
    const { container } = wrap(<RefRevisionLink value="res:uuid:5" fieldRef={revRef} />);
    // Should show some code element with the short ID
    const codes = container.querySelectorAll('code');
    expect(codes.length).toBeGreaterThan(0);
  });

  it('has copy button', () => {
    wrap(<RefRevisionLink value="res:uuid:5" fieldRef={revRef} />);
    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[buttons.length - 1]);
    expect(mockWriteText).toHaveBeenCalledWith('res:uuid:5');
  });

  it('link click handlers call stopPropagation', () => {
    const { container } = wrap(<RefRevisionLink value="res:uuid:5" fieldRef={revRef} />);
    const link = container.querySelector('a')!;
    const clickEvent = new MouseEvent('click', { bubbles: true });
    const stopSpy = vi.spyOn(clickEvent, 'stopPropagation');
    link.dispatchEvent(clickEvent);
    expect(stopSpy).toHaveBeenCalled();
  });

  it('copy button resets after timeout', () => {
    vi.useFakeTimers();
    wrap(<RefRevisionLink value="res:uuid:5" fieldRef={revRef} />);
    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[buttons.length - 1]);
    vi.advanceTimersByTime(2000);
    vi.useRealTimers();
    expect(mockWriteText).toHaveBeenCalledWith('res:uuid:5');
  });

  it('renders with plain resource_id (no revision search param)', () => {
    const { container } = wrap(<RefRevisionLink value="plain-res-id" fieldRef={revRef} />);
    const link = container.querySelector('a')!;
    expect(link.getAttribute('data-search')).toBe('{}');
  });

  it('renders with revision_id format (includes revision search param)', () => {
    const { container } = wrap(<RefRevisionLink value="res:uuid:5" fieldRef={revRef} />);
    const link = container.querySelector('a')!;
    const search = JSON.parse(link.getAttribute('data-search') || '{}');
    expect(search.revision).toBe('res:uuid:5');
  });
});

// ---------------------------------------------------------------------------
// RefRevisionLinkList
// ---------------------------------------------------------------------------

describe('RefRevisionLinkList', () => {
  it('renders empty text for null values', () => {
    const { container } = wrap(<RefRevisionLinkList values={null} fieldRef={revRef} />);
    expect(container.textContent).toContain('（空）');
  });

  it('renders empty text for empty array', () => {
    const { container } = wrap(<RefRevisionLinkList values={[]} fieldRef={revRef} />);
    expect(container.textContent).toContain('（空）');
  });

  it('renders list of revision links', () => {
    const { container } = wrap(<RefRevisionLinkList values={['a:1', 'b:2']} fieldRef={revRef} />);
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBeGreaterThanOrEqual(2);
  });

  it('shows expand when exceeding maxVisible', () => {
    const values = ['a:1', 'b:2', 'c:3', 'd:4'];
    const { container } = wrap(<RefRevisionLinkList values={values} fieldRef={revRef} maxVisible={2} />);
    expect(container.textContent).toContain('+2 more...');
  });

  it('expands and collapses', () => {
    const values = ['a:1', 'b:2', 'c:3', 'd:4'];
    const { container } = wrap(<RefRevisionLinkList values={values} fieldRef={revRef} maxVisible={2} />);
    
    // Find "+2 more..." text and click it
    const moreText = Array.from(container.querySelectorAll('*')).find(
      el => el.textContent?.trim() === '+2 more...'
    ) as HTMLElement;
    expect(moreText).toBeDefined();
    fireEvent.click(moreText);
    expect(container.textContent).toContain('收起');

    // Collapse
    const collapseText = Array.from(container.querySelectorAll('*')).find(
      el => el.textContent?.trim() === '收起'
    ) as HTMLElement;
    fireEvent.click(collapseText);
    expect(container.textContent).toContain('+2 more...');
  });
});
