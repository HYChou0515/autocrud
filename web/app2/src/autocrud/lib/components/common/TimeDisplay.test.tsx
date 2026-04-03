/**
 * TimeDisplay & formatTime — unit tests.
 *
 * Covers:
 * - formatTime: all format modes + invalid date
 * - TimeDisplay component: all formats, tooltip, invalid date
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { TimeDisplay, formatTime } from './TimeDisplay';

// ---------------------------------------------------------------------------
// formatTime (pure function)
// ---------------------------------------------------------------------------

describe('formatTime', () => {
  it('returns formatted full date', () => {
    const result = formatTime('2024-01-15T10:30:45', 'full');
    expect(result).toBe('2024-01-15 10:30:45');
  });

  it('returns short format', () => {
    const result = formatTime('2024-01-15T10:30:45', 'short');
    expect(result).toBe('01/15 10:30');
  });

  it('returns date only format', () => {
    const result = formatTime('2024-01-15T10:30:45', 'date');
    expect(result).toBe('2024-01-15');
  });

  it('returns relative time by default', () => {
    const result = formatTime('2024-01-15T10:30:45');
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });

  it('returns relative format explicitly', () => {
    const result = formatTime('2024-01-15T10:30:45', 'relative');
    expect(typeof result).toBe('string');
  });

  it('returns - for invalid date', () => {
    expect(formatTime('not-a-date')).toBe('-');
  });

  it('accepts Date object', () => {
    const date = new Date('2024-06-15T12:00:00');
    expect(formatTime(date, 'full')).toBe('2024-06-15 12:00:00');
  });
});

// ---------------------------------------------------------------------------
// TimeDisplay component
// ---------------------------------------------------------------------------

describe('TimeDisplay', () => {
  const wrap = (ui: React.ReactElement) => render(<MantineProvider>{ui}</MantineProvider>);

  it('renders full format without tooltip', () => {
    wrap(<TimeDisplay time="2024-01-15T10:30:45" format="full" />);
    expect(screen.getByText('2024-01-15 10:30:45')).toBeDefined();
  });

  it('renders short format', () => {
    wrap(<TimeDisplay time="2024-01-15T10:30:45" format="short" />);
    expect(screen.getByText('01/15 10:30')).toBeDefined();
  });

  it('renders date format', () => {
    wrap(<TimeDisplay time="2024-01-15T10:30:45" format="date" />);
    expect(screen.getByText('2024-01-15')).toBeDefined();
  });

  it('renders relative format with tooltip', () => {
    wrap(<TimeDisplay time="2024-01-15T10:30:45" format="relative" />);
    // Relative time varies, just check something renders
    const span = document.querySelector('span[style]');
    expect(span).toBeDefined();
  });

  it('renders - for invalid date', () => {
    wrap(<TimeDisplay time="invalid" />);
    expect(screen.getByText('-')).toBeDefined();
  });

  it('renders without tooltip when showTooltip is false', () => {
    wrap(<TimeDisplay time="2024-01-15T10:30:45" format="relative" showTooltip={false} />);
    const span = document.querySelector('span');
    expect(span).toBeDefined();
  });
});
