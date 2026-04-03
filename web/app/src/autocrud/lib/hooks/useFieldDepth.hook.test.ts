/**
 * useFieldDepth hook integration tests — tests the actual React hook
 * rather than the extracted pure-function logic (which is tested in
 * useFieldDepth.test.ts).
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act, cleanup } from '@testing-library/react';
import { useFieldDepth } from './useFieldDepth';

beforeEach(() => {
  cleanup();
});

/** Minimal field helper. */
function makeField(name: string, opts: any = {}) {
  return {
    name,
    label: name,
    type: 'string' as const,
    isArray: false,
    isRequired: false,
    isNullable: false,
    ...opts,
  };
}

describe('useFieldDepth hook', () => {
  it('returns maxAvailableDepth based on field structure', () => {
    const fields = [makeField('a'), makeField('b.c')];
    const { result } = renderHook(() => useFieldDepth({ fields }));
    expect(result.current.maxAvailableDepth).toBe(2);
  });

  it('defaults depth to maxAvailableDepth', () => {
    const fields = [makeField('a'), makeField('b.c')];
    const { result } = renderHook(() => useFieldDepth({ fields }));
    expect(result.current.depth).toBe(result.current.maxAvailableDepth);
  });

  it('respects maxFormDepth override', () => {
    const fields = [makeField('a'), makeField('b.c'), makeField('b.d.e')];
    const { result } = renderHook(() => useFieldDepth({ fields, maxFormDepth: 1 }));
    expect(result.current.depth).toBe(1);
  });

  it('setDepth updates the depth', () => {
    const fields = [makeField('a'), makeField('b.c')];
    const { result } = renderHook(() => useFieldDepth({ fields }));

    act(() => {
      result.current.setDepth(1);
    });

    expect(result.current.depth).toBe(1);
  });

  it('returns visibleFields for current depth', () => {
    const fields = [makeField('a'), makeField('b.c')];
    const { result } = renderHook(() => useFieldDepth({ fields }));

    // At max depth (2), all fields should be visible
    expect(result.current.visibleFields.map((f: any) => f.name)).toContain('a');
    expect(result.current.visibleFields.map((f: any) => f.name)).toContain('b.c');
  });

  it('returns collapsedGroups when depth is low', () => {
    const fields = [makeField('a'), makeField('b.c'), makeField('b.d')];
    const { result } = renderHook(() => useFieldDepth({ fields, maxFormDepth: 1 }));

    expect(result.current.visibleFields.map((f: any) => f.name)).toContain('a');
    expect(result.current.collapsedGroups.map((g: any) => g.path)).toContain('b');
  });

  it('stripItemFields keeps itemFields-bearing fields visible but stripped', () => {
    const subFields = [makeField('sub_x')];
    const fields = [makeField('items', { itemFields: subFields, type: 'array', isArray: true })];
    const { result } = renderHook(() =>
      useFieldDepth({ fields, maxFormDepth: 1, stripItemFields: true }),
    );

    const itemsField = result.current.visibleFields.find((f: any) => f.name === 'items');
    expect(itemsField).toBeDefined();
    expect(itemsField!.itemFields).toBeUndefined();
  });

  it('without stripItemFields, itemFields fields become collapsed at low depth', () => {
    const subFields = [makeField('sub_x')];
    const fields = [makeField('items', { itemFields: subFields, type: 'array', isArray: true })];
    const { result } = renderHook(() =>
      useFieldDepth({ fields, maxFormDepth: 1, stripItemFields: false }),
    );

    // 'items' should be in collapsed groups
    expect(result.current.collapsedGroups.map((g: any) => g.path)).toContain('items');
  });
});
