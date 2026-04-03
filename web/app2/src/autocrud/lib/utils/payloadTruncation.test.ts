/**
 * payloadTruncation — Unit tests for payload truncation utilities.
 */

import { describe, it, expect } from 'vitest';
import {
  truncatePayload,
  truncateForCell,
  truncateForDetail,
  TRUNCATION_MARKER,
  CELL_TRUNCATE_OPTIONS,
  DETAIL_TRUNCATE_OPTIONS,
  type TruncationInfo,
} from './payloadTruncation';

// ---------------------------------------------------------------------------
// truncatePayload — core behaviour
// ---------------------------------------------------------------------------

describe('truncatePayload', () => {
  // -- Primitives pass through --

  it('passes null through', () => {
    expect(truncatePayload(null)).toBeNull();
  });

  it('passes undefined through', () => {
    expect(truncatePayload(undefined)).toBeUndefined();
  });

  it('passes booleans through', () => {
    expect(truncatePayload(true)).toBe(true);
    expect(truncatePayload(false)).toBe(false);
  });

  it('passes numbers through', () => {
    expect(truncatePayload(42)).toBe(42);
    expect(truncatePayload(3.14)).toBe(3.14);
  });

  it('passes short strings through unchanged', () => {
    expect(truncatePayload('hello')).toBe('hello');
  });

  // -- String truncation --

  it('truncates long strings', () => {
    const long = 'x'.repeat(20_000);
    const result = truncatePayload(long, { maxStringLength: 100 }) as string;
    expect(result.length).toBeLessThan(200);
    expect(result).toContain('…[truncated');
    expect(result).toContain('KB total');
  });

  it('does not truncate strings exactly at the limit', () => {
    const str = 'a'.repeat(100);
    expect(truncatePayload(str, { maxStringLength: 100 })).toBe(str);
  });

  // -- Object key truncation --

  it('keeps all keys when under maxKeys', () => {
    const obj = { a: 1, b: 2, c: 3 };
    const result = truncatePayload(obj, { maxKeys: 5 }) as Record<string, unknown>;
    expect(Object.keys(result)).toEqual(['a', 'b', 'c']);
  });

  it('truncates object keys and adds marker', () => {
    const obj: Record<string, number> = {};
    for (let i = 0; i < 20; i++) obj[`key${i}`] = i;

    const result = truncatePayload(obj, { maxKeys: 5 }) as Record<string, unknown>;
    // Should have 5 data keys + marker
    const keys = Object.keys(result);
    expect(keys).toHaveLength(6); // 5 + marker
    expect(keys).toContain(TRUNCATION_MARKER);

    const info = result[TRUNCATION_MARKER] as TruncationInfo;
    expect(info.total).toBe(20);
    expect(info.omitted).toBe(15);
  });

  // -- Array truncation --

  it('keeps all array items when under maxArrayItems', () => {
    const arr = [1, 2, 3];
    const result = truncatePayload(arr, { maxArrayItems: 10 });
    expect(result).toEqual([1, 2, 3]);
  });

  it('truncates arrays and adds marker', () => {
    const arr = Array.from({ length: 100 }, (_, i) => i);
    const result = truncatePayload(arr, { maxArrayItems: 5 }) as unknown[];
    expect(result).toHaveLength(6); // 5 items + marker
    const marker = result[5] as Record<string, TruncationInfo>;
    expect(marker[TRUNCATION_MARKER]).toBeDefined();
    expect(marker[TRUNCATION_MARKER].total).toBe(100);
    expect(marker[TRUNCATION_MARKER].omitted).toBe(95);
  });

  // -- Depth limiting --

  it('replaces deep arrays with placeholder string', () => {
    const nested = { a: { b: { c: [1, 2, 3] } } };
    const result = truncatePayload(nested, { maxDepth: 2 }) as any;
    expect(result.a.b).toBe('[Object(1 keys)]');
  });

  it('replaces deep objects with placeholder string', () => {
    const nested = { a: { b: { c: { d: 'deep' } } } };
    const result = truncatePayload(nested, { maxDepth: 3 }) as any;
    expect(result.a.b.c).toBe('[Object(1 keys)]');
  });

  // -- Recursive truncation --

  it('truncates nested string values', () => {
    const obj = { data: 'x'.repeat(500) };
    const result = truncatePayload(obj, { maxStringLength: 100 }) as Record<string, unknown>;
    const val = result.data as string;
    expect(val.length).toBeLessThan(200);
    expect(val).toContain('…[truncated');
  });

  it('truncates nested arrays inside objects', () => {
    const obj = { items: Array.from({ length: 50 }, (_, i) => i) };
    const result = truncatePayload(obj, { maxArrayItems: 3 }) as any;
    expect(result.items).toHaveLength(4); // 3 items + marker
  });

  // -- Does not mutate original --

  it('does not mutate original object', () => {
    const original: Record<string, number> = {};
    for (let i = 0; i < 20; i++) original[`key${i}`] = i;
    const originalKeys = Object.keys(original).length;

    truncatePayload(original, { maxKeys: 5 });

    expect(Object.keys(original)).toHaveLength(originalKeys);
    expect(original[TRUNCATION_MARKER]).toBeUndefined();
  });

  it('does not mutate original array', () => {
    const original = Array.from({ length: 50 }, (_, i) => i);
    truncatePayload(original, { maxArrayItems: 5 });
    expect(original).toHaveLength(50);
  });
});

// ---------------------------------------------------------------------------
// truncateForCell — aggressive preset
// ---------------------------------------------------------------------------

describe('truncateForCell', () => {
  it('uses CELL preset to truncate many keys', () => {
    const obj: Record<string, number> = {};
    for (let i = 0; i < 100; i++) obj[`k${i}`] = i;

    const result = truncateForCell(obj) as Record<string, unknown>;
    // Should have maxKeys + 1 (marker)
    const keys = Object.keys(result);
    expect(keys).toHaveLength(CELL_TRUNCATE_OPTIONS.maxKeys + 1);
    expect(keys).toContain(TRUNCATION_MARKER);
  });

  it('truncates long string values aggressively', () => {
    const obj = { blob: 'A'.repeat(10_000) };
    const result = truncateForCell(obj) as Record<string, string>;
    expect(result.blob.length).toBeLessThan(CELL_TRUNCATE_OPTIONS.maxStringLength + 100);
    expect(result.blob).toContain('…[truncated');
  });

  it('truncates long arrays', () => {
    const arr = Array.from({ length: 100 }, (_, i) => `item${i}`);
    const result = truncateForCell(arr) as unknown[];
    expect(result).toHaveLength(CELL_TRUNCATE_OPTIONS.maxArrayItems + 1);
  });

  it('handles empty objects', () => {
    expect(truncateForCell({})).toEqual({});
  });

  it('handles empty arrays', () => {
    expect(truncateForCell([])).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// truncateForDetail — moderate preset
// ---------------------------------------------------------------------------

describe('truncateForDetail', () => {
  it('uses DETAIL preset limits', () => {
    const obj: Record<string, number> = {};
    for (let i = 0; i < 200; i++) obj[`k${i}`] = i;

    const result = truncateForDetail(obj) as Record<string, unknown>;
    const keys = Object.keys(result);
    expect(keys).toHaveLength(DETAIL_TRUNCATE_OPTIONS.maxKeys + 1);
    expect(keys).toContain(TRUNCATION_MARKER);
  });

  it('keeps objects under the limit untouched', () => {
    const obj = { a: 1, b: 'hello', c: [1, 2] };
    const result = truncateForDetail(obj);
    expect(result).toEqual(obj);
  });

  it('truncates large string values', () => {
    const obj = { content: 'B'.repeat(50_000) };
    const result = truncateForDetail(obj) as Record<string, string>;
    expect(result.content.length).toBeLessThan(DETAIL_TRUNCATE_OPTIONS.maxStringLength + 100);
    expect(result.content).toContain('…[truncated');
  });
});

// ---------------------------------------------------------------------------
// Performance — must not freeze on huge payloads
// ---------------------------------------------------------------------------

describe('performance', () => {
  it('handles object with 10k keys in under 100ms', () => {
    const huge: Record<string, number> = {};
    for (let i = 0; i < 10_000; i++) huge[`field_${i}`] = i;

    const start = performance.now();
    const result = truncateForCell(huge);
    const elapsed = performance.now() - start;

    expect(result).toBeDefined();
    expect(elapsed).toBeLessThan(100);
  });

  it('handles 5MB string value in under 50ms', () => {
    const huge = { blob: 'X'.repeat(5_000_000) };

    const start = performance.now();
    const result = truncateForCell(huge);
    const elapsed = performance.now() - start;

    expect(result).toBeDefined();
    expect(elapsed).toBeLessThan(50);
  });

  it('handles deeply nested structure without stack overflow', () => {
    // Build a deeply nested object: {a: {a: {a: ... }}}
    let obj: Record<string, unknown> = { value: 'leaf' };
    for (let i = 0; i < 100; i++) {
      obj = { nested: obj };
    }

    // Should not throw — depth limiting kicks in
    const result = truncatePayload(obj, { maxDepth: 5 });
    expect(result).toBeDefined();
  });

  it('handles array with many large objects in under 100ms', () => {
    const items = Array.from({ length: 1000 }, (_, i) => ({
      id: i,
      name: `item_${i}`,
      data: 'y'.repeat(1000),
    }));

    const start = performance.now();
    const result = truncateForCell(items);
    const elapsed = performance.now() - start;

    expect(result).toBeDefined();
    expect(elapsed).toBeLessThan(100);
  });
});
