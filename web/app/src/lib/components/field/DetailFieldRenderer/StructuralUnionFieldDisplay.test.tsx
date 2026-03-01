/**
 * StructuralUnionFieldDisplay + CollapsibleJson — Unit tests.
 *
 * Tests cover:
 * 1. `inferVariant` — pure function for variant matching
 * 2. `StructuralUnionFieldDisplay` — rendering for each variant kind
 * 3. `CollapsibleJson` — collapse/expand behaviour
 * 4. `DetailFieldRenderer` integration — `__variant` dispatches correctly
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import type { ResourceField, UnionVariant, UnionMeta } from '../../../resources';
import { inferVariant, StructuralUnionFieldDisplay } from './StructuralUnionFieldDisplay';
import { CollapsibleJson } from './CollapsibleJson';
import { DetailFieldRenderer } from './index';

function wrap(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

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

// ============================================================================
// inferVariant — pure function tests
// ============================================================================

describe('inferVariant', () => {
  const arrayVariantWithUnionMeta: UnionVariant = {
    tag: 'list_union',
    label: 'List (Union)',
    isArray: true,
    itemUnionMeta: {
      discriminatorField: 'type',
      variants: [
        { tag: 'A', label: 'A', fields: [makeField({ name: 'a_field' })] },
        { tag: 'B', label: 'B', fields: [makeField({ name: 'b_field' })] },
      ],
    },
  };

  const arrayVariantWithFields: UnionVariant = {
    tag: 'list_EventBodyA',
    label: 'List EventBodyA',
    isArray: true,
    fields: [
      makeField({ name: 'event_type' }),
      makeField({ name: 'damage', type: 'number' }),
    ],
  };

  const dictVariant: UnionVariant = {
    tag: 'dict_EventBodyX',
    label: 'Dict EventBodyX',
    isDict: true,
    dictValueFields: [
      makeField({ name: 'good' }),
      makeField({ name: 'great', type: 'number' }),
    ],
  };

  const objectVariantX: UnionVariant = {
    tag: 'EventBodyX',
    label: 'EventBodyX',
    schemaName: 'EventBodyX',
    fields: [
      makeField({ name: 'type', constValue: 'EventBodyX' }),
      makeField({ name: 'good' }),
      makeField({ name: 'great', type: 'number' }),
    ],
  };

  const objectVariantB: UnionVariant = {
    tag: 'EventBodyB',
    label: 'EventBodyB',
    schemaName: 'EventBodyB',
    fields: [
      makeField({ name: 'type', constValue: 'EventBodyB' }),
      makeField({ name: 'quality' }),
    ],
  };

  const allVariants = [
    arrayVariantWithUnionMeta,
    objectVariantX,
    objectVariantB,
  ];

  it('returns null for null/undefined value', () => {
    expect(inferVariant(null, allVariants)).toBeNull();
    expect(inferVariant(undefined, allVariants)).toBeNull();
  });

  it('returns null for primitive value', () => {
    expect(inferVariant(42, allVariants)).toBeNull();
    expect(inferVariant('hello', allVariants)).toBeNull();
  });

  it('matches array value to array variant', () => {
    const result = inferVariant([{ type: 'A', a_field: 'x' }], allVariants);
    expect(result).toBe(arrayVariantWithUnionMeta);
  });

  it('prefers array variant with itemUnionMeta over plain fields', () => {
    const variants = [arrayVariantWithFields, arrayVariantWithUnionMeta];
    const result = inferVariant([{ something: 'data' }], variants);
    expect(result).toBe(arrayVariantWithUnionMeta);
  });

  it('falls back to plain array variant if no itemUnionMeta', () => {
    const variants = [arrayVariantWithFields];
    const result = inferVariant([{ event_type: 'x', damage: 10 }], variants);
    expect(result).toBe(arrayVariantWithFields);
  });

  it('returns null for array value when no array variants exist', () => {
    const result = inferVariant([1, 2, 3], [objectVariantX, objectVariantB]);
    expect(result).toBeNull();
  });

  it('matches dict value to dict variant', () => {
    const variants = [arrayVariantWithFields, dictVariant, objectVariantX];
    const value = { key1: { good: 'a', great: 1 }, key2: { good: 'b', great: 2 } };
    const result = inferVariant(value, variants);
    expect(result).toBe(dictVariant);
  });

  it('does not match dict variant for empty object', () => {
    const variants = [dictVariant, objectVariantX];
    // Empty object has 0 keys, so dict check skipped → falls to object overlap
    const result = inferVariant({}, variants);
    // No keys to overlap → null
    expect(result).toBeNull();
  });

  it('does not match dict variant when values are not all objects', () => {
    const variants = [dictVariant, objectVariantX];
    const value = { key1: 'string_value', key2: 42 };
    const result = inferVariant(value, variants);
    // Not all values are objects → skip dict → try object overlap
    // keys = ['key1', 'key2'], objectVariantX fields = ['type', 'good', 'great'] → 0 overlap
    expect(result).toBeNull();
  });

  it('matches object value to variant with highest key overlap', () => {
    const value = { type: 'EventBodyX', good: 'hello', great: 42 };
    const result = inferVariant(value, [objectVariantX, objectVariantB]);
    expect(result).toBe(objectVariantX);
  });

  it('matches object value to variant B when keys overlap better', () => {
    const value = { type: 'EventBodyB', quality: 'excellent' };
    const result = inferVariant(value, [objectVariantX, objectVariantB]);
    expect(result).toBe(objectVariantB);
  });

  it('returns null when no object keys overlap any variant fields', () => {
    const value = { unknown_field: 'data' };
    const result = inferVariant(value, [objectVariantX, objectVariantB]);
    expect(result).toBeNull();
  });
});

// ============================================================================
// CollapsibleJson
// ============================================================================

describe('CollapsibleJson', () => {
  it('renders N/A for null value', () => {
    wrap(<CollapsibleJson value={null} />);
    expect(screen.getByText('N/A')).toBeTruthy();
  });

  it('renders primitive value inline', () => {
    wrap(<CollapsibleJson value={42} />);
    expect(screen.getByText('42')).toBeTruthy();
  });

  it('renders small object directly (no collapse)', () => {
    wrap(<CollapsibleJson value={{ a: 1 }} />);
    // Should show the JSON inline (small enough)
    expect(screen.getByText(/\"a\": 1/)).toBeTruthy();
  });

  it('renders large object collapsed by default with summary', () => {
    const largeObj: Record<string, string> = {};
    for (let i = 0; i < 20; i++) {
      largeObj[`key_${i}`] = `value_${i}_with_some_extra_content`;
    }
    wrap(<CollapsibleJson value={largeObj} />);
    // Should show summary
    expect(screen.getByText('{20 keys}')).toBeTruthy();
    // Should NOT show the full JSON yet
    expect(screen.queryByText(/"key_0"/)).toBeNull();
  });

  it('expands when clicked', () => {
    const largeObj: Record<string, string> = {};
    for (let i = 0; i < 20; i++) {
      largeObj[`key_${i}`] = `value_${i}_with_some_extra_content`;
    }
    wrap(<CollapsibleJson value={largeObj} />);

    // Click to expand
    const buttons = screen.getAllByText('{20 keys}');
    fireEvent.click(buttons[0]);
    // Now the full JSON should be visible
    expect(screen.getByText(/"key_0"/)).toBeTruthy();
  });

  it('shows defaultExpanded=true', () => {
    const largeArr = Array.from({ length: 20 }, (_, i) => ({ id: i, name: `item_${i}_padded` }));
    wrap(<CollapsibleJson value={largeArr} defaultExpanded />);
    // Should show JSON immediately
    expect(screen.getByText(/"id": 0/)).toBeTruthy();
  });

  it('shows array summary correctly', () => {
    const arr = Array.from({ length: 5 }, (_, i) => ({
      id: i,
      data: `some_long_string_to_exceed_120_chars_${i}`,
    }));
    wrap(<CollapsibleJson value={arr} />);
    expect(screen.getByText('[5 items]')).toBeTruthy();
  });

  it('singular item text for single-element array', () => {
    const arr = [{ id: 1, data: 'some_long_string_to_make_over_120_chars_padding_padding_padding_padding_padding_padding_padding_padding' }];
    wrap(<CollapsibleJson value={arr} />);
    expect(screen.getByText('[1 item]')).toBeTruthy();
  });
});

// ============================================================================
// StructuralUnionFieldDisplay — rendering tests
// ============================================================================

describe('StructuralUnionFieldDisplay', () => {
  const objectVariantX: UnionVariant = {
    tag: 'EventBodyX',
    label: 'EventBodyX',
    fields: [
      makeField({ name: 'good' }),
      makeField({ name: 'great', type: 'number' }),
    ],
  };

  const objectVariantB: UnionVariant = {
    tag: 'EventBodyB',
    label: 'EventBodyB',
    fields: [
      makeField({ name: 'quality' }),
    ],
  };

  const arrayVariantWithUnionMeta: UnionVariant = {
    tag: 'list_union',
    label: 'List (Union)',
    isArray: true,
    itemUnionMeta: {
      discriminatorField: 'type',
      variants: [
        { tag: 'EventBodyX', label: 'EventBodyX', fields: [makeField({ name: 'good' })] },
        { tag: 'EventBodyB', label: 'EventBodyB', fields: [makeField({ name: 'quality' })] },
      ],
    },
  };

  const arrayVariantWithFields: UnionVariant = {
    tag: 'list_EventBodyA',
    label: 'List EventBodyA',
    isArray: true,
    fields: [
      makeField({ name: 'event_type' }),
      makeField({ name: 'damage', type: 'number' }),
    ],
  };

  const dictVariant: UnionVariant = {
    tag: 'dict_EventBodyX',
    label: 'Dict EventBodyX',
    isDict: true,
    dictValueFields: [
      makeField({ name: 'good' }),
      makeField({ name: 'great', type: 'number' }),
    ],
  };

  const unionMeta: UnionMeta = {
    discriminatorField: '__variant',
    variants: [arrayVariantWithUnionMeta, objectVariantX, objectVariantB],
  };

  it('renders object variant with fields as nested table', () => {
    const value = { good: 'hello', great: 42 };
    const { container } = wrap(
      <StructuralUnionFieldDisplay
        value={value}
        unionMeta={unionMeta}
        renderValue={({ value: v }) => <span data-testid="rv">{String(v)}</span>}
      />,
    );

    // Sub-field labels and values rendered (no Badge label)
    expect(container.textContent).toContain('good');
    expect(container.textContent).toContain('great');
    expect(container.textContent).toContain('hello');
    expect(container.textContent).toContain('42');
  });

  it('renders array variant with itemUnionMeta', () => {
    const value = [
      { type: 'EventBodyX', good: 'sword' },
      { type: 'EventBodyB', quality: 'A+' },
    ];
    const { container } = wrap(
      <StructuralUnionFieldDisplay
        value={value}
        unionMeta={unionMeta}
        renderValue={({ value: v }) => <span data-testid="rv">{String(v)}</span>}
      />,
    );

    // Item badges (from UnionFieldDisplay)
    expect(container.textContent).toContain('EventBodyX');
    expect(container.textContent).toContain('EventBodyB');
    // Sub-field values
    expect(container.textContent).toContain('sword');
    expect(container.textContent).toContain('A+');
  });

  it('renders array variant with fixed fields', () => {
    const meta: UnionMeta = {
      discriminatorField: '__variant',
      variants: [arrayVariantWithFields, objectVariantX],
    };
    const value = [
      { event_type: 'explosion', damage: 100 },
      { event_type: 'heal', damage: -50 },
    ];
    wrap(
      <StructuralUnionFieldDisplay
        value={value}
        unionMeta={meta}
        renderValue={({ value: v }) => <span>{String(v)}</span>}
      />,
    );

    expect(screen.getByText('explosion')).toBeTruthy();
    expect(screen.getByText('100')).toBeTruthy();
    expect(screen.getByText('heal')).toBeTruthy();
  });

  it('renders empty array', () => {
    const { container } = wrap(
      <StructuralUnionFieldDisplay
        value={[]}
        unionMeta={unionMeta}
        renderValue={({ value: v }) => <span>{String(v)}</span>}
      />,
    );

    expect(container.textContent).toContain('No items');
  });

  it('renders dict variant with dictValueFields', () => {
    const meta: UnionMeta = {
      discriminatorField: '__variant',
      variants: [arrayVariantWithFields, dictVariant],
    };
    const value = {
      warrior: { good: 'sword', great: 10 },
      mage: { good: 'staff', great: 20 },
    };
    const { container } = wrap(
      <StructuralUnionFieldDisplay
        value={value}
        unionMeta={meta}
        renderValue={({ value: v }) => <span data-testid="rv">{String(v)}</span>}
      />,
    );

    expect(container.textContent).toContain('warrior');
    expect(container.textContent).toContain('mage');
    expect(container.textContent).toContain('sword');
    expect(container.textContent).toContain('staff');
  });

  it('falls back to JSON for unmatched value', () => {
    const meta: UnionMeta = {
      discriminatorField: '__variant',
      variants: [objectVariantX],
    };
    // Value has no key overlap with objectVariantX fields
    const value = { completely: 'unknown', data: 'here' };
    const { container } = wrap(
      <StructuralUnionFieldDisplay
        value={value}
        unionMeta={meta}
        renderValue={({ value: v }) => <span>{String(v)}</span>}
      />,
    );

    // Should render JSON (no badge), the variant label should NOT appear
    // Check that the JSON content is present
    expect(container.textContent).toContain('completely');
    expect(container.textContent).toContain('unknown');
  });

  it('falls back to JSON for null value', () => {
    const { container } = wrap(
      <StructuralUnionFieldDisplay
        value={null}
        unionMeta={unionMeta}
        renderValue={({ value: v }) => <span>{String(v)}</span>}
      />,
    );

    expect(container.textContent).toContain('N/A');
  });
});

// ============================================================================
// DetailFieldRenderer integration — __variant dispatch
// ============================================================================

describe('DetailFieldRenderer — structural union (__variant)', () => {
  const structuralUnionField: ResourceField = makeField({
    name: 'event_x5',
    type: 'union',
    unionMeta: {
      discriminatorField: '__variant',
      variants: [
        {
          tag: 'list_EventBodyA',
          label: 'List EventBodyA',
          isArray: true,
          fields: [
            makeField({ name: 'event_type' }),
            makeField({ name: 'damage', type: 'number' }),
          ],
        },
        {
          tag: 'EventBodyX',
          label: 'EventBodyX',
          fields: [
            makeField({ name: 'good' }),
            makeField({ name: 'great', type: 'number' }),
          ],
        },
      ],
    },
  });

  it('dispatches __variant union to StructuralUnionFieldDisplay', () => {
    const value = { good: 'hello', great: 42 };
    const { container } = wrap(<DetailFieldRenderer field={structuralUnionField} value={value} data={{}} />);

    // Should render sub-field values (no Badge label)
    expect(container.textContent).toContain('hello');
    expect(container.textContent).toContain('42');
  });

  it('dispatches __variant union array to StructuralUnionFieldDisplay', () => {
    const value = [
      { event_type: 'explosion', damage: 100 },
      { event_type: 'heal', damage: -50 },
    ];
    const { container } = wrap(<DetailFieldRenderer field={structuralUnionField} value={value} data={{}} />);

    expect(container.textContent).toContain('explosion');
  });

  it('simple union (__type) still shows as JSON', () => {
    const simpleUnionField: ResourceField = makeField({
      name: 'mixed',
      type: 'union',
      unionMeta: {
        discriminatorField: '__type',
        variants: [
          { tag: 'string', label: 'String', type: 'string' },
          { tag: 'number', label: 'Number', type: 'number' },
        ],
      },
    });
    const { container } = wrap(<DetailFieldRenderer field={simpleUnionField} value="hello world" data={{}} />);
    // Should render as string fallback, not crash
    expect(container.textContent).toContain('hello world');
  });

  it('discriminated union (real field) still works', () => {
    const discUnionField: ResourceField = makeField({
      name: 'skill_data',
      type: 'union',
      unionMeta: {
        discriminatorField: 'type',
        variants: [
          {
            tag: 'active',
            label: 'Active Skill',
            fields: [makeField({ name: 'cooldown', type: 'number' })],
          },
        ],
      },
    });
    const value = { type: 'active', cooldown: 5 };
    wrap(<DetailFieldRenderer field={discUnionField} value={value} data={{}} />);

    expect(screen.getByText('Active Skill')).toBeTruthy();
    expect(screen.getByText('5')).toBeTruthy();
  });
});
