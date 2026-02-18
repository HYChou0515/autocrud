/**
 * FieldRenderer — Renders a single field based on its resolved FieldKind.
 *
 * 1. `resolveFieldKind()` determines the kind (pure, testable).
 * 2. `FIELD_RENDERERS` map dispatches to the appropriate render function.
 */

import { TextInput, NumberInput, Textarea, Checkbox, Select, Switch } from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import type { UseFormReturnType } from '@mantine/form';
import type { ResourceField, FieldVariant } from '../../resources';
import { RefSelect, RefMultiSelect, RefRevisionSelect, RefRevisionMultiSelect } from '../RefSelect';
import { MarkdownEditor } from '../MarkdownEditor';
import { BinaryFieldEditor } from './BinaryFieldEditor';
import { UnionFieldRenderer } from './UnionFieldRenderer';
import { ArrayFieldRenderer } from './ArrayFieldRenderer';
import { resolveFieldKind, type FieldKind } from './resolveFieldKind';
import { getDefaultVariant, type BinaryFormValue } from '@/lib/utils/formUtils';

// ---------------------------------------------------------------------------
// Shared context passed to every renderer function
// ---------------------------------------------------------------------------

export interface FieldRenderContext {
  field: ResourceField;
  form: UseFormReturnType<any>;
  effectiveVariant: FieldVariant;
  simpleUnionTypes: Record<string, string>;
  setSimpleUnionTypes: React.Dispatch<React.SetStateAction<Record<string, string>>>;
}

// ---------------------------------------------------------------------------
// Renderer map — one entry per FieldKind
// ---------------------------------------------------------------------------

const FIELD_RENDERERS: Record<FieldKind, (ctx: FieldRenderContext) => React.ReactElement> = {
  /* ---- Complex / delegate ---- */

  itemFields: ({ field, form }) => <ArrayFieldRenderer field={field} form={form} />,

  union: ({ field, form, simpleUnionTypes, setSimpleUnionTypes }) => (
    <UnionFieldRenderer
      field={field}
      unionMeta={field.unionMeta!}
      form={form}
      simpleUnionTypes={simpleUnionTypes}
      setSimpleUnionTypes={setSimpleUnionTypes}
    />
  ),

  binary: ({ field, form }) => {
    const apiUrl = (typeof window !== 'undefined' && (import.meta as any).env?.VITE_API_URL) || '';
    const binaryVal = form.getValues()[field.name as string] as unknown as BinaryFormValue | null;
    return (
      <BinaryFieldEditor
        key={field.name}
        label={field.label}
        required={field.isRequired}
        value={binaryVal}
        onChange={(val) => form.setFieldValue(field.name as any, val as any)}
        apiUrl={apiUrl}
      />
    );
  },

  /* ---- Text-like ---- */

  json: ({ field, form, effectiveVariant }) => {
    const v = effectiveVariant as Extract<FieldVariant, { type: 'json' }>;
    return (
      <Textarea
        key={field.name}
        label={field.label}
        required={field.isRequired}
        placeholder="JSON object"
        minRows={3}
        maxRows={v.height ? v.height / 24 : undefined}
        {...form.getInputProps(field.name)}
      />
    );
  },

  markdown: ({ field, form, effectiveVariant }) => {
    const v = effectiveVariant as Extract<FieldVariant, { type: 'markdown' }>;
    const inputProps = form.getInputProps(field.name);
    return (
      <MarkdownEditor
        key={field.name}
        label={field.label}
        required={field.isRequired}
        value={inputProps.value ?? ''}
        onChange={(val) => form.setFieldValue(field.name as any, val as any)}
        height={v.height ?? 300}
        error={inputProps.error as string | undefined}
      />
    );
  },

  arrayString: ({ field, form }) => (
    <TextInput
      key={field.name}
      label={`${field.label} (comma-separated)`}
      required={field.isRequired}
      placeholder="value1, value2, value3"
      {...form.getInputProps(field.name)}
    />
  ),

  tags: ({ field, form }) => (
    <TextInput
      key={field.name}
      label={field.label}
      required={field.isRequired}
      placeholder="tag1, tag2, tag3"
      {...form.getInputProps(field.name)}
    />
  ),

  textarea: ({ field, form, effectiveVariant }) => {
    const v = effectiveVariant as Extract<FieldVariant, { type: 'textarea' }>;
    return (
      <Textarea
        key={field.name}
        label={field.label}
        required={field.isRequired}
        rows={v.rows || 3}
        {...form.getInputProps(field.name)}
      />
    );
  },

  /* ---- Select / enum ---- */

  select: ({ field, form, effectiveVariant }) => {
    const v = effectiveVariant as Extract<FieldVariant, { type: 'select' }>;
    const inputProps = form.getInputProps(field.name);
    return (
      <Select
        key={field.name}
        label={field.label}
        required={field.isRequired}
        data={v.options || []}
        clearable={field.isNullable}
        {...inputProps}
        onChange={(val) => form.setFieldValue(field.name as any, (val ?? null) as any)}
      />
    );
  },

  /* ---- Boolean ---- */

  checkbox: ({ field, form }) => (
    <Checkbox
      key={field.name}
      label={field.label}
      {...form.getInputProps(field.name, { type: 'checkbox' })}
    />
  ),

  switch: ({ field, form }) => (
    <Switch
      key={field.name}
      label={field.label}
      {...form.getInputProps(field.name, { type: 'checkbox' })}
    />
  ),

  /* ---- Date ---- */

  date: ({ field, form }) => (
    <DateTimePicker
      key={field.name}
      label={field.label}
      required={field.isRequired}
      valueFormat="YYYY-MM-DD HH:mm:ss"
      clearable
      {...form.getInputProps(field.name)}
    />
  ),

  /* ---- Number ---- */

  numberSlider: ({ field, form, effectiveVariant }) => {
    const v = effectiveVariant as Extract<FieldVariant, { type: 'slider' }>;
    return (
      <NumberInput
        key={field.name}
        label={field.label}
        required={field.isRequired}
        min={v.sliderMin}
        max={v.sliderMax}
        step={v.step}
        {...form.getInputProps(field.name)}
      />
    );
  },

  number: ({ field, form, effectiveVariant }) => {
    const v = effectiveVariant as Extract<FieldVariant, { type: 'number' }>;
    return (
      <NumberInput
        key={field.name}
        label={field.label}
        required={field.isRequired}
        min={v.min}
        max={v.max}
        step={v.step}
        {...form.getInputProps(field.name)}
      />
    );
  },

  /* ---- Ref ---- */

  refResourceId: ({ field, form }) => (
    <RefSelect
      key={field.name}
      label={field.label}
      required={field.isRequired}
      fieldRef={field.ref!}
      value={form.getValues()[field.name as string] as string | null}
      onChange={(val) => form.setFieldValue(field.name as any, val as any)}
      error={form.errors[field.name as string] as string | undefined}
      clearable={field.isNullable}
    />
  ),

  refResourceIdMulti: ({ field, form }) => (
    <RefMultiSelect
      key={field.name}
      label={field.label}
      required={field.isRequired}
      fieldRef={field.ref!}
      value={(form.getValues()[field.name as string] as string[] | undefined) ?? []}
      onChange={(val) => form.setFieldValue(field.name as any, val as any)}
      error={form.errors[field.name as string] as string | undefined}
    />
  ),

  refRevisionId: ({ field, form }) => (
    <RefRevisionSelect
      key={field.name}
      label={field.label}
      required={field.isRequired}
      fieldRef={field.ref!}
      value={form.getValues()[field.name as string] as string | null}
      onChange={(val) => form.setFieldValue(field.name as any, val as any)}
      error={form.errors[field.name as string] as string | undefined}
      clearable={field.isNullable}
    />
  ),

  refRevisionIdMulti: ({ field, form }) => (
    <RefRevisionMultiSelect
      key={field.name}
      label={field.label}
      required={field.isRequired}
      fieldRef={field.ref!}
      value={(form.getValues()[field.name as string] as string[] | undefined) ?? []}
      onChange={(val) => form.setFieldValue(field.name as any, val as any)}
      error={form.errors[field.name as string] as string | undefined}
    />
  ),

  /* ---- Default ---- */

  text: ({ field, form }) => (
    <TextInput
      key={field.name}
      label={field.label}
      required={field.isRequired}
      {...form.getInputProps(field.name)}
    />
  ),
};

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

interface FieldRendererProps {
  field: ResourceField;
  form: UseFormReturnType<any>;
  simpleUnionTypes: Record<string, string>;
  setSimpleUnionTypes: React.Dispatch<React.SetStateAction<Record<string, string>>>;
}

export function FieldRenderer({
  field,
  form,
  simpleUnionTypes,
  setSimpleUnionTypes,
}: FieldRendererProps) {
  const kind = resolveFieldKind(field);
  const effectiveVariant = field.variant || getDefaultVariant(field);

  return FIELD_RENDERERS[kind]({
    field,
    form,
    effectiveVariant,
    simpleUnionTypes,
    setSimpleUnionTypes,
  });
}
