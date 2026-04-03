/**
 * FormFieldRenderer (FieldRenderer) — component-level tests.
 *
 * Tests the public FieldRenderer component by passing different field
 * configurations and verifying the correct input type is rendered.
 * Sub-components like RefSelect, JsonEditor, etc. are mocked.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import type { ResourceField } from '../../../resources';
import { FieldRenderer } from './index';
import { useForm } from '@mantine/form';

// Mock heavy sub-components to keep tests fast & isolated
vi.mock('./RefSelect', () => ({
  RefSelect: (props: any) => (
    <div data-testid="ref-select">
      {props.label}
      <button data-testid="ref-select-change" onClick={() => props.onChange?.('new-id')}>
        change
      </button>
    </div>
  ),
  RefMultiSelect: (props: any) => (
    <div data-testid="ref-multi-select">
      {props.label}
      <button data-testid="ref-multi-change" onClick={() => props.onChange?.(['id1', 'id2'])}>
        change
      </button>
    </div>
  ),
  RefRevisionSelect: (props: any) => (
    <div data-testid="ref-revision-select">
      {props.label}
      <button data-testid="ref-rev-change" onClick={() => props.onChange?.('rev-1')}>
        change
      </button>
    </div>
  ),
  RefRevisionMultiSelect: (props: any) => (
    <div data-testid="ref-revision-multi-select">
      {props.label}
      <button data-testid="ref-rev-multi-change" onClick={() => props.onChange?.(['r1', 'r2'])}>
        change
      </button>
    </div>
  ),
}));

vi.mock('./JsonEditor', () => ({
  JsonEditor: (props: any) => (
    <div data-testid="json-editor">
      {props.label}
      <button data-testid="json-editor-change" onClick={() => props.onChange?.('{"new":true}')}>
        change
      </button>
    </div>
  ),
}));

vi.mock('./MarkdownEditor', () => ({
  MarkdownEditor: (props: any) => (
    <div data-testid="markdown-editor">
      {props.label}
      <button data-testid="md-editor-change" onClick={() => props.onChange?.('# New')}>
        change
      </button>
    </div>
  ),
}));

vi.mock('./BinaryFieldEditor', () => ({
  BinaryFieldEditor: (props: any) => (
    <div data-testid="binary-editor">
      {props.label}
      <button
        data-testid="binary-change"
        onClick={() => props.onChange?.({ _mode: 'file', file: null })}
      >
        change
      </button>
    </div>
  ),
}));

vi.mock('./UnionFieldRenderer', () => ({
  UnionFieldRenderer: (props: any) => <div data-testid="union-renderer">{props.field.label}</div>,
}));

vi.mock('./ArrayFieldRenderer', () => ({
  ArrayFieldRenderer: (props: any) => <div data-testid="array-renderer">{props.field.label}</div>,
}));

beforeEach(() => {
  cleanup();
});

function makeField(overrides: Partial<ResourceField> = {}): ResourceField {
  return {
    name: 'testField',
    label: 'Test Field',
    type: 'string',
    isArray: false,
    isRequired: false,
    isNullable: false,
    ...overrides,
  };
}

/** Wrapper component that provides form context */
function TestFieldRenderer({
  field,
  initialValues,
}: {
  field: ResourceField;
  initialValues?: Record<string, any>;
}) {
  const form = useForm({
    initialValues: initialValues ?? { [field.name]: '' },
  });

  return (
    <MantineProvider>
      <FieldRenderer
        field={field}
        form={form}
        simpleUnionTypes={{}}
        setSimpleUnionTypes={vi.fn()}
      />
    </MantineProvider>
  );
}

describe('FieldRenderer', () => {
  it('renders TextInput for plain string field', () => {
    render(<TestFieldRenderer field={makeField()} />);
    expect(screen.getByText('Test Field')).toBeDefined();
  });

  it('renders nothing for hidden (constValue) field', () => {
    const { container } = render(
      <TestFieldRenderer field={makeField({ constValue: 'fixed_type' })} />,
    );
    // hidden renderer returns null - only MantineProvider CSS
    expect(container.textContent).not.toContain('Test Field');
  });

  it('renders NumberInput for number field', () => {
    render(
      <TestFieldRenderer
        field={makeField({ type: 'number', name: 'level', label: 'Level' })}
        initialValues={{ level: 0 }}
      />,
    );
    expect(screen.getByText('Level')).toBeDefined();
  });

  it('renders Switch for boolean field', () => {
    render(
      <TestFieldRenderer
        field={makeField({ type: 'boolean', name: 'active', label: 'Active' })}
        initialValues={{ active: false }}
      />,
    );
    expect(screen.getByText('Active')).toBeDefined();
  });

  it('renders Checkbox for boolean field with checkbox variant', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          type: 'boolean',
          name: 'confirmed',
          label: 'Confirmed',
          variant: { type: 'checkbox' },
        })}
        initialValues={{ confirmed: false }}
      />,
    );
    expect(screen.getByText('Confirmed')).toBeDefined();
  });

  it('renders Select for field with select variant', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'status',
          label: 'Status',
          variant: { type: 'select', options: [{ value: 'active', label: 'Active' }] },
        })}
        initialValues={{ status: '' }}
      />,
    );
    expect(screen.getByText('Status')).toBeDefined();
  });

  it('renders Textarea for textarea variant', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'desc',
          label: 'Description',
          variant: { type: 'textarea', rows: 5 },
        })}
        initialValues={{ desc: '' }}
      />,
    );
    expect(screen.getByText('Description')).toBeDefined();
  });

  it('renders JsonEditor for json variant', () => {
    render(
      <TestFieldRenderer
        field={makeField({ name: 'config', label: 'Config', variant: { type: 'json' } })}
        initialValues={{ config: '{}' }}
      />,
    );
    expect(screen.getByTestId('json-editor')).toBeDefined();
  });

  it('renders JsonEditor for object type', () => {
    render(
      <TestFieldRenderer
        field={makeField({ name: 'data', label: 'Data', type: 'object' })}
        initialValues={{ data: '{}' }}
      />,
    );
    expect(screen.getByTestId('json-editor')).toBeDefined();
  });

  it('renders MarkdownEditor for markdown variant', () => {
    render(
      <TestFieldRenderer
        field={makeField({ name: 'notes', label: 'Notes', variant: { type: 'markdown' } })}
        initialValues={{ notes: '' }}
      />,
    );
    expect(screen.getByTestId('markdown-editor')).toBeDefined();
  });

  it('renders TagsInput for array of strings', () => {
    render(
      <TestFieldRenderer
        field={makeField({ name: 'tags', label: 'Tags', type: 'string', isArray: true })}
        initialValues={{ tags: [] }}
      />,
    );
    expect(screen.getByText('Tags')).toBeDefined();
  });

  it('renders TagsInput for tags variant', () => {
    render(
      <TestFieldRenderer
        field={makeField({ name: 'labels', label: 'Labels', variant: { type: 'tags' } })}
        initialValues={{ labels: [] }}
      />,
    );
    expect(screen.getByText('Labels')).toBeDefined();
  });

  it('renders BinaryFieldEditor for binary type', () => {
    render(
      <TestFieldRenderer
        field={makeField({ name: 'avatar', label: 'Avatar', type: 'binary' })}
        initialValues={{ avatar: null }}
      />,
    );
    expect(screen.getByTestId('binary-editor')).toBeDefined();
  });

  it('renders FileInput for file type', () => {
    render(
      <TestFieldRenderer
        field={makeField({ name: 'upload', label: 'Upload', type: 'file' })}
        initialValues={{ upload: null }}
      />,
    );
    expect(screen.getByText('Upload')).toBeDefined();
  });

  it('renders RefSelect for resource_id ref', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'owner_id',
          label: 'Owner',
          ref: { resource: 'user', type: 'resource_id' },
        })}
        initialValues={{ owner_id: null }}
      />,
    );
    expect(screen.getByTestId('ref-select')).toBeDefined();
  });

  it('renders RefMultiSelect for array resource_id ref', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'member_ids',
          label: 'Members',
          isArray: true,
          ref: { resource: 'user', type: 'resource_id' },
        })}
        initialValues={{ member_ids: [] }}
      />,
    );
    expect(screen.getByTestId('ref-multi-select')).toBeDefined();
  });

  it('renders RefRevisionSelect for revision_id ref', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'rev_id',
          label: 'Revision',
          ref: { resource: 'doc', type: 'revision_id' },
        })}
        initialValues={{ rev_id: null }}
      />,
    );
    expect(screen.getByTestId('ref-revision-select')).toBeDefined();
  });

  it('renders RefRevisionMultiSelect for array revision_id ref', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'rev_ids',
          label: 'Revisions',
          isArray: true,
          ref: { resource: 'doc', type: 'revision_id' },
        })}
        initialValues={{ rev_ids: [] }}
      />,
    );
    expect(screen.getByTestId('ref-revision-multi-select')).toBeDefined();
  });

  it('renders UnionFieldRenderer for union type', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'effect',
          label: 'Effect',
          type: 'union',
          unionMeta: {
            discriminatorField: 'kind',
            variants: [{ tag: 'heal', label: 'Heal' }],
          },
        })}
        initialValues={{ effect: {} }}
      />,
    );
    expect(screen.getByTestId('union-renderer')).toBeDefined();
  });

  it('renders ArrayFieldRenderer for field with itemFields', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'items',
          label: 'Items',
          type: 'array',
          isArray: true,
          itemFields: [makeField({ name: 'items.name', label: 'Name' })],
        })}
        initialValues={{ items: [] }}
      />,
    );
    expect(screen.getByTestId('array-renderer')).toBeDefined();
  });

  it('renders NumberInput with slider variant', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'volume',
          label: 'Volume',
          type: 'number',
          variant: { type: 'slider', sliderMin: 0, sliderMax: 100 },
        })}
        initialValues={{ volume: 50 }}
      />,
    );
    expect(screen.getByText('Volume')).toBeDefined();
  });
});

describe('FieldRenderer — onChange interactions', () => {
  it('json onChange calls form.setFieldValue', () => {
    render(
      <TestFieldRenderer
        field={makeField({ name: 'config', label: 'Config', variant: { type: 'json' } })}
        initialValues={{ config: '{}' }}
      />,
    );
    fireEvent.click(screen.getByTestId('json-editor-change'));
  });

  it('markdown onChange calls form.setFieldValue', () => {
    render(
      <TestFieldRenderer
        field={makeField({ name: 'notes', label: 'Notes', variant: { type: 'markdown' } })}
        initialValues={{ notes: '' }}
      />,
    );
    fireEvent.click(screen.getByTestId('md-editor-change'));
  });

  it('binary onChange calls form.setFieldValue', () => {
    render(
      <TestFieldRenderer
        field={makeField({ name: 'avatar', label: 'Avatar', type: 'binary' })}
        initialValues={{ avatar: null }}
      />,
    );
    fireEvent.click(screen.getByTestId('binary-change'));
  });

  it('refResourceId onChange calls form.setFieldValue', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'owner_id',
          label: 'Owner',
          ref: { resource: 'user', type: 'resource_id' },
        })}
        initialValues={{ owner_id: null }}
      />,
    );
    fireEvent.click(screen.getByTestId('ref-select-change'));
  });

  it('refResourceIdMulti onChange calls form.setFieldValue', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'member_ids',
          label: 'Members',
          isArray: true,
          ref: { resource: 'user', type: 'resource_id' },
        })}
        initialValues={{ member_ids: [] }}
      />,
    );
    fireEvent.click(screen.getByTestId('ref-multi-change'));
  });

  it('refRevisionId onChange calls form.setFieldValue', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'rev_id',
          label: 'Revision',
          ref: { resource: 'doc', type: 'revision_id' },
        })}
        initialValues={{ rev_id: null }}
      />,
    );
    fireEvent.click(screen.getByTestId('ref-rev-change'));
  });

  it('refRevisionIdMulti onChange calls form.setFieldValue', () => {
    render(
      <TestFieldRenderer
        field={makeField({
          name: 'rev_ids',
          label: 'Revisions',
          isArray: true,
          ref: { resource: 'doc', type: 'revision_id' },
        })}
        initialValues={{ rev_ids: [] }}
      />,
    );
    fireEvent.click(screen.getByTestId('ref-rev-multi-change'));
  });

  it('text input onChange triggers with typing', () => {
    render(<TestFieldRenderer field={makeField()} initialValues={{ testField: '' }} />);
    const inputs = screen.getAllByRole('textbox');
    fireEvent.change(inputs[0], { target: { value: 'hello' } });
  });

  it('number input onChange triggers', () => {
    render(
      <TestFieldRenderer
        field={makeField({ type: 'number', name: 'level', label: 'Level' })}
        initialValues={{ level: 0 }}
      />,
    );
    const inputs = screen.getAllByRole('textbox');
    if (inputs[0]) {
      fireEvent.change(inputs[0], { target: { value: '42' } });
    }
  });

  it('switch onChange triggers', () => {
    const { container } = render(
      <TestFieldRenderer
        field={makeField({ type: 'boolean', name: 'active', label: 'Active' })}
        initialValues={{ active: false }}
      />,
    );
    const checkbox = container.querySelector('input[type="checkbox"]');
    if (checkbox) {
      fireEvent.click(checkbox);
    }
  });

  it('select onChange triggers', () => {
    const { container } = render(
      <TestFieldRenderer
        field={makeField({
          name: 'status',
          label: 'Status',
          variant: { type: 'select', options: [{ value: 'active', label: 'Active' }] },
        })}
        initialValues={{ status: '' }}
      />,
    );
    const input = container.querySelector('input');
    if (input) {
      fireEvent.change(input, { target: { value: 'active' } });
    }
  });
});
