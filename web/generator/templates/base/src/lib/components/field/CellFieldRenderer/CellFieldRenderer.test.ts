/**
 * CellFieldRenderer — Registry completeness & dispatch tests.
 *
 * Because CELL_RENDERERS is typed as Record<FieldKind, ...>,
 * TypeScript already enforces coverage at compile time. These tests verify:
 *   1. Registry key completeness at runtime
 *   2. renderCellValue dispatch correctness for each FieldKind
 *   3. null/undefined handling
 *   4. Edge cases for each renderer
 */

import { describe, it, expect } from 'vitest';
import { resolveFieldKind, type FieldKind } from '../resolveFieldKind';
import { CELL_RENDERERS, renderCellValue, CellFieldRenderer } from './index';
import type { ResourceField } from '../../../resources';

/** Minimal helper to create a ResourceField with sensible defaults. */
function makeField(overrides: Partial<ResourceField> & { name: string }): ResourceField {
  return {
    label: overrides.name,
    type: 'string',
    isArray: false,
    isRequired: false,
    isNullable: false,
    ...overrides,
  };
}

/**
 * All FieldKind values that CELL_RENDERERS must cover.
 */
const ALL_FIELD_KINDS: FieldKind[] = [
  'itemFields',
  'union',
  'binary',
  'json',
  'markdown',
  'arrayString',
  'tags',
  'select',
  'checkbox',
  'switch',
  'date',
  'numberSlider',
  'number',
  'textarea',
  'refResourceId',
  'refResourceIdMulti',
  'refRevisionId',
  'refRevisionIdMulti',
  'text',
];

describe('CELL_RENDERERS registry completeness', () => {
  it('has an entry for every FieldKind', () => {
    for (const kind of ALL_FIELD_KINDS) {
      expect(CELL_RENDERERS).toHaveProperty(kind);
      expect(typeof CELL_RENDERERS[kind]).toBe('function');
    }
  });

  it('has no extra entries beyond FieldKind', () => {
    const registeredKeys = Object.keys(CELL_RENDERERS);
    expect(registeredKeys.sort()).toEqual([...ALL_FIELD_KINDS].sort());
  });

  it('ALL_FIELD_KINDS contains every FieldKind value', () => {
    expect(ALL_FIELD_KINDS.length).toBe(19);
  });
});

describe('renderCellValue null handling', () => {
  it('returns empty string for null value', () => {
    const field = makeField({ name: 'x' });
    expect(renderCellValue({ field, value: null })).toBe('');
  });

  it('returns empty string for undefined value', () => {
    const field = makeField({ name: 'x' });
    expect(renderCellValue({ field, value: undefined })).toBe('');
  });
});

describe('renderCellValue dispatch correctness', () => {
  /** Map of FieldKind → { field config, sample value, expected output check } */
  const fieldConfigs: Array<{
    kind: FieldKind;
    field: ResourceField;
    value: unknown;
    check: (result: React.ReactNode) => void;
  }> = [
    {
      kind: 'text',
      field: makeField({ name: 'name' }),
      value: 'Alice',
      check: (r) => expect(r).toBe('Alice'),
    },
    {
      kind: 'number',
      field: makeField({ name: 'age', type: 'number' }),
      value: 42,
      check: (r) => expect(r).toBe('42'),
    },
    {
      kind: 'numberSlider',
      field: makeField({
        name: 'level',
        type: 'number',
        variant: { type: 'slider', sliderMin: 0, sliderMax: 100 },
      }),
      value: 75,
      check: (r) => expect(r).toBe('75'),
    },
    {
      kind: 'select',
      field: makeField({
        name: 'role',
        enumValues: ['admin', 'user'],
        variant: { type: 'select', options: [{ value: 'admin', label: 'Admin' }] },
      }),
      value: 'admin',
      check: (r) => expect(r).toBe('admin'),
    },
    {
      kind: 'textarea',
      field: makeField({ name: 'desc', variant: { type: 'textarea' } }),
      value: 'long text here',
      check: (r) => expect(r).toBe('long text here'),
    },
    {
      kind: 'markdown',
      field: makeField({ name: 'bio', variant: { type: 'markdown' } }),
      value: '# Hello',
      check: (r) => expect(r).toBe('# Hello'),
    },
    {
      kind: 'checkbox',
      field: makeField({ name: 'agree', type: 'boolean', variant: { type: 'checkbox' } }),
      value: true,
      check: (r) => expect(r).toBe('✅'),
    },
    {
      kind: 'switch',
      field: makeField({ name: 'active', type: 'boolean' }),
      value: false,
      check: (r) => expect(r).toBe('❌'),
    },
  ];

  for (const { kind, field, value, check } of fieldConfigs) {
    it(`dispatches to '${kind}' renderer`, () => {
      // Ensure resolveFieldKind produces expected kind
      expect(resolveFieldKind(field)).toBe(kind);
      // Ensure renderCellValue uses the correct renderer
      const result = renderCellValue({ field, value });
      check(result);
    });
  }
});

describe('CellFieldRenderer date renderer', () => {
  it('renders a date string via formatTime', () => {
    const field = makeField({ name: 'created', type: 'date' });
    const result = renderCellValue({ field, value: '2024-06-15T10:30:00Z' });
    // formatTime returns a ReactElement — just verify it's not empty
    expect(result).toBeTruthy();
    expect(result).not.toBe('');
  });
});

describe('CellFieldRenderer array renderers', () => {
  it('arrayString: joins strings with comma', () => {
    const field = makeField({ name: 'tags', type: 'string', isArray: true });
    expect(resolveFieldKind(field)).toBe('arrayString');
    const result = renderCellValue({ field, value: ['a', 'b', 'c'] });
    expect(result).toBe('a, b, c');
  });

  it('arrayString: empty array returns [] element', () => {
    const field = makeField({ name: 'tags', type: 'string', isArray: true });
    const result = renderCellValue({ field, value: [] });
    // Returns a React element with "[]"
    expect(result).toBeTruthy();
    expect(result).not.toBe('');
  });

  it('tags: joins strings with comma', () => {
    const field = makeField({ name: 'labels', variant: { type: 'tags' } });
    expect(resolveFieldKind(field)).toBe('tags');
    const result = renderCellValue({ field, value: ['x', 'y'] });
    expect(result).toBe('x, y');
  });
});

describe('CellFieldRenderer binary renderer', () => {
  it('renders binary with file_id', () => {
    const field = makeField({ name: 'avatar', type: 'binary' });
    expect(resolveFieldKind(field)).toBe('binary');
    const result = renderCellValue({
      field,
      value: { file_id: 'abc', content_type: 'image/png', size: 1024 },
    });
    expect(result).toBeTruthy();
  });

  it('returns dash for non-binary value', () => {
    const field = makeField({ name: 'avatar', type: 'binary' });
    const result = renderCellValue({ field, value: {} });
    expect(result).toBeTruthy();
  });
});

describe('CellFieldRenderer json renderer', () => {
  it('renders object preview for objects', () => {
    const field = makeField({ name: 'meta', type: 'object' });
    expect(resolveFieldKind(field)).toBe('json');
    const result = renderCellValue({ field, value: { key: 'val' } });
    expect(result).toBeTruthy();
  });

  it('renders string for non-objects', () => {
    const field = makeField({ name: 'meta', type: 'object' });
    const result = renderCellValue({ field, value: 'not-json' });
    expect(result).toBe('not-json');
  });
});

describe('CellFieldRenderer itemFields renderer', () => {
  it('renders array of objects as preview', () => {
    const field = makeField({
      name: 'items',
      type: 'array',
      isArray: true,
      itemFields: [makeField({ name: 'sub', type: 'string' })],
    });
    expect(resolveFieldKind(field)).toBe('itemFields');
    const result = renderCellValue({ field, value: [{ sub: 'a' }, { sub: 'b' }] });
    expect(result).toBeTruthy();
  });

  it('returns dash for empty array', () => {
    const field = makeField({
      name: 'items',
      type: 'array',
      isArray: true,
      itemFields: [makeField({ name: 'sub', type: 'string' })],
    });
    const result = renderCellValue({ field, value: [] });
    expect(result).toBeTruthy();
  });

  it('returns dash for non-array', () => {
    const field = makeField({
      name: 'items',
      type: 'array',
      isArray: true,
      itemFields: [makeField({ name: 'sub', type: 'string' })],
    });
    const result = renderCellValue({ field, value: 'not-array' });
    expect(result).toBeTruthy();
  });
});

describe('CellFieldRenderer union renderer', () => {
  it('renders union value as JSON preview', () => {
    const field = makeField({
      name: 'data',
      type: 'union',
      unionMeta: { discriminatorField: 'kind', variants: [] },
    });
    expect(resolveFieldKind(field)).toBe('union');
    const result = renderCellValue({ field, value: { kind: 'typeA', foo: 1 } });
    expect(result).toBeTruthy();
  });
});

describe('CellFieldRenderer ref renderers', () => {
  it('refResourceId renders a link', () => {
    const field = makeField({
      name: 'guild_id',
      ref: { resource: 'guild', type: 'resource_id' },
    });
    expect(resolveFieldKind(field)).toBe('refResourceId');
    const result = renderCellValue({ field, value: 'rid-123' });
    expect(result).toBeTruthy();
  });

  it('refResourceIdMulti renders a link list', () => {
    const field = makeField({
      name: 'friend_ids',
      isArray: true,
      ref: { resource: 'character', type: 'resource_id' },
    });
    expect(resolveFieldKind(field)).toBe('refResourceIdMulti');
    const result = renderCellValue({ field, value: ['rid-1', 'rid-2'] });
    expect(result).toBeTruthy();
  });

  it('refRevisionId renders a link', () => {
    const field = makeField({
      name: 'snapshot_id',
      ref: { resource: 'snapshot', type: 'revision_id' },
    });
    expect(resolveFieldKind(field)).toBe('refRevisionId');
    const result = renderCellValue({ field, value: 'rev-abc' });
    expect(result).toBeTruthy();
  });

  it('refRevisionIdMulti renders a link list', () => {
    const field = makeField({
      name: 'snapshot_ids',
      isArray: true,
      ref: { resource: 'snapshot', type: 'revision_id' },
    });
    expect(resolveFieldKind(field)).toBe('refRevisionIdMulti');
    const result = renderCellValue({ field, value: ['rev-1', 'rev-2'] });
    expect(result).toBeTruthy();
  });
});

describe('CellFieldRenderer text renderer (auto-detection fallback)', () => {
  it('detects boolean inside text kind', () => {
    // A field resolved as 'text' but with boolean value
    const field = makeField({ name: 'flag' });
    expect(resolveFieldKind(field)).toBe('text');
    expect(renderCellValue({ field, value: true })).toBe('✅');
    expect(renderCellValue({ field, value: false })).toBe('❌');
  });

  it('detects array inside text kind', () => {
    const field = makeField({ name: 'misc' });
    expect(renderCellValue({ field, value: ['a', 'b'] })).toBe('a, b');
  });

  it('detects ISO date string', () => {
    const field = makeField({ name: 'ts' });
    const result = renderCellValue({ field, value: '2024-06-15T10:30:00Z' });
    expect(result).toBeTruthy();
    expect(result).not.toBe('2024-06-15T10:30:00Z'); // Should be formatted
  });

  it('detects binary-like object (file_id + size)', () => {
    const field = makeField({ name: 'blob' });
    const result = renderCellValue({
      field,
      value: { file_id: 'f1', size: 500, content_type: 'text/plain' },
    });
    expect(result).toBeTruthy();
  });

  it('detects plain object', () => {
    const field = makeField({ name: 'obj' });
    const result = renderCellValue({ field, value: { key: 'val' } });
    expect(result).toBeTruthy();
  });

  it('falls back to String()', () => {
    const field = makeField({ name: 'x' });
    expect(renderCellValue({ field, value: 123 })).toBe('123');
  });
});

describe('CellFieldRenderer component', () => {
  it('renders via the public component wrapper', () => {
    const field = makeField({ name: 'name' });
    const result = CellFieldRenderer({ field, value: 'Alice' });
    expect(result).toBeTruthy();
  });

  it('handles null value in component wrapper', () => {
    const field = makeField({ name: 'name' });
    const result = CellFieldRenderer({ field, value: null });
    expect(result).toBeTruthy();
  });
});

describe('CellFieldRenderer arrayJoin edge cases', () => {
  it('arrayString: renders object arrays as preview', () => {
    const field = makeField({ name: 'tags', type: 'string', isArray: true });
    const result = renderCellValue({ field, value: [{ complex: true }] });
    expect(result).toBeTruthy();
  });

  it('arrayString: renders non-array as string', () => {
    const field = makeField({ name: 'tags', type: 'string', isArray: true });
    const result = renderCellValue({ field, value: 'not-an-array' });
    expect(result).toBe('not-an-array');
  });
});

describe('CellFieldRenderer text renderer (nested edge cases)', () => {
  it('detects empty array inside text kind', () => {
    const field = makeField({ name: 'misc' });
    const result = renderCellValue({ field, value: [] });
    expect(result).toBeTruthy();
  });

  it('detects object array inside text kind', () => {
    const field = makeField({ name: 'misc' });
    const result = renderCellValue({ field, value: [{ a: 1 }] });
    expect(result).toBeTruthy();
  });

  it('joins simple array inside text kind', () => {
    const field = makeField({ name: 'misc' });
    expect(renderCellValue({ field, value: ['x', 'y'] })).toBe('x, y');
  });
});
