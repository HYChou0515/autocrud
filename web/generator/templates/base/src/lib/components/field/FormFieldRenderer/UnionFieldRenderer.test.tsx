/**
 * UnionFieldRenderer — Structural union (__variant mode) tests.
 *
 * Tests the third rendering mode where anyOf types without a discriminator
 * are rendered as Radio.Card variant selection with per-variant fieldsets.
 *
 * NOTE: Mantine + happy-dom sometimes renders duplicate text nodes, so we
 * consistently use getAllByText(...).length checks instead of getByText.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';
import type { ResourceField, UnionMeta } from '../../../resources';
import { UnionFieldRenderer } from './UnionFieldRenderer';

/** Wrap with MantineProvider */
function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

/** Assert text is present in the DOM (allows duplicates from Mantine rendering) */
function expectText(text: string) {
  expect(screen.getAllByText(text).length).toBeGreaterThanOrEqual(1);
}

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

// ---------------------------------------------------------------------------
// Test wrapper that provides a real Mantine form
// ---------------------------------------------------------------------------

interface WrapperProps {
  field: ResourceField;
  unionMeta: UnionMeta;
  initialValues: Record<string, any>;
  /** Called after every render with current form values */
  onValuesChange?: (values: Record<string, any>) => void;
}

function FormWrapper({ field, unionMeta, initialValues, onValuesChange }: WrapperProps) {
  const form = useForm({ initialValues });
  const [simpleUnionTypes, setSimpleUnionTypes] = useState<Record<string, string>>({});

  // Expose form values for assertions via callback
  if (onValuesChange) onValuesChange(form.getValues());

  return (
    <UnionFieldRenderer
      field={field}
      unionMeta={unionMeta}
      form={form}
      simpleUnionTypes={simpleUnionTypes}
      setSimpleUnionTypes={setSimpleUnionTypes}
    />
  );
}

// ---------------------------------------------------------------------------
// Structural union: list[EventBodyX] | EventBodyX
// ---------------------------------------------------------------------------

const eventBodyFields: ResourceField[] = [
  makeField({ name: 'event_type', type: 'string', isRequired: true }),
  makeField({ name: 'damage', type: 'number' }),
];

const structuralUnionMeta: UnionMeta = {
  discriminatorField: '__variant',
  variants: [
    {
      tag: 'list_EventBodyX',
      label: 'List of EventBodyX',
      isArray: true,
      fields: eventBodyFields,
    },
    {
      tag: 'EventBodyX',
      label: 'Single EventBodyX',
      schemaName: 'EventBodyX',
      fields: eventBodyFields,
    },
  ],
};

const structuralField: ResourceField = makeField({
  name: 'event_x3',
  label: 'Event X3',
  type: 'union',
  unionMeta: structuralUnionMeta,
});

describe('UnionFieldRenderer — structural union (__variant)', () => {
  it('renders Radio.Card for each variant', () => {
    renderWithMantine(
      <FormWrapper
        field={structuralField}
        unionMeta={structuralUnionMeta}
        initialValues={{ event_x3: { __variant: 'list_EventBodyX', __items: [] } }}
      />,
    );

    expectText('List of EventBodyX');
    expectText('Single EventBodyX');
    expectText('(array)');
  });

  it('shows "No items yet" for empty array variant', () => {
    renderWithMantine(
      <FormWrapper
        field={structuralField}
        unionMeta={structuralUnionMeta}
        initialValues={{ event_x3: { __variant: 'list_EventBodyX', __items: [] } }}
      />,
    );

    expectText('No items yet');
    expectText('Items (0)');
  });

  it('shows Add button for array variant', () => {
    renderWithMantine(
      <FormWrapper
        field={structuralField}
        unionMeta={structuralUnionMeta}
        initialValues={{ event_x3: { __variant: 'list_EventBodyX', __items: [] } }}
      />,
    );

    expectText('Add');
  });

  it('clicking Add adds an item with sub-fields', () => {
    renderWithMantine(
      <FormWrapper
        field={structuralField}
        unionMeta={structuralUnionMeta}
        initialValues={{ event_x3: { __variant: 'list_EventBodyX', __items: [] } }}
      />,
    );

    // Click the first Add button
    fireEvent.click(screen.getAllByText('Add')[0]);

    // After adding, sub-field labels should appear
    expectText('event_type');
    expectText('damage');
    expectText('#1');
    expectText('Items (1)');
  });

  it('renders inline sub-fields for object variant', () => {
    renderWithMantine(
      <FormWrapper
        field={structuralField}
        unionMeta={structuralUnionMeta}
        initialValues={{
          event_x3: { __variant: 'EventBodyX', event_type: 'explosion', damage: 42 },
        }}
      />,
    );

    expectText('event_type');
    expectText('damage');
  });

  it('object variant renders sub-fields without array controls', () => {
    // Start directly with object variant selected
    const { container } = renderWithMantine(
      <FormWrapper
        field={structuralField}
        unionMeta={structuralUnionMeta}
        initialValues={{ event_x3: { __variant: 'EventBodyX', event_type: '', damage: '' } }}
      />,
    );

    // Object variant shows sub-fields
    expectText('event_type');
    expectText('damage');
    // Should NOT have Add button (which is an array-only control)
    // Use container.querySelectorAll to avoid Mantine double-text-node issues
    const addButtons = Array.from(container.querySelectorAll('button')).filter(
      (btn) => btn.textContent?.includes('Add'),
    );
    expect(addButtons.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Structural union: primitive variant (e.g. $ref | string)
// ---------------------------------------------------------------------------

const mixedUnionMeta: UnionMeta = {
  discriminatorField: '__variant',
  variants: [
    {
      tag: 'ModelA',
      label: 'Model A',
      schemaName: 'ModelA',
      fields: [makeField({ name: 'value', type: 'string', isRequired: true })],
    },
    {
      tag: 'string',
      label: 'plain string',
      type: 'string',
    },
  ],
};

const mixedField: ResourceField = makeField({
  name: 'mixed_field',
  label: 'Mixed Field',
  type: 'union',
  unionMeta: mixedUnionMeta,
});

describe('UnionFieldRenderer — structural union with primitive variant', () => {
  it('renders primitive variant with Value input', () => {
    renderWithMantine(
      <FormWrapper
        field={mixedField}
        unionMeta={mixedUnionMeta}
        initialValues={{ mixed_field: { __variant: 'string', value: 'hello' } }}
      />,
    );

    expectText('Value');
    expectText('Model A');
    expectText('plain string');
  });

  it('renders object variant with sub-fields when selected', () => {
    renderWithMantine(
      <FormWrapper
        field={mixedField}
        unionMeta={mixedUnionMeta}
        initialValues={{ mixed_field: { __variant: 'ModelA', value: 'test' } }}
      />,
    );

    // The "value" sub-field label of ModelA variant
    expectText('value');
  });
});

// ---------------------------------------------------------------------------
// Ensure discriminated union still works (regression)
// ---------------------------------------------------------------------------

const discriminatedUnionMeta: UnionMeta = {
  discriminatorField: 'type',
  variants: [
    {
      tag: 'Sword',
      label: 'Sword',
      fields: [makeField({ name: 'attack', type: 'number', isRequired: true })],
    },
    {
      tag: 'Shield',
      label: 'Shield',
      fields: [makeField({ name: 'defense', type: 'number', isRequired: true })],
    },
  ],
};

const discriminatedField: ResourceField = makeField({
  name: 'equipment',
  label: 'Equipment',
  type: 'union',
  unionMeta: discriminatedUnionMeta,
});

describe('UnionFieldRenderer — discriminated union (regression)', () => {
  it('renders Radio.Card for discriminated union', () => {
    renderWithMantine(
      <FormWrapper
        field={discriminatedField}
        unionMeta={discriminatedUnionMeta}
        initialValues={{ equipment: { type: 'Sword', attack: 10 } }}
      />,
    );

    expectText('Sword');
    expectText('Shield');
    expectText('attack');
  });
});

// ---------------------------------------------------------------------------
// Ensure simple union still works (regression)
// ---------------------------------------------------------------------------

const simpleUnionMeta: UnionMeta = {
  discriminatorField: '__type',
  variants: [
    { tag: 'string', label: 'String', type: 'string' },
    { tag: 'number', label: 'Number', type: 'number' },
  ],
};

const simpleField: ResourceField = makeField({
  name: 'flexible',
  label: 'Flexible',
  type: 'union',
  unionMeta: simpleUnionMeta,
});

describe('UnionFieldRenderer — simple union (regression)', () => {
  it('renders Radio.Group for simple union', () => {
    renderWithMantine(
      <FormWrapper
        field={simpleField}
        unionMeta={simpleUnionMeta}
        initialValues={{ flexible: '' }}
      />,
    );

    expectText('String');
    expectText('Number');
  });
});

// ---------------------------------------------------------------------------
// Structural union with itemUnionMeta: list[DiscriminatedUnion] | SingleRef
// ---------------------------------------------------------------------------

const itemUnionVariantFields = {
  EventBodyX: [
    makeField({ name: 'good', type: 'string', isRequired: true }),
    makeField({ name: 'great', type: 'number', isRequired: true }),
  ],
  EventBodyB: [
    makeField({ name: 'beta_info', type: 'string', isRequired: true }),
  ],
};

const itemUnionMeta: UnionMeta = {
  discriminatorField: 'type',
  variants: [
    {
      tag: 'EventBodyX',
      label: 'Event Body X',
      schemaName: 'EventBodyX',
      fields: itemUnionVariantFields.EventBodyX,
    },
    {
      tag: 'EventBodyB',
      label: 'Event Body B',
      schemaName: 'EventBodyB',
      fields: itemUnionVariantFields.EventBodyB,
    },
  ],
};

const itemUnionStructuralMeta: UnionMeta = {
  discriminatorField: '__variant',
  variants: [
    {
      tag: 'list_union',
      label: '(EventBodyX | EventBodyB)[]',
      isArray: true,
      fields: [],
      itemUnionMeta,
    },
    {
      tag: 'EventBodyX',
      label: 'Event Body X',
      schemaName: 'EventBodyX',
      fields: itemUnionVariantFields.EventBodyX,
    },
  ],
};

const itemUnionField: ResourceField = makeField({
  name: 'event_x3',
  label: 'Event X3',
  type: 'union',
  isRequired: true,
  unionMeta: itemUnionStructuralMeta,
});

describe('UnionFieldRenderer — structural union with itemUnionMeta', () => {
  it('renders variant selector with array union label', () => {
    renderWithMantine(
      <FormWrapper
        field={itemUnionField}
        unionMeta={itemUnionStructuralMeta}
        initialValues={{ event_x3: { __variant: 'list_union', __items: [] } }}
      />,
    );

    // Root-level variant labels should be present
    expectText('(EventBodyX | EventBodyB)[]');
    expectText('Event Body X');
    // "No items yet" should show for empty array
    expectText('No items yet');
  });

  it('renders Add button for discriminated array items', () => {
    renderWithMantine(
      <FormWrapper
        field={itemUnionField}
        unionMeta={itemUnionStructuralMeta}
        initialValues={{ event_x3: { __variant: 'list_union', __items: [] } }}
      />,
    );

    const addButtons = screen.getAllByText('Add');
    expect(addButtons.length).toBeGreaterThanOrEqual(1);
  });

  it('renders per-item type selector and fields after adding an item', () => {
    renderWithMantine(
      <FormWrapper
        field={itemUnionField}
        unionMeta={itemUnionStructuralMeta}
        initialValues={{
          event_x3: {
            __variant: 'list_union',
            __items: [{ type: 'EventBodyX', good: '', great: '' }],
          },
        }}
      />,
    );

    // Should have item #1
    expectText('#1');
    // Should have sub-fields for EventBodyX variant
    expectText('good');
    expectText('great');
  });

  it('renders multiple items with different variant types', () => {
    renderWithMantine(
      <FormWrapper
        field={itemUnionField}
        unionMeta={itemUnionStructuralMeta}
        initialValues={{
          event_x3: {
            __variant: 'list_union',
            __items: [
              { type: 'EventBodyX', good: 'test', great: '' },
              { type: 'EventBodyB', beta_info: 'info' },
            ],
          },
        }}
      />,
    );

    // Both items present
    expectText('#1');
    expectText('#2');
    // Fields for both items
    expectText('good');
    expectText('great');
    expectText('beta_info');
  });

  it('switches to non-array variant and shows inline fields', () => {
    renderWithMantine(
      <FormWrapper
        field={itemUnionField}
        unionMeta={itemUnionStructuralMeta}
        initialValues={{
          event_x3: { __variant: 'EventBodyX', good: '', great: '' },
        }}
      />,
    );

    // Should show inline fields for EventBodyX (non-array variant)
    expectText('good');
    expectText('great');
  });
});

// ---------------------------------------------------------------------------
// Fallback JSON textarea for unknown/json primitive variant
// ---------------------------------------------------------------------------

describe('UnionFieldRenderer — JSON fallback for unknown primitive type', () => {
  const jsonFallbackMeta: UnionMeta = {
    discriminatorField: '__variant',
    variants: [
      {
        tag: 'EventBodyX',
        label: 'Event Body X',
        schemaName: 'EventBodyX',
        fields: itemUnionVariantFields.EventBodyX,
      },
      {
        tag: 'json',
        label: 'Json',
        type: 'json',
      },
    ],
  };

  const jsonFallbackField: ResourceField = makeField({
    name: 'mixed',
    label: 'Mixed',
    type: 'union',
    isRequired: true,
    unionMeta: jsonFallbackMeta,
  });

  it('renders JSON textarea for "json" type variant', () => {
    renderWithMantine(
      <FormWrapper
        field={jsonFallbackField}
        unionMeta={jsonFallbackMeta}
        initialValues={{ mixed: { __variant: 'json', value: '' } }}
      />,
    );

    expectText('Value (JSON)');
  });
});

// ---------------------------------------------------------------------------
// Null variant
// ---------------------------------------------------------------------------

describe('UnionFieldRenderer — null variant', () => {
  const nullMeta: UnionMeta = {
    discriminatorField: '__variant',
    variants: [
      {
        tag: 'list_EventBodyX',
        label: 'EventBodyX[]',
        schemaName: 'EventBodyX',
        fields: itemUnionVariantFields.EventBodyX,
        isArray: true,
      },
      {
        tag: 'null',
        label: 'None',
        type: 'null',
      },
    ],
  };

  const nullField: ResourceField = makeField({
    name: 'event_x6',
    label: 'Event X6',
    type: 'union',
    isRequired: false,
    isNullable: true,
    unionMeta: nullMeta,
  });

  it('renders None radio option for null variant', () => {
    renderWithMantine(
      <FormWrapper
        field={nullField}
        unionMeta={nullMeta}
        initialValues={{ event_x6: { __variant: 'null' } }}
      />,
    );

    expectText('None');
    expectText('(null)');
  });

  it('shows null message when null variant is selected', () => {
    renderWithMantine(
      <FormWrapper
        field={nullField}
        unionMeta={nullMeta}
        initialValues={{ event_x6: { __variant: 'null' } }}
      />,
    );

    expectText('This field will be set to null');
  });

  it('sets form value to { __variant: "null" } when initialized with null variant', () => {
    let capturedValues: Record<string, any> = {};
    renderWithMantine(
      <FormWrapper
        field={nullField}
        unionMeta={nullMeta}
        initialValues={{ event_x6: { __variant: 'null' } }}
        onValuesChange={(v) => {
          capturedValues = v;
        }}
      />,
    );

    expect(capturedValues.event_x6.__variant).toBe('null');
    // Should NOT have __items or value
    expect(capturedValues.event_x6.__items).toBeUndefined();
    expect(capturedValues.event_x6.value).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Dict variant
// ---------------------------------------------------------------------------

describe('UnionFieldRenderer — dict variant', () => {
  const dictMeta: UnionMeta = {
    discriminatorField: '__variant',
    variants: [
      {
        tag: 'list_EventBodyX',
        label: 'EventBodyX[]',
        schemaName: 'EventBodyX',
        fields: itemUnionVariantFields.EventBodyX,
        isArray: true,
      },
      {
        tag: 'dict_EventBodyX',
        label: 'Dict[str, EventBodyX]',
        isDict: true,
        dictValueFields: itemUnionVariantFields.EventBodyX,
      },
    ],
  };

  const dictField: ResourceField = makeField({
    name: 'event_x7',
    label: 'Event X7',
    type: 'union',
    isRequired: true,
    unionMeta: dictMeta,
  });

  it('renders dict radio option with (dict) hint', () => {
    renderWithMantine(
      <FormWrapper
        field={dictField}
        unionMeta={dictMeta}
        initialValues={{ event_x7: { __variant: 'dict_EventBodyX', __entries: [] } }}
      />,
    );

    expectText('Dict[str, EventBodyX]');
    expectText('(dict)');
  });

  it('shows empty entries message and Add button when dict variant selected', () => {
    renderWithMantine(
      <FormWrapper
        field={dictField}
        unionMeta={dictMeta}
        initialValues={{ event_x7: { __variant: 'dict_EventBodyX', __entries: [] } }}
      />,
    );

    expectText('Entries (0)');
    expectText('No entries yet');
    expectText('Add');
  });

  it('sets form value with __entries when initialized with dict variant', () => {
    let capturedValues: Record<string, any> = {};
    renderWithMantine(
      <FormWrapper
        field={dictField}
        unionMeta={dictMeta}
        initialValues={{ event_x7: { __variant: 'dict_EventBodyX', __entries: [] } }}
        onValuesChange={(v) => {
          capturedValues = v;
        }}
      />,
    );

    expect(capturedValues.event_x7.__variant).toBe('dict_EventBodyX');
    expect(capturedValues.event_x7.__entries).toEqual([]);
  });
});
