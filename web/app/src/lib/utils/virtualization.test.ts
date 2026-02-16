import { describe, expect, it } from 'vitest';
import { getVirtualPadding } from './virtualization';

describe('getVirtualPadding', () => {
  it('returns full bottom padding when no items', () => {
    expect(getVirtualPadding([], 120)).toEqual({
      paddingTop: 0,
      paddingBottom: 120,
    });
  });

  it('returns top and bottom padding based on items', () => {
    const items = [
      { start: 40, end: 120 },
      { start: 120, end: 200 },
    ];

    expect(getVirtualPadding(items, 320)).toEqual({
      paddingTop: 40,
      paddingBottom: 120,
    });
  });

  it('clamps padding to non-negative values', () => {
    const items = [{ start: -10, end: 60 }];

    expect(getVirtualPadding(items, -5)).toEqual({
      paddingTop: 0,
      paddingBottom: 0,
    });
  });
});
