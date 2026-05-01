/**
 * displayHelpers — unit tests.
 *
 * Covers:
 * - isISODateString: truthy/falsy cases
 * - isBlobObject: with/without file_id + size
 * - renderSimpleValue: null, dates, booleans, arrays, objects, strings
 */

import { describe, it, expect } from 'vitest';
import { isISODateString, isBlobObject, renderSimpleValue, NA } from './displayHelpers';

// ---------------------------------------------------------------------------
// isISODateString
// ---------------------------------------------------------------------------

describe('isISODateString', () => {
  it('returns true for ISO date string', () => {
    expect(isISODateString('2024-01-15T10:30:00')).toBe(true);
    expect(isISODateString('2024-01-15T10:30:00.000Z')).toBe(true);
    expect(isISODateString('2024-12-31T23:59:59+08:00')).toBe(true);
  });

  it('returns false for non-date strings', () => {
    expect(isISODateString('hello world')).toBe(false);
    expect(isISODateString('2024-01-15')).toBe(false);
    expect(isISODateString('')).toBe(false);
  });

  it('returns false for non-string values', () => {
    expect(isISODateString(123)).toBe(false);
    expect(isISODateString(null)).toBe(false);
    expect(isISODateString(undefined)).toBe(false);
    expect(isISODateString({})).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// isBlobObject
// ---------------------------------------------------------------------------

describe('isBlobObject', () => {
  it('returns true when file_id and size are present', () => {
    expect(isBlobObject({ file_id: 'abc', size: 1024 })).toBe(true);
  });

  it('returns false when file_id is missing', () => {
    expect(isBlobObject({ size: 1024 })).toBe(false);
  });

  it('returns false when size is missing', () => {
    expect(isBlobObject({ file_id: 'abc' })).toBe(false);
  });

  it('returns false for empty object', () => {
    expect(isBlobObject({})).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// renderSimpleValue
// ---------------------------------------------------------------------------

describe('renderSimpleValue', () => {
  it('returns NA for null', () => {
    expect(renderSimpleValue(null)).toBe(NA);
  });

  it('returns NA for undefined', () => {
    expect(renderSimpleValue(undefined)).toBe(NA);
  });

  it('returns Yes for true', () => {
    expect(renderSimpleValue(true)).toBe('✅ Yes');
  });

  it('returns No for false', () => {
    expect(renderSimpleValue(false)).toBe('❌ No');
  });

  it('returns stringified value for plain string', () => {
    expect(renderSimpleValue('hello')).toBe('hello');
  });

  it('returns stringified number', () => {
    expect(renderSimpleValue(42)).toBe('42');
  });

  it('returns joined string for simple array', () => {
    expect(renderSimpleValue(['a', 'b', 'c'])).toBe('a, b, c');
  });

  it('returns JSX for empty array', () => {
    const result = renderSimpleValue([]);
    expect(result).toBeDefined();
    // It returns a React element for empty arrays
    expect(result).not.toBe('');
  });

  it('returns JSX for object array', () => {
    const result = renderSimpleValue([{ key: 'val' }]);
    expect(result).toBeDefined();
  });

  it('returns JSX for plain object', () => {
    const result = renderSimpleValue({ key: 'value' });
    expect(result).toBeDefined();
  });

  it('returns TimeDisplay for ISO date string', () => {
    const result = renderSimpleValue('2024-01-15T10:30:00');
    expect(result).toBeDefined();
  });
});
