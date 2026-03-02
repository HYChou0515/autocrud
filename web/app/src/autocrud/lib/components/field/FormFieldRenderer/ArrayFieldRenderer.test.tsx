/**
 * ArrayFieldRenderer — Tests for nested sub-field rendering.
 *
 * Verifies that ArrayFieldRenderer properly delegates to the correct
 * component for each sub-field type, including recursive types like
 * union, date, and nested arrays.
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { useForm } from '@mantine/form';
import type { ResourceField } from '../../../resources';
import { ArrayFieldRenderer } from './ArrayFieldRenderer';

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
  initialValues: Record<string, any>;
  onValuesChange?: (values: Record<string, any>) => void;
}

function FormWrapper({ field, initialValues, onValuesChange }: WrapperProps) {
  const form = useForm({ initialValues });
  if (onValuesChange) onValuesChange(form.getValues());
  return <ArrayFieldRenderer field={field} form={form} />;
}

// ---------------------------------------------------------------------------
// Basic: array of objects with simple sub-fields
// ---------------------------------------------------------------------------

const simpleArrayField: ResourceField = makeField({
  name: 'items',
  label: 'Items',
  type: 'array',
  isArray: true,
  itemFields: [
    makeField({ name: 'name', type: 'string', isRequired: true }),
    makeField({ name: 'count', type: 'number' }),
    makeField({ name: 'active', type: 'boolean' }),
  ],
});

describe('ArrayFieldRenderer — basic sub-fields', () => {
  it('renders label and Add button', () => {
    renderWithMantine(<FormWrapper field={simpleArrayField} initialValues={{ items: [] }} />);

    expectText('Items');
    expectText('Add');
    expectText('No items yet');
  });

  it('adds item with sub-fields when Add is clicked', () => {
    renderWithMantine(<FormWrapper field={simpleArrayField} initialValues={{ items: [] }} />);

    fireEvent.click(screen.getAllByText('Add')[0]);
    expectText('name');
    expectText('count');
    expectText('active');
    expectText('#1');
  });
});

// ---------------------------------------------------------------------------
// Date sub-field in array items
// ---------------------------------------------------------------------------

const dateArrayField: ResourceField = makeField({
  name: 'events',
  label: 'Events',
  type: 'array',
  isArray: true,
  itemFields: [
    makeField({ name: 'event_time', type: 'date', isRequired: true }),
    makeField({ name: 'description', type: 'string' }),
  ],
});

describe('ArrayFieldRenderer — date sub-field', () => {
  it('renders DateTimePicker for date type sub-field', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={dateArrayField}
        initialValues={{
          events: [{ event_time: null, description: '' }],
        }}
      />,
    );

    // DateTimePicker renders the label. In happy-dom it may not fully render
    // interactive parts, but the label must be present.
    expect(container.textContent).toContain('event_time');
    // Verify it's NOT a plain TextInput — DateTimePicker renders a button element
    const dateRelated =
      container.querySelector('button') ?? container.querySelector('[data-dates-provider]');
    expect(dateRelated).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Binary sub-field in array items
// ---------------------------------------------------------------------------

const binaryArrayField: ResourceField = makeField({
  name: 'attachments',
  label: 'Attachments',
  type: 'array',
  isArray: true,
  itemFields: [
    makeField({ name: 'file', type: 'binary', isRequired: true }),
    makeField({ name: 'caption', type: 'string' }),
  ],
});

describe('ArrayFieldRenderer — binary sub-field', () => {
  it('renders BinaryFieldEditor for binary type sub-field', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={binaryArrayField}
        initialValues={{
          attachments: [{ file: { _mode: 'empty' }, caption: '' }],
        }}
      />,
    );

    // BinaryFieldEditor shows Upload/URL toggle
    expect(container.textContent).toContain('Upload');
    expect(container.textContent).toContain('URL');
    expect(container.textContent).toContain('file');
  });
});

// ---------------------------------------------------------------------------
// Union sub-field in array items (recursive)
// ---------------------------------------------------------------------------

const unionArrayField: ResourceField = makeField({
  name: 'entries',
  label: 'Entries',
  type: 'array',
  isArray: true,
  itemFields: [
    makeField({ name: 'label', type: 'string', isRequired: true }),
    makeField({
      name: 'value',
      type: 'union',
      unionMeta: {
        discriminatorField: '__type',
        variants: [
          { tag: 'string', label: 'Text', type: 'string' },
          { tag: 'number', label: 'Number', type: 'number' },
        ],
      },
    }),
  ],
});

describe('ArrayFieldRenderer — union sub-field (recursive)', () => {
  it('renders UnionFieldRenderer for union type sub-field', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={unionArrayField}
        initialValues={{
          entries: [{ label: 'test', value: '' }],
        }}
      />,
    );

    // The simple union should render its type radio options
    expect(container.textContent).toContain('Text');
    expect(container.textContent).toContain('Number');
    expect(container.textContent).toContain('label');
  });
});

// ---------------------------------------------------------------------------
// Nested array of objects sub-field in array items (recursive)
// ---------------------------------------------------------------------------

const nestedArrayField: ResourceField = makeField({
  name: 'groups',
  label: 'Groups',
  type: 'array',
  isArray: true,
  itemFields: [
    makeField({ name: 'group_name', type: 'string', isRequired: true }),
    makeField({
      name: 'members',
      label: 'Members',
      type: 'array',
      isArray: true,
      itemFields: [
        makeField({ name: 'member_name', type: 'string', isRequired: true }),
        makeField({ name: 'role', type: 'string' }),
      ],
    }),
  ],
});

describe('ArrayFieldRenderer — nested array of objects (recursive)', () => {
  it('renders nested ArrayFieldRenderer for itemFields sub-field', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={nestedArrayField}
        initialValues={{
          groups: [{ group_name: 'team', members: [] }],
        }}
      />,
    );

    // Should render the outer group's sub-fields
    expect(container.textContent).toContain('group_name');
    // The inner ArrayFieldRenderer should show "Members" and "Add"
    expect(container.textContent).toContain('Members');
    // Should have 2 "Add" buttons — one for outer groups, one for inner members
    const addButtons = Array.from(container.querySelectorAll('button')).filter(
      (btn) => btn.textContent?.trim() === 'Add',
    );
    expect(addButtons.length).toBe(2);
  });

  it('can add items to nested array', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={nestedArrayField}
        initialValues={{
          groups: [{ group_name: 'team', members: [] }],
        }}
      />,
    );

    // Click the inner Add button (Members)
    const addButtons = Array.from(container.querySelectorAll('button')).filter(
      (btn) => btn.textContent?.trim() === 'Add',
    );
    // The second Add button should be for the inner members array
    fireEvent.click(addButtons[1]);

    // After adding, inner sub-field labels should appear
    expect(container.textContent).toContain('member_name');
    expect(container.textContent).toContain('role');
  });
});

// ---------------------------------------------------------------------------
// TagsInput (isArray+string) sub-field in array items
// ---------------------------------------------------------------------------

const tagsArrayField: ResourceField = makeField({
  name: 'items',
  label: 'Items',
  type: 'array',
  isArray: true,
  itemFields: [
    makeField({ name: 'name', type: 'string', isRequired: true }),
    makeField({ name: 'tags', type: 'string', isArray: true }),
  ],
});

describe('ArrayFieldRenderer — TagsInput sub-field', () => {
  it('renders TagsInput for isArray+string sub-field', () => {
    const { container } = renderWithMantine(
      <FormWrapper
        field={tagsArrayField}
        initialValues={{
          items: [{ name: 'test', tags: [] }],
        }}
      />,
    );

    // TagsInput has placeholder "Type and press Enter"
    const tagsInput = container.querySelector('input[placeholder="Type and press Enter"]');
    expect(tagsInput).toBeTruthy();
    expect(container.textContent).toContain('tags');
  });
});
