import { describe, it, expect } from 'vitest';
import { resolveFieldKind } from './resolveFieldKind';
import type { ResourceField } from '../../resources';

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

describe('resolveFieldKind', () => {
  // -------------------------------------------------------------------
  // 1. itemFields
  // -------------------------------------------------------------------
  it('returns "itemFields" when field has non-empty itemFields', () => {
    const field = makeField({
      name: 'items',
      type: 'array',
      isArray: true,
      itemFields: [makeField({ name: 'sub', type: 'string' })],
    });
    expect(resolveFieldKind(field)).toBe('itemFields');
  });

  it('does NOT return "itemFields" when itemFields is empty', () => {
    const field = makeField({ name: 'items', type: 'string', itemFields: [] });
    expect(resolveFieldKind(field)).not.toBe('itemFields');
  });

  // -------------------------------------------------------------------
  // 2. union
  // -------------------------------------------------------------------
  it('returns "union" for union type with unionMeta', () => {
    const field = makeField({
      name: 'data',
      type: 'union',
      unionMeta: { discriminatorField: 'kind', variants: [] },
    });
    expect(resolveFieldKind(field)).toBe('union');
  });

  it('does NOT return "union" when unionMeta is undefined', () => {
    const field = makeField({ name: 'data', type: 'union' });
    expect(resolveFieldKind(field)).not.toBe('union');
  });

  // -------------------------------------------------------------------
  // 3. binary
  // -------------------------------------------------------------------
  it('returns "binary" for binary type', () => {
    const field = makeField({ name: 'avatar', type: 'binary' });
    expect(resolveFieldKind(field)).toBe('binary');
  });

  // -------------------------------------------------------------------
  // 4. json / object
  // -------------------------------------------------------------------
  it('returns "json" for object type (no variant)', () => {
    const field = makeField({ name: 'meta', type: 'object' });
    expect(resolveFieldKind(field)).toBe('json');
  });

  it('returns "json" when variant is json', () => {
    const field = makeField({
      name: 'config',
      type: 'string',
      variant: { type: 'json', height: 400 },
    });
    expect(resolveFieldKind(field)).toBe('json');
  });

  // -------------------------------------------------------------------
  // 5. markdown
  // -------------------------------------------------------------------
  it('returns "markdown" when variant is markdown', () => {
    const field = makeField({
      name: 'body',
      type: 'string',
      variant: { type: 'markdown', height: 300 },
    });
    expect(resolveFieldKind(field)).toBe('markdown');
  });

  // -------------------------------------------------------------------
  // 6. arrayString (comma-separated)
  // -------------------------------------------------------------------
  it('returns "arrayString" for string array without ref', () => {
    const field = makeField({ name: 'tags', type: 'string', isArray: true });
    expect(resolveFieldKind(field)).toBe('arrayString');
  });

  it('does NOT return "arrayString" for string array with resource_id ref', () => {
    const field = makeField({
      name: 'relatedIds',
      type: 'string',
      isArray: true,
      ref: { resource: 'users', type: 'resource_id' },
    });
    expect(resolveFieldKind(field)).toBe('refResourceIdMulti');
  });

  // -------------------------------------------------------------------
  // 7. tags
  // -------------------------------------------------------------------
  it('returns "tags" when variant is tags', () => {
    const field = makeField({
      name: 'labels',
      type: 'string',
      variant: { type: 'tags' },
    });
    expect(resolveFieldKind(field)).toBe('tags');
  });

  // -------------------------------------------------------------------
  // 8. select
  // -------------------------------------------------------------------
  it('returns "select" when variant is select', () => {
    const field = makeField({
      name: 'status',
      type: 'string',
      variant: { type: 'select', options: [{ value: 'a', label: 'A' }] },
    });
    expect(resolveFieldKind(field)).toBe('select');
  });

  // -------------------------------------------------------------------
  // 9. checkbox
  // -------------------------------------------------------------------
  it('returns "checkbox" for boolean with checkbox variant', () => {
    const field = makeField({
      name: 'active',
      type: 'boolean',
      variant: { type: 'checkbox' },
    });
    expect(resolveFieldKind(field)).toBe('checkbox');
  });

  // -------------------------------------------------------------------
  // 10. switch (default boolean)
  // -------------------------------------------------------------------
  it('returns "switch" for boolean without explicit variant', () => {
    const field = makeField({ name: 'enabled', type: 'boolean' });
    expect(resolveFieldKind(field)).toBe('switch');
  });

  // -------------------------------------------------------------------
  // 11. date
  // -------------------------------------------------------------------
  it('returns "date" for date type', () => {
    const field = makeField({ name: 'createdAt', type: 'date' });
    expect(resolveFieldKind(field)).toBe('date');
  });

  it('returns "date" when variant is date', () => {
    const field = makeField({
      name: 'expiry',
      type: 'string',
      variant: { type: 'date' },
    });
    expect(resolveFieldKind(field)).toBe('date');
  });

  // -------------------------------------------------------------------
  // 12. numberSlider
  // -------------------------------------------------------------------
  it('returns "numberSlider" for number with slider variant', () => {
    const field = makeField({
      name: 'volume',
      type: 'number',
      variant: { type: 'slider', sliderMin: 0, sliderMax: 100 },
    });
    expect(resolveFieldKind(field)).toBe('numberSlider');
  });

  // -------------------------------------------------------------------
  // 13. number
  // -------------------------------------------------------------------
  it('returns "number" for number type without slider', () => {
    const field = makeField({ name: 'age', type: 'number' });
    expect(resolveFieldKind(field)).toBe('number');
  });

  // -------------------------------------------------------------------
  // 14. textarea
  // -------------------------------------------------------------------
  it('returns "textarea" when variant is textarea', () => {
    const field = makeField({
      name: 'bio',
      type: 'string',
      variant: { type: 'textarea', rows: 5 },
    });
    expect(resolveFieldKind(field)).toBe('textarea');
  });

  // -------------------------------------------------------------------
  // 15-16. refResourceId / refResourceIdMulti
  // -------------------------------------------------------------------
  it('returns "refResourceId" for single resource_id ref', () => {
    const field = makeField({
      name: 'ownerId',
      type: 'string',
      ref: { resource: 'users', type: 'resource_id' },
    });
    expect(resolveFieldKind(field)).toBe('refResourceId');
  });

  it('returns "refResourceIdMulti" for array resource_id ref', () => {
    const field = makeField({
      name: 'memberIds',
      type: 'string',
      isArray: true,
      ref: { resource: 'users', type: 'resource_id' },
    });
    expect(resolveFieldKind(field)).toBe('refResourceIdMulti');
  });

  // -------------------------------------------------------------------
  // 17-18. refRevisionId / refRevisionIdMulti
  // -------------------------------------------------------------------
  it('returns "refRevisionId" for single revision_id ref', () => {
    const field = makeField({
      name: 'snapshotId',
      type: 'string',
      ref: { resource: 'snapshots', type: 'revision_id' },
    });
    expect(resolveFieldKind(field)).toBe('refRevisionId');
  });

  it('returns "refRevisionIdMulti" for array revision_id ref', () => {
    const field = makeField({
      name: 'snapshotIds',
      type: 'string',
      isArray: true,
      ref: { resource: 'snapshots', type: 'revision_id' },
    });
    expect(resolveFieldKind(field)).toBe('refRevisionIdMulti');
  });

  // -------------------------------------------------------------------
  // 19. text (default)
  // -------------------------------------------------------------------
  it('returns "text" for plain string field', () => {
    const field = makeField({ name: 'username', type: 'string' });
    expect(resolveFieldKind(field)).toBe('text');
  });

  // -------------------------------------------------------------------
  // Priority: itemFields takes precedence over type-based resolution
  // -------------------------------------------------------------------
  it('itemFields takes precedence over union type', () => {
    const field = makeField({
      name: 'combo',
      type: 'union',
      unionMeta: { discriminatorField: 'kind', variants: [] },
      itemFields: [makeField({ name: 'sub', type: 'string' })],
    });
    expect(resolveFieldKind(field)).toBe('itemFields');
  });

  it('variant json takes precedence over string type', () => {
    const field = makeField({
      name: 'data',
      type: 'string',
      variant: { type: 'json' },
    });
    expect(resolveFieldKind(field)).toBe('json');
  });
});
