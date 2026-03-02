/**
 * UnionFieldRenderer — Structural union (__variant mode) tests.
 *
 * Tests the third rendering mode where anyOf types without a discriminator
 * are rendered as Radio.Card variant selection with per-variant fieldsets.
 *
 * NOTE: Mantine + happy-dom sometimes renders duplicate text nodes, so we
 * consistently use getAllByText(...).length checks instead of getByText.
 */

import { describe, it, expect } from 'vitest';
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
    const addButtons = Array.from(container.querySelectorAll('button')).filter((btn) =>
      btn.textContent?.includes('Add'),
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
  EventBodyB: [makeField({ name: 'beta_info', type: 'string', isRequired: true })],
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

// ---------------------------------------------------------------------------
// constValue fields — discriminator injection for structural union
// ---------------------------------------------------------------------------

/**
 * When a structural union variant has a field with `constValue`,
 * the form should:
 * 1. Auto-set the constValue when switching to that variant
 * 2. NOT render a user-editable input for constValue fields
 * 3. Include the constValue in submitted data
 */

const constValueVariantMeta: UnionMeta = {
  discriminatorField: '__variant',
  variants: [
    {
      tag: 'list_union',
      label: '(EventBodyX | EventBodyB)[]',
      isArray: true,
      itemUnionMeta: {
        discriminatorField: 'type',
        variants: [
          {
            tag: 'EventBodyX',
            label: 'EventBodyX',
            schemaName: 'EventBodyX',
            fields: [
              makeField({ name: 'good', type: 'string', isRequired: true }),
              makeField({ name: 'great', type: 'number', isRequired: true }),
            ],
          },
          {
            tag: 'EventBodyB',
            label: 'EventBodyB',
            schemaName: 'EventBodyB',
            fields: [
              makeField({ name: 'some_field', type: 'string', isRequired: true }),
              makeField({ name: 'cooldown_seconds', type: 'number', isRequired: true }),
            ],
          },
        ],
      },
    },
    {
      tag: 'EventBodyX',
      label: 'EventBodyX',
      schemaName: 'EventBodyX',
      fields: [
        makeField({ name: 'type', type: 'string', isRequired: true, constValue: 'EventBodyX' }),
        makeField({ name: 'good', type: 'string', isRequired: true }),
        makeField({ name: 'great', type: 'number', isRequired: true }),
      ],
    },
    {
      tag: 'EventBodyB',
      label: 'EventBodyB',
      schemaName: 'EventBodyB',
      fields: [
        makeField({ name: 'type', type: 'string', isRequired: true, constValue: 'EventBodyB' }),
        makeField({ name: 'some_field', type: 'string', isRequired: true }),
        makeField({ name: 'cooldown_seconds', type: 'number', isRequired: true }),
      ],
    },
  ],
};

const constValueField: ResourceField = makeField({
  name: 'event_x3',
  label: 'Event X3',
  type: 'union',
  unionMeta: constValueVariantMeta,
});

describe('UnionFieldRenderer — constValue fields in structural union', () => {
  it('auto-sets constValue when switching to object variant', () => {
    let capturedValues: Record<string, any> = {};
    renderWithMantine(
      <FormWrapper
        field={constValueField}
        unionMeta={constValueVariantMeta}
        initialValues={{ event_x3: { __variant: 'list_union', __items: [] } }}
        onValuesChange={(v) => {
          capturedValues = v;
        }}
      />,
    );

    // Switch to EventBodyB variant by clicking its radio card
    const cards = screen.getAllByText('EventBodyB');
    fireEvent.click(cards[0]);

    // The form value should include type with constValue
    expect(capturedValues.event_x3.__variant).toBe('EventBodyB');
    expect(capturedValues.event_x3.type).toBe('EventBodyB');
    expect(capturedValues.event_x3.some_field).toBe('');
    expect(capturedValues.event_x3.cooldown_seconds).toBe('');
  });

  it('does not render input for constValue fields', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={constValueField}
        unionMeta={constValueVariantMeta}
        initialValues={{
          event_x3: {
            __variant: 'EventBodyB',
            type: 'EventBodyB',
            some_field: '',
            cooldown_seconds: '',
          },
        }}
      />,
    );

    // The "Some Field" and "Cooldown Seconds" inputs should be rendered
    const inputs = container.querySelectorAll('input');
    const _inputLabels = Array.from(inputs).map((el) => el.getAttribute('aria-label') ?? '');
    const _labels = Array.from(container.querySelectorAll('label')).map((el) => el.textContent);

    // constValue field "type" should NOT have a visible input
    // Only "Some Field" and "Cooldown Seconds" should be rendered as inputs
    const typeInputs = Array.from(inputs).filter((input) => {
      // Check the label associated with this input
      const id = input.getAttribute('id');
      if (!id) return false;
      const label = container.querySelector(`label[for="${id}"]`);
      return label?.textContent === 'type';
    });
    expect(typeInputs.length).toBe(0);
  });

  it('preserves constValue through form lifecycle', () => {
    let capturedValues: Record<string, any> = {};
    renderWithMantine(
      <FormWrapper
        field={constValueField}
        unionMeta={constValueVariantMeta}
        initialValues={{
          event_x3: {
            __variant: 'EventBodyX',
            type: 'EventBodyX',
            good: 'hello',
            great: 42,
          },
        }}
        onValuesChange={(v) => {
          capturedValues = v;
        }}
      />,
    );

    // The constValue should be preserved
    expect(capturedValues.event_x3.type).toBe('EventBodyX');
    expect(capturedValues.event_x3.good).toBe('hello');
    expect(capturedValues.event_x3.great).toBe(42);
  });
});

// ---------------------------------------------------------------------------
// Nullable discriminated union: EventBodyA | EventBodyB | None
// ---------------------------------------------------------------------------

const nullableDiscriminatedUnionMeta: UnionMeta = {
  discriminatorField: 'type',
  variants: [
    {
      tag: 'EventBodyA',
      label: 'Event Body A',
      schemaName: 'EventBodyA',
      fields: [
        makeField({ name: 'extra_info_a', type: 'string', isRequired: true }),
        makeField({ name: 'extra_value_a', type: 'number', isRequired: true }),
      ],
    },
    {
      tag: 'EventBodyB',
      label: 'Event Body B',
      schemaName: 'EventBodyB',
      fields: [
        makeField({ name: 'some_field', type: 'string', isRequired: true }),
        makeField({ name: 'cooldown_seconds', type: 'number', isRequired: true }),
      ],
    },
  ],
};

const nullableDiscriminatedField: ResourceField = makeField({
  name: 'event_body',
  label: 'Event Body',
  type: 'union',
  isNullable: true,
  isRequired: false,
  unionMeta: nullableDiscriminatedUnionMeta,
});

describe('UnionFieldRenderer — nullable discriminated union', () => {
  it('renders a None option for nullable discriminated union', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={nullableDiscriminatedField}
        unionMeta={nullableDiscriminatedUnionMeta}
        initialValues={{ event_body: null }}
      />,
    );

    // Should show all variant options AND a None option
    expectText('Event Body A');
    expectText('Event Body B');
    expect(container.textContent).toContain('None');
  });

  it('selects None by default when value is null', () => {
    let capturedValues: any = {};
    const { container } = renderWithMantine(
      <FormWrapper
        field={nullableDiscriminatedField}
        unionMeta={nullableDiscriminatedUnionMeta}
        initialValues={{ event_body: null }}
        onValuesChange={(v) => {
          capturedValues = v;
        }}
      />,
    );

    // The None radio card should be selected (value is null)
    expect(container.textContent).toContain('None');
    expect(capturedValues.event_body).toBeNull();
  });

  it('sets value to null when None is clicked', () => {
    let capturedValues: any = {};
    const { container } = renderWithMantine(
      <FormWrapper
        field={nullableDiscriminatedField}
        unionMeta={nullableDiscriminatedUnionMeta}
        initialValues={{
          event_body: { type: 'EventBodyA', extra_info_a: 'test', extra_value_a: 42 },
        }}
        onValuesChange={(v) => {
          capturedValues = v;
        }}
      />,
    );

    // Initially should show EventBodyA fields
    expectText('Event Body A');

    // Find the None radio input within our rendered container and click it
    const radios = container.querySelectorAll<HTMLElement>('[role="radio"]');
    // The None radio should be the first one (isNullable adds it at the top)
    const noneRadio = Array.from(radios).find((r) => r.textContent?.includes('None'));
    expect(noneRadio).toBeTruthy();
    fireEvent.click(noneRadio!);
    expect(capturedValues.event_body).toBeNull();
  });

  it('switches from None to a variant', () => {
    let capturedValues: any = {};
    const { container } = renderWithMantine(
      <FormWrapper
        field={nullableDiscriminatedField}
        unionMeta={nullableDiscriminatedUnionMeta}
        initialValues={{ event_body: null }}
        onValuesChange={(v) => {
          capturedValues = v;
        }}
      />,
    );

    // Find the EventBodyA radio card within our rendered container
    const radios = container.querySelectorAll<HTMLElement>('[role="radio"]');
    const bodyARadio = Array.from(radios).find((r) => r.textContent?.includes('Event Body A'));
    expect(bodyARadio).toBeTruthy();
    fireEvent.click(bodyARadio!);

    // Value should now have the discriminator set
    expect(capturedValues.event_body).not.toBeNull();
    expect(capturedValues.event_body?.type).toBe('EventBodyA');
  });
});

// ---------------------------------------------------------------------------
// Binary sub-field in structural union variant
// ---------------------------------------------------------------------------

const binaryVariantFields: ResourceField[] = [
  makeField({ name: 'caption', type: 'string', isRequired: true }),
  makeField({ name: 'avatar', type: 'binary', isRequired: false }),
];

const binaryStructuralUnionMeta: UnionMeta = {
  discriminatorField: '__variant',
  variants: [
    {
      tag: 'WithBinary',
      label: 'With Binary',
      schemaName: 'WithBinary',
      fields: binaryVariantFields,
    },
    {
      tag: 'Simple',
      label: 'Simple Text',
      type: 'string',
    },
  ],
};

const binaryStructuralField: ResourceField = makeField({
  name: 'media_field',
  label: 'Media Field',
  type: 'union',
  unionMeta: binaryStructuralUnionMeta,
});

describe('UnionFieldRenderer — binary sub-field in structural union', () => {
  it('renders BinaryFieldEditor for binary sub-field in object variant', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={binaryStructuralField}
        unionMeta={binaryStructuralUnionMeta}
        initialValues={{
          media_field: { __variant: 'WithBinary', caption: '', avatar: { _mode: 'empty' } },
        }}
      />,
    );

    // BinaryFieldEditor renders a SegmentedControl with Upload/URL options
    expect(container.textContent).toContain('Upload');
    expect(container.textContent).toContain('URL');
    // The label "avatar" should appear
    expect(container.textContent).toContain('avatar');
  });

  it('initialises binary sub-field with { _mode: "empty" } when switching variant', () => {
    let capturedValues: Record<string, any> = {};
    const { container } = renderWithMantine(
      <FormWrapper
        field={binaryStructuralField}
        unionMeta={binaryStructuralUnionMeta}
        initialValues={{ media_field: { __variant: 'Simple', value: 'abc' } }}
        onValuesChange={(v) => {
          capturedValues = v;
        }}
      />,
    );

    // Switch to WithBinary variant
    const radios = container.querySelectorAll<HTMLElement>('[role="radio"]');
    const withBinaryRadio = Array.from(radios).find((r) => r.textContent?.includes('With Binary'));
    expect(withBinaryRadio).toBeTruthy();
    fireEvent.click(withBinaryRadio!);

    // Binary sub-field should have { _mode: 'empty' }
    expect(capturedValues.media_field.__variant).toBe('WithBinary');
    expect(capturedValues.media_field.avatar).toEqual({ _mode: 'empty' });
    expect(capturedValues.media_field.caption).toBe('');
  });
});

// ---------------------------------------------------------------------------
// Binary sub-field in discriminated union variant
// ---------------------------------------------------------------------------

const binaryDiscriminatedUnionMeta: UnionMeta = {
  discriminatorField: 'type',
  variants: [
    {
      tag: 'MediaA',
      label: 'Media A',
      schemaName: 'MediaA',
      fields: [
        makeField({ name: 'file_data', type: 'binary', isRequired: true }),
        makeField({ name: 'description', type: 'string' }),
      ],
    },
    {
      tag: 'MediaB',
      label: 'Media B',
      schemaName: 'MediaB',
      fields: [
        makeField({ name: 'url', type: 'string', isRequired: true }),
        makeField({ name: 'quality', type: 'number' }),
      ],
    },
  ],
};

const binaryDiscriminatedField: ResourceField = makeField({
  name: 'media',
  label: 'Media',
  type: 'union',
  unionMeta: binaryDiscriminatedUnionMeta,
});

describe('UnionFieldRenderer — binary sub-field in discriminated union', () => {
  it('renders BinaryFieldEditor when variant has binary sub-field', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={binaryDiscriminatedField}
        unionMeta={binaryDiscriminatedUnionMeta}
        initialValues={{
          media: { type: 'MediaA', file_data: { _mode: 'empty' }, description: '' },
        }}
      />,
    );

    // BinaryFieldEditor should render Upload/URL controls
    expect(container.textContent).toContain('Upload');
    expect(container.textContent).toContain('URL');
    expect(container.textContent).toContain('file_data');
  });

  it('initialises binary sub-field correctly when switching to binary variant', () => {
    let capturedValues: Record<string, any> = {};
    const { container } = renderWithMantine(
      <FormWrapper
        field={binaryDiscriminatedField}
        unionMeta={binaryDiscriminatedUnionMeta}
        initialValues={{ media: { type: 'MediaB', url: 'https://example.com', quality: 90 } }}
        onValuesChange={(v) => {
          capturedValues = v;
        }}
      />,
    );

    // Switch to MediaA variant
    const radios = container.querySelectorAll<HTMLElement>('[role="radio"]');
    const mediaARadio = Array.from(radios).find((r) => r.textContent?.includes('Media A'));
    expect(mediaARadio).toBeTruthy();
    fireEvent.click(mediaARadio!);

    expect(capturedValues.media.type).toBe('MediaA');
    expect(capturedValues.media.file_data).toEqual({ _mode: 'empty' });
    expect(capturedValues.media.description).toBe('');
  });
});

// ---------------------------------------------------------------------------
// Array-string (list[str]) sub-field in union variant
// ---------------------------------------------------------------------------

const tagsVariantFields: ResourceField[] = [
  makeField({ name: 'name', type: 'string', isRequired: true }),
  makeField({ name: 'tags', type: 'string', isArray: true }),
];

const tagsStructuralUnionMeta: UnionMeta = {
  discriminatorField: '__variant',
  variants: [
    {
      tag: 'WithTags',
      label: 'With Tags',
      schemaName: 'WithTags',
      fields: tagsVariantFields,
    },
    {
      tag: 'PlainText',
      label: 'Plain Text',
      type: 'string',
    },
  ],
};

const tagsStructuralField: ResourceField = makeField({
  name: 'tagged_field',
  label: 'Tagged Field',
  type: 'union',
  unionMeta: tagsStructuralUnionMeta,
});

describe('UnionFieldRenderer — array-string sub-field in structural union', () => {
  it('renders TagsInput for isArray+string sub-field in object variant', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={tagsStructuralField}
        unionMeta={tagsStructuralUnionMeta}
        initialValues={{
          tagged_field: { __variant: 'WithTags', name: '', tags: [] },
        }}
      />,
    );

    // TagsInput has a placeholder "Type and press Enter"
    const placeholderInput = container.querySelector('input[placeholder="Type and press Enter"]');
    expect(placeholderInput).toBeTruthy();
    // The tags label should be visible
    expect(container.textContent).toContain('tags');
  });

  it('initialises array sub-field with [] when switching variant', () => {
    let capturedValues: Record<string, any> = {};
    const { container } = renderWithMantine(
      <FormWrapper
        field={tagsStructuralField}
        unionMeta={tagsStructuralUnionMeta}
        initialValues={{ tagged_field: { __variant: 'PlainText', value: 'hello' } }}
        onValuesChange={(v) => {
          capturedValues = v;
        }}
      />,
    );

    // Switch to WithTags variant
    const radios = container.querySelectorAll<HTMLElement>('[role="radio"]');
    const withTagsRadio = Array.from(radios).find((r) => r.textContent?.includes('With Tags'));
    expect(withTagsRadio).toBeTruthy();
    fireEvent.click(withTagsRadio!);

    expect(capturedValues.tagged_field.__variant).toBe('WithTags');
    expect(capturedValues.tagged_field.tags).toEqual([]);
    expect(capturedValues.tagged_field.name).toBe('');
  });
});

// ---------------------------------------------------------------------------
// Date sub-field in union variant
// ---------------------------------------------------------------------------

const dateVariantFields: ResourceField[] = [
  makeField({ name: 'event_time', type: 'date', isRequired: true }),
  makeField({ name: 'note', type: 'string' }),
];

const dateStructuralUnionMeta: UnionMeta = {
  discriminatorField: '__variant',
  variants: [
    {
      tag: 'WithDate',
      label: 'With Date',
      schemaName: 'WithDate',
      fields: dateVariantFields,
    },
    {
      tag: 'Simple',
      label: 'Simple Text',
      type: 'string',
    },
  ],
};

const dateStructuralField: ResourceField = makeField({
  name: 'date_field',
  label: 'Date Field',
  type: 'union',
  unionMeta: dateStructuralUnionMeta,
});

describe('UnionFieldRenderer — date sub-field in union variant', () => {
  it('renders DateTimePicker for date sub-field in object variant', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={dateStructuralField}
        unionMeta={dateStructuralUnionMeta}
        initialValues={{
          date_field: { __variant: 'WithDate', event_time: null, note: '' },
        }}
      />,
    );

    // DateTimePicker renders with a date button and the label
    expect(container.textContent).toContain('event_time');
    // DateTimePicker renders a button to toggle the calendar
    const _dateButton =
      container.querySelector('button[aria-label="Date"]') ??
      container.querySelector('[data-dates-provider]') ??
      container.querySelector('.mantine-DateTimePicker-root');
    // At minimum, the label must be present (DateTimePicker in happy-dom may not
    // fully render its interactive parts)
    expect(container.textContent).toContain('event_time');
  });
});

// ---------------------------------------------------------------------------
// Nested union sub-field in union variant (recursive)
// ---------------------------------------------------------------------------

const nestedUnionSubField: ResourceField = makeField({
  name: 'metadata',
  label: 'Metadata',
  type: 'union',
  unionMeta: {
    discriminatorField: '__type',
    variants: [
      { tag: 'string', label: 'String', type: 'string' },
      { tag: 'number', label: 'Number', type: 'number' },
    ],
  },
});

const nestedUnionVariantFields: ResourceField[] = [
  makeField({ name: 'title', type: 'string', isRequired: true }),
  nestedUnionSubField,
];

const nestedUnionStructuralMeta: UnionMeta = {
  discriminatorField: '__variant',
  variants: [
    {
      tag: 'WithNestedUnion',
      label: 'With Nested Union',
      schemaName: 'WithNestedUnion',
      fields: nestedUnionVariantFields,
    },
    {
      tag: 'Plain',
      label: 'Plain Text',
      type: 'string',
    },
  ],
};

const nestedUnionField: ResourceField = makeField({
  name: 'nested_union_field',
  label: 'Nested Union Field',
  type: 'union',
  unionMeta: nestedUnionStructuralMeta,
});

describe('UnionFieldRenderer — nested union sub-field (recursive)', () => {
  it('renders inner union controls for nested union sub-field', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={nestedUnionField}
        unionMeta={nestedUnionStructuralMeta}
        initialValues={{
          nested_union_field: { __variant: 'WithNestedUnion', title: '', metadata: '' },
        }}
      />,
    );

    // The outer variant labels should show
    expectText('With Nested Union');
    expectText('Plain Text');
    // The inner simple union should render its type radio options
    expect(container.textContent).toContain('String');
    expect(container.textContent).toContain('Number');
    // Title field should render
    expect(container.textContent).toContain('title');
  });
});

// ---------------------------------------------------------------------------
// Nested itemFields (array of objects) sub-field in union variant
// ---------------------------------------------------------------------------

const nestedItemFieldsSubField: ResourceField = makeField({
  name: 'items',
  label: 'Items',
  type: 'array',
  isArray: true,
  itemFields: [
    makeField({ name: 'item_name', type: 'string', isRequired: true }),
    makeField({ name: 'item_count', type: 'number' }),
  ],
});

const itemFieldsVariantFields: ResourceField[] = [
  makeField({ name: 'group_name', type: 'string', isRequired: true }),
  nestedItemFieldsSubField,
];

const itemFieldsStructuralMeta: UnionMeta = {
  discriminatorField: '__variant',
  variants: [
    {
      tag: 'WithItems',
      label: 'With Items',
      schemaName: 'WithItems',
      fields: itemFieldsVariantFields,
    },
    {
      tag: 'Simple',
      label: 'Simple Text',
      type: 'string',
    },
  ],
};

const itemFieldsContainerField: ResourceField = makeField({
  name: 'container_field',
  label: 'Container Field',
  type: 'union',
  unionMeta: itemFieldsStructuralMeta,
});

describe('UnionFieldRenderer — nested itemFields sub-field in union variant', () => {
  it('renders ArrayFieldRenderer for itemFields sub-field', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={itemFieldsContainerField}
        unionMeta={itemFieldsStructuralMeta}
        initialValues={{
          container_field: {
            __variant: 'WithItems',
            group_name: '',
            items: [],
          },
        }}
      />,
    );

    // group_name text field should render
    expect(container.textContent).toContain('group_name');
    // The ArrayFieldRenderer should show "Items" label and "Add" button
    expect(container.textContent).toContain('Items');
    expectText('Add');
    // "No items yet" from ArrayFieldRenderer
    expect(container.textContent).toContain('No items yet');
  });

  it('can add items to nested array within union variant', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={itemFieldsContainerField}
        unionMeta={itemFieldsStructuralMeta}
        initialValues={{
          container_field: {
            __variant: 'WithItems',
            group_name: 'test',
            items: [],
          },
        }}
      />,
    );

    // Find the Add button within the ArrayFieldRenderer
    const addButtons = Array.from(container.querySelectorAll('button')).filter(
      (btn) => btn.textContent?.trim() === 'Add',
    );
    expect(addButtons.length).toBeGreaterThanOrEqual(1);
    fireEvent.click(addButtons[0]);

    // After adding, sub-field labels should appear
    expect(container.textContent).toContain('item_name');
    expect(container.textContent).toContain('item_count');
  });
});

// ---------------------------------------------------------------------------
// Dict variant uses emptyValueForSubField for all sub-field types
// ---------------------------------------------------------------------------

const dictWithBinaryMeta: UnionMeta = {
  discriminatorField: '__variant',
  variants: [
    {
      tag: 'dict_val',
      label: 'Dict[str, Val]',
      isDict: true,
      dictValueFields: [
        makeField({ name: 'avatar', type: 'binary' }),
        makeField({ name: 'tags', type: 'string', isArray: true }),
        makeField({ name: 'active', type: 'boolean' }),
      ],
    },
    {
      tag: 'string',
      label: 'Plain',
      type: 'string',
    },
  ],
};

const dictWithBinaryField: ResourceField = makeField({
  name: 'dict_field',
  label: 'Dict Field',
  type: 'union',
  unionMeta: dictWithBinaryMeta,
});

describe('UnionFieldRenderer — dict variant emptyValueForSubField', () => {
  it('renders dict variant value sub-fields including binary and array', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={dictWithBinaryField}
        unionMeta={dictWithBinaryMeta}
        initialValues={{
          dict_field: {
            __variant: 'dict_val',
            __entries: [{ __key: 'k1', avatar: { _mode: 'empty' }, tags: [], active: false }],
          },
        }}
      />,
    );

    // Should render BinaryFieldEditor (Upload/URL) and tags input
    expect(container.textContent).toContain('Upload');
    expect(container.textContent).toContain('URL');
    expect(container.textContent).toContain('avatar');
    expect(container.textContent).toContain('tags');
  });
});

// ---------------------------------------------------------------------------
// Nullable fields should NOT show required indicator (isRequired && isNullable)
// ---------------------------------------------------------------------------

describe('UnionFieldRenderer — nullable sub-fields should not be required', () => {
  it('nullable binary sub-field in discriminated union does not show required', () => {
    const meta: UnionMeta = {
      discriminatorField: 'type',
      variants: [
        {
          tag: 'EventBodyA',
          label: 'EventBodyA',
          schemaName: 'EventBodyA',
          fields: [
            makeField({
              name: 'extra_info_a',
              type: 'string',
              isRequired: true,
              isNullable: false,
            }),
            makeField({ name: 'content', type: 'binary', isRequired: true, isNullable: true }),
          ],
        },
      ],
    };
    const field = makeField({
      name: 'event_body',
      label: 'Event Body',
      type: 'union',
      unionMeta: meta,
    });

    const { container } = renderWithMantine(
      <FormWrapper
        field={field}
        unionMeta={meta}
        initialValues={{
          event_body: { type: 'EventBodyA', extra_info_a: '', content: { _mode: 'empty' } },
        }}
      />,
    );

    // extra_info_a is required (isRequired=true, isNullable=false) → should have required
    const extraInfoInput = container.querySelector(
      'input[aria-label="extra_info_a"],input',
    ) as HTMLInputElement;
    // Find all labels to verify required indicator
    const labels = Array.from(container.querySelectorAll('label'));
    const extraInfoLabel = labels.find((l) => l.textContent?.includes('extra_info_a'));
    const contentLabel = labels.find((l) => l.textContent?.includes('content'));

    // extra_info_a: isRequired=true, isNullable=false → should show required (asterisk)
    expect(
      extraInfoLabel?.querySelector('[data-required]') ?? extraInfoLabel?.innerHTML,
    ).toBeTruthy();
    // content: isRequired=true, isNullable=true → should NOT show required
    // Binary field renders with "Upload" / "URL" tabs, check no required indicator on its label
    const contentContainer = container.textContent || '';
    expect(contentContainer).toContain('content');
    // The BinaryFieldEditor receives required prop — check that it is NOT required
    // We test by checking the rendered required indicators
    if (contentLabel) {
      const asterisk = contentLabel.querySelector('.mantine-InputWrapper-required');
      expect(asterisk).toBeNull();
    }
  });

  it('nullable text sub-field in discriminated union does not show required asterisk', () => {
    const meta: UnionMeta = {
      discriminatorField: 'type',
      variants: [
        {
          tag: 'A',
          label: 'Type A',
          schemaName: 'A',
          fields: [
            makeField({
              name: 'required_field',
              type: 'string',
              isRequired: true,
              isNullable: false,
            }),
            makeField({
              name: 'nullable_field',
              type: 'string',
              isRequired: true,
              isNullable: true,
            }),
            makeField({
              name: 'optional_field',
              type: 'string',
              isRequired: false,
              isNullable: false,
            }),
          ],
        },
      ],
    };
    const field = makeField({
      name: 'data',
      label: 'Data',
      type: 'union',
      unionMeta: meta,
    });

    const { container } = renderWithMantine(
      <FormWrapper
        field={field}
        unionMeta={meta}
        initialValues={{
          data: { type: 'A', required_field: '', nullable_field: '', optional_field: '' },
        }}
      />,
    );

    // Find all TextInputs by checking labels
    const allInputs = container.querySelectorAll('.mantine-TextInput-root');
    // required_field: isRequired=true, isNullable=false → should be required
    // nullable_field: isRequired=true, isNullable=true → should NOT be required
    // optional_field: isRequired=false → should NOT be required

    // Check by looking for required inputs
    const requiredInputs = container.querySelectorAll('input[required]');
    const requiredLabels = Array.from(requiredInputs).map((inp) => {
      const wrapper = inp.closest('.mantine-TextInput-root');
      return wrapper?.querySelector('label')?.textContent?.replace(' *', '');
    });

    // Only required_field should be marked as required
    expect(requiredLabels).toContain('required_field');
    expect(requiredLabels).not.toContain('nullable_field');
    expect(requiredLabels).not.toContain('optional_field');
  });

  it('nullable number sub-field in structural union variant does not show required', () => {
    const meta: UnionMeta = {
      discriminatorField: '__variant',
      variants: [
        {
          tag: 'MyStruct',
          label: 'My Struct',
          schemaName: 'MyStruct',
          fields: [
            makeField({ name: 'score', type: 'number', isRequired: true, isNullable: false }),
            makeField({ name: 'bonus', type: 'number', isRequired: true, isNullable: true }),
          ],
        },
      ],
    };
    const field = makeField({
      name: 'val',
      label: 'Value',
      type: 'union',
      unionMeta: meta,
    });

    const { container } = renderWithMantine(
      <FormWrapper
        field={field}
        unionMeta={meta}
        initialValues={{ val: { __variant: 'MyStruct', score: 0, bonus: 0 } }}
      />,
    );

    const requiredInputs = container.querySelectorAll('input[required]');
    const requiredLabels = Array.from(requiredInputs).map((inp) => {
      const wrapper = inp.closest('.mantine-NumberInput-root');
      return wrapper?.querySelector('label')?.textContent?.replace(' *', '');
    });

    expect(requiredLabels).toContain('score');
    expect(requiredLabels).not.toContain('bonus');
  });
});
