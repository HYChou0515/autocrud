import { useState, useMemo } from 'react';
import { useForm } from '@mantine/form';
import { zodResolver } from 'mantine-form-zod-resolver';
import {
  TextInput,
  NumberInput,
  Textarea,
  Checkbox,
  Select,
  Button,
  Stack,
  Group,
  FileInput,
  Switch,
  SegmentedControl,
  Alert,
  Text,
  Tooltip,
  ActionIcon,
  Paper,
  Radio,
} from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { IconLayersSubtract, IconTrash, IconPlus, IconLink, IconX } from '@tabler/icons-react';
import type { ResourceConfig, ResourceField, FieldVariant, UnionMeta } from '../resources';
import { RefSelect, RefMultiSelect, RefRevisionSelect, RefRevisionMultiSelect } from './RefSelect';
import {
  getByPath,
  setByPath,
  fileToBase64,
  binaryFormValueToApi,
  toLabel,
  inferDefaultVariant,
  computeVisibleFieldsAndGroups,
  computeMaxAvailableDepth,
  processInitialValues,
  formValuesToApiObject as formValuesToApiObjectUtil,
  applyJsonToForm as applyJsonToFormUtil,
  isCollapsedChild as isCollapsedChildUtil,
  validateJsonFields,
  preprocessArrayFields,
  parseAndValidateJson,
  type BinaryFormValue,
} from '@/lib/utils/formUtils';

/** Inline binary field editor — file upload or URL input */
function BinaryFieldEditor({
  label,
  required,
  value,
  onChange,
  apiUrl,
}: {
  label: string;
  required?: boolean;
  value: BinaryFormValue | null;
  onChange: (val: BinaryFormValue) => void;
  apiUrl?: string;
}) {
  const mode = value?._mode ?? 'empty';
  const activeMode = mode === 'existing' || mode === 'empty' ? 'file' : mode;

  const handleModeChange = (m: string) => {
    if (m === 'file') onChange({ _mode: 'file', file: null });
    else onChange({ _mode: 'url', url: '' });
  };

  const handleFileChange = (file: File | null) => {
    onChange({ _mode: 'file', file });
  };

  const handleUrlChange = (url: string) => {
    onChange({ _mode: 'url', url });
  };

  const handleClear = () => {
    onChange({ _mode: 'empty' });
  };

  const blobUrl = value?.file_id && apiUrl ? `${apiUrl}/blobs/${value.file_id}` : null;

  return (
    <Stack gap={4}>
      <Group gap="xs" align="flex-end">
        <Text size="sm" fw={500}>
          {label}
          {required && <span style={{ color: 'var(--mantine-color-red-6)' }}> *</span>}
        </Text>
        {mode === 'existing' && blobUrl && (
          <Text size="xs" c="dimmed">
            (current:{' '}
            <a href={blobUrl} target="_blank" rel="noreferrer">
              {value?.content_type}
            </a>
            {value?.size != null && `, ${(value.size / 1024).toFixed(1)} KB`})
          </Text>
        )}
      </Group>
      <Group gap="xs">
        <SegmentedControl
          size="xs"
          value={activeMode}
          onChange={handleModeChange}
          data={[
            { label: 'Upload', value: 'file' },
            { label: 'URL', value: 'url' },
          ]}
        />
        {mode !== 'empty' && (
          <Tooltip label="Clear">
            <ActionIcon variant="subtle" color="gray" size="sm" onClick={handleClear}>
              <IconX size={14} />
            </ActionIcon>
          </Tooltip>
        )}
      </Group>
      {activeMode === 'file' ? (
        <FileInput
          placeholder="Choose file..."
          value={value?._mode === 'file' ? (value.file ?? null) : null}
          onChange={handleFileChange}
          clearable
        />
      ) : (
        <TextInput
          placeholder="https://example.com/image.png"
          leftSection={<IconLink size={14} />}
          value={value?._mode === 'url' ? (value.url ?? '') : ''}
          onChange={(e) => handleUrlChange(e.currentTarget.value)}
        />
      )}
    </Stack>
  );
}

export interface ResourceFormProps<T> {
  config: ResourceConfig<T>;
  initialValues?: Partial<T>;
  onSubmit: (values: T) => void | Promise<void>;
  onCancel?: () => void;
  submitLabel?: string;
}

/**
 * Generic resource form with auto-generated fields based on config
 * 支援 Zod 驗證和 variant 自定義
 */
export function ResourceForm<T extends Record<string, any>>({
  config,
  initialValues = {},
  onSubmit,
  onCancel,
  submitLabel = 'Submit',
}: ResourceFormProps<T>) {
  const [editMode, setEditMode] = useState<'form' | 'json'>('form');
  const [jsonText, setJsonText] = useState('');
  const [jsonError, setJsonError] = useState<string | null>(null);

  // Compute max available depth from all fields
  const maxAvailableDepth = useMemo(() => {
    return computeMaxAvailableDepth(config.fields);
  }, [config.fields]);

  // Runtime-adjustable form depth (how deep nested objects expand into form fields)
  const [formDepth, setFormDepth] = useState<number>(config.maxFormDepth ?? maxAvailableDepth);

  // Track selected type for simple union fields (discriminatorField === '__type')
  const [simpleUnionTypes, setSimpleUnionTypes] = useState<Record<string, string>>({});

  /**
   * Compute visible fields and collapsed groups based on formDepth.
   * - visibleFields: fields rendered as individual form inputs
   * - collapsedGroups: parent paths at the depth boundary → rendered as JSON editors
   * - collapsedGroupFields: mapping from parent path → its child fields (for reconstruction)
   */
  const {
    visibleFields,
    collapsedGroups,
    collapsedGroupFields: _collapsedGroupFields,
  } = useMemo(() => {
    return computeVisibleFieldsAndGroups(config.fields, formDepth);
  }, [config.fields, formDepth]);

  // Identify date fields to convert between ISO strings and Date objects
  const dateFieldNames = config.fields
    .filter((f) => f.type === 'date' || f.variant?.type === 'date')
    .map((f) => f.name);

  // Convert ISO string values to Date objects for date fields and convert null to defaults
  const processedInitialValues = processInitialValues(
    initialValues as Record<string, any>,
    config.fields,
    collapsedGroups,
    dateFieldNames,
  );

  // Custom validation for JSON object fields + zod schema validation
  const zodValidate = config.zodSchema ? zodResolver(config.zodSchema) : undefined;
  const combinedValidate = (values: T) => {
    // Validate JSON object fields using extracted utility
    const errors = validateJsonFields(
      values as Record<string, any>,
      config.fields,
      collapsedGroups,
    );

    // Merge with zod validation errors
    if (zodValidate) {
      try {
        // Pre-process values for zod: convert comma-separated strings to arrays for isArray fields
        const zodValues = preprocessArrayFields(values as Record<string, any>, config.fields);

        const zodErrors = zodValidate(zodValues as T);
        // Suppress zod errors for object-type fields (stored as JSON strings) and collapsed group paths
        // BUT NOT for fields with itemFields (they use actual arrays, zod can validate them directly)
        const suppressPaths = new Set([
          ...config.fields
            .filter((f) => f.type === 'object' && !(f.itemFields && f.itemFields.length > 0))
            .map((f) => f.name),
          ...config.fields.filter((f) => f.type === 'binary').map((f) => f.name),
          // Simple array fields (comma-separated string in form, z.array() in schema) — exclude array ref fields
          ...config.fields
            .filter(
              (f) =>
                f.isArray &&
                !(f.itemFields && f.itemFields.length > 0) &&
                !(f.ref && f.ref.type === 'resource_id'),
            )
            .map((f) => f.name),
          ...collapsedGroups.map((g: { path: string; label: string }) => g.path),
        ]);
        // Collect nested simple-array sub-field names within array-with-itemFields
        const nestedArraySubFields: { parent: string; sub: string }[] = [];
        for (const f of config.fields) {
          if (f.itemFields && f.itemFields.length > 0) {
            for (const sf of f.itemFields) {
              if (sf.isArray) {
                nestedArraySubFields.push({ parent: f.name, sub: sf.name });
              }
              if (sf.type === 'binary') {
                nestedArraySubFields.push({ parent: f.name, sub: sf.name });
              }
            }
          }
        }
        for (const key of Object.keys(zodErrors)) {
          if (suppressPaths.has(key)) {
            delete zodErrors[key];
          }
          // Also suppress child path errors of collapsed groups
          if (
            collapsedGroups.some((g: { path: string; label: string }) =>
              key.startsWith(g.path + '.'),
            )
          ) {
            delete zodErrors[key];
          }
          // Suppress errors for nested comma-separated array / binary sub-fields (e.g. equipments.0.special_effects)
          if (
            nestedArraySubFields.some(({ parent, sub }) => {
              const regex = new RegExp(`^${parent}\\.\\d+\\.${sub}$`);
              return regex.test(key);
            })
          ) {
            delete zodErrors[key];
          }
        }
        return { ...zodErrors, ...errors };
      } catch {
        // zodResolver may crash with incompatible value types
        return errors;
      }
    }
    return errors;
  };

  const form = useForm<T>({
    initialValues: processedInitialValues as T,
    validate: combinedValidate,
  });

  // Identify object fields to parse JSON strings back to objects
  const _objectFieldNames = config.fields.filter((f) => f.type === 'object').map((f) => f.name);

  /** Convert current form values to a clean API-ready object */
  const formValuesToApiObject = (): Record<string, any> => {
    const values = form.getValues() as Record<string, any>;
    return formValuesToApiObjectUtil(values, config.fields, collapsedGroups, dateFieldNames);
  };

  /** Apply a parsed JSON object back into form values */
  const applyJsonToForm = (obj: Record<string, any>) => {
    const newValues = applyJsonToFormUtil(obj, config.fields, collapsedGroups, dateFieldNames);

    // Apply values to form using setFieldValue
    for (const field of config.fields) {
      if (isCollapsedChildUtil(field.name, collapsedGroups)) continue;
      const val =
        newValues[field.name] !== undefined
          ? newValues[field.name]
          : getByPath(newValues, field.name);
      form.setFieldValue(field.name, val);
    }
    // Apply collapsed group values
    for (const group of collapsedGroups) {
      form.setFieldValue(group.path, newValues[group.path]);
    }
  };

  /** Switch from Form mode to JSON mode */
  const handleSwitchToJson = () => {
    const apiObj = formValuesToApiObject();
    setJsonText(JSON.stringify(apiObj, null, 2));
    setJsonError(null);
    setEditMode('json');
  };

  /** Switch from JSON mode to Form mode */
  const handleSwitchToForm = () => {
    const result = parseAndValidateJson(jsonText);
    if (!result.success) {
      setJsonError(result.error || 'Invalid JSON');
      return;
    }
    applyJsonToForm(result.data);
    setJsonError(null);
    setEditMode('form');
  };

  /** Handle JSON mode submit */
  const handleJsonSubmit = () => {
    const result = parseAndValidateJson(jsonText);
    if (!result.success) {
      setJsonError(result.error || 'Invalid JSON');
      return;
    }
    const parsed = result.data;

    // Use zod schema for full validation (enum, type checks, patterns, etc.)
    if (config.zodSchema) {
      const zodResult = config.zodSchema.safeParse(parsed);
      if (!zodResult.success) {
        const fieldErrors = zodResult.error.issues.map((issue: any) => {
          const path = issue.path.join('.');
          const fieldDef = config.fields.find((f) => f.name === path);
          const label = fieldDef?.label || path || 'Root';
          return `${label}: ${issue.message}`;
        });
        setJsonError(fieldErrors.join('\n'));
        return;
      }
    }
    setJsonError(null);
    return onSubmit(parsed as T);
  };

  // Convert Date objects back to ISO strings on submit
  // and parse JSON strings back to objects for object fields
  // and convert empty strings back to null for nullable fields
  const handleSubmit = async (values: T) => {
    // Extract binary field values BEFORE deep clone (File objects are lost in JSON.parse)
    const binaryFieldValues = new Map<string, BinaryFormValue | null>();
    // Also extract binary values nested inside array items
    const arrayItemBinaryValues = new Map<string, BinaryFormValue | null>(); // key: "fieldName.index.subFieldName"
    for (const field of config.fields) {
      if (field.type === 'binary') {
        const bv = getByPath(values as Record<string, any>, field.name) as BinaryFormValue | null;
        binaryFieldValues.set(field.name, bv);
      }
      if (field.itemFields) {
        const items = (values as Record<string, any>)[field.name];
        if (Array.isArray(items)) {
          for (let i = 0; i < items.length; i++) {
            for (const sf of field.itemFields) {
              if (sf.type === 'binary') {
                const bv = items[i]?.[sf.name] as BinaryFormValue | null;
                arrayItemBinaryValues.set(`${field.name}.${i}.${sf.name}`, bv);
              }
            }
          }
        }
      }
    }

    const processed = JSON.parse(JSON.stringify(values)) as Record<string, any>;

    const isCollapsedChild = (name: string) =>
      collapsedGroups.some((g: { path: string; label: string }) => name.startsWith(g.path + '.'));

    // Clean up field values based on type
    for (const field of config.fields) {
      // Skip collapsed children — their data is in the parent JSON string
      if (isCollapsedChild(field.name)) continue;

      const val = getByPath(processed, field.name);

      // Array of typed objects — process each item's sub-fields
      if (field.itemFields && field.itemFields.length > 0) {
        if (Array.isArray(val)) {
          const _hasBinarySubs = field.itemFields.some((sf) => sf.type === 'binary');
          const cleanItems = await Promise.all(
            val.map(async (item: any, idx: number) => {
              const res: Record<string, any> = {};
              for (const sf of field.itemFields!) {
                let v = item?.[sf.name];
                if (sf.type === 'binary') {
                  // Use pre-extracted binary value (has File object)
                  const bv = arrayItemBinaryValues.get(`${field.name}.${idx}.${sf.name}`);
                  v = await binaryFormValueToApi(bv);
                } else if (sf.isArray && sf.type === 'string') {
                  v =
                    typeof v === 'string'
                      ? v
                          .split(',')
                          .map((s: string) => s.trim())
                          .filter(Boolean)
                      : Array.isArray(v)
                        ? v
                        : [];
                } else if (sf.type === 'number' && (v === '' || v === undefined)) {
                  v = sf.isNullable ? null : undefined;
                } else if (sf.type === 'string' && v === '' && sf.isNullable) {
                  v = null;
                } else if (sf.type === 'object') {
                  if (typeof v === 'string' && v.trim()) {
                    try {
                      v = JSON.parse(v);
                    } catch {
                      /* keep */
                    }
                  } else if (typeof v === 'string' && !v.trim()) {
                    v = null;
                  }
                }
                res[sf.name] = v;
              }
              return res;
            }),
          );
          setByPath(processed, field.name, cleanItems);
        }
        continue;
      }

      if (dateFieldNames.includes(field.name)) {
        if (val instanceof Date || (typeof val === 'string' && val)) {
          const d = val instanceof Date ? val : new Date(val);
          if (!isNaN(d.getTime())) {
            setByPath(processed, field.name, d.toISOString());
          }
        }
      } else if (field.type === 'binary') {
        // Binary fields are processed separately above via binaryFieldValues
        continue;
      } else if (field.type === 'object') {
        if (typeof val === 'string' && val.trim()) {
          try {
            setByPath(processed, field.name, JSON.parse(val));
          } catch {
            // Keep as string if invalid JSON
          }
        } else if (typeof val === 'string' && !val.trim()) {
          setByPath(processed, field.name, null);
        }
      } else if (
        field.isArray &&
        !(field.itemFields && field.itemFields.length > 0) &&
        !(field.ref && field.ref.type === 'resource_id')
      ) {
        // Simple array field (comma-separated string in form) — convert to array before zod
        // Skip array ref fields — they are already arrays from RefMultiSelect
        if (typeof val === 'string') {
          setByPath(
            processed,
            field.name,
            val
              ? val
                  .split(',')
                  .map((s: string) => s.trim())
                  .filter(Boolean)
              : [],
          );
        }
      } else if (field.type === 'number') {
        // Convert empty string back to null for nullable number fields
        if (val === '' || val === undefined) {
          setByPath(processed, field.name, field.isNullable ? null : undefined);
        }
      } else if (field.type === 'string') {
        // Convert empty string to null for nullable string fields
        if (val === '' && field.isNullable) {
          setByPath(processed, field.name, null);
        }
      }
    }

    // Parse collapsed group JSON strings back to objects
    for (const group of collapsedGroups) {
      const val = getByPath(processed, group.path);
      if (typeof val === 'string' && val.trim()) {
        try {
          setByPath(processed, group.path, JSON.parse(val));
        } catch {
          /* keep */
        }
      } else if (typeof val === 'string' && !val.trim()) {
        setByPath(processed, group.path, null);
      }
    }

    // Process binary fields: convert File/URL to base64 API payload
    for (const [fieldName, bv] of binaryFieldValues) {
      const apiVal = await binaryFormValueToApi(bv);
      setByPath(processed, fieldName, apiVal);
    }

    // Validate processed values against zod schema before submitting
    if (config.zodSchema) {
      const result = config.zodSchema.safeParse(processed);
      if (!result.success) {
        // Map zod errors back to form field errors
        for (const issue of result.error.issues) {
          const path = issue.path.join('.');
          form.setFieldError(path, issue.message);
        }
        return;
      }
    }

    return onSubmit(processed as T);
  };

  /**
   * Render a union field as Radio Cards (discriminated) or Radio Group (simple).
   * - Discriminated unions: Radio.Card per variant → sub-fields for selected variant
   * - Simple unions: Radio buttons for type → matching input control
   */
  const renderUnionField = (
    field: ResourceField,
    unionMeta: UnionMeta,
    key: string,
    fieldLabel: string,
    isRequired: boolean,
  ) => {
    const { name } = field;
    const isDiscriminated = unionMeta.discriminatorField !== '__type';
    const currentValue = (form.getValues() as Record<string, any>)[name];

    if (isDiscriminated) {
      // ── Discriminated union: Radio.Card for each variant ──
      const discField = unionMeta.discriminatorField;
      const selectedTag = currentValue?.[discField] ?? '';
      const selectedVariant = unionMeta.variants.find((v) => v.tag === selectedTag);

      const handleVariantChange = (tag: string) => {
        const variant = unionMeta.variants.find((v) => v.tag === tag);
        if (!variant) return;
        // Build a new value object: discriminator + empty sub-fields
        const newValue: Record<string, any> = { [discField]: tag };
        if (variant.fields) {
          for (const sf of variant.fields) {
            if (sf.type === 'number') newValue[sf.name] = '';
            else if (sf.type === 'boolean') newValue[sf.name] = false;
            else if (sf.type === 'object') newValue[sf.name] = '';
            else newValue[sf.name] = '';
          }
        }
        form.setFieldValue(name as any, newValue as any);
      };

      return (
        <Stack key={key} gap="xs">
          <Radio.Group
            label={fieldLabel}
            required={isRequired}
            value={selectedTag}
            onChange={(val) => handleVariantChange(val)}
          >
            <Stack gap="xs" mt="xs">
              {unionMeta.variants.map((v) => (
                <Radio.Card key={v.tag} value={v.tag} radius="md" withBorder p="md">
                  <Group wrap="nowrap" align="flex-start">
                    <Radio.Indicator />
                    <div>
                      <Text fw={500} size="sm">
                        {v.label}
                      </Text>
                      {v.schemaName && (
                        <Text size="xs" c="dimmed">
                          {v.schemaName}
                        </Text>
                      )}
                    </div>
                  </Group>
                </Radio.Card>
              ))}
            </Stack>
          </Radio.Group>

          {/* Render sub-fields of the selected variant */}
          {selectedVariant?.fields && selectedVariant.fields.length > 0 && (
            <Paper withBorder p="sm" radius="sm">
              <Stack gap="xs">
                {selectedVariant.fields.map((sf) => {
                  const subPath = `${name}.${sf.name}`;

                  // Enum → Select
                  if (sf.enumValues && sf.enumValues.length > 0) {
                    return (
                      <Select
                        key={subPath}
                        label={sf.label}
                        required={sf.isRequired}
                        data={sf.enumValues.map((v) => ({ value: v, label: v }))}
                        clearable={sf.isNullable}
                        {...form.getInputProps(subPath)}
                      />
                    );
                  }
                  // Boolean → Switch
                  if (sf.type === 'boolean') {
                    return (
                      <Switch
                        key={subPath}
                        label={sf.label}
                        {...form.getInputProps(subPath, { type: 'checkbox' })}
                      />
                    );
                  }
                  // Number
                  if (sf.type === 'number') {
                    return (
                      <NumberInput
                        key={subPath}
                        label={sf.label}
                        required={sf.isRequired}
                        {...form.getInputProps(subPath)}
                      />
                    );
                  }
                  // Object → JSON textarea
                  if (sf.type === 'object') {
                    return (
                      <Textarea
                        key={subPath}
                        label={sf.label}
                        required={sf.isRequired}
                        placeholder="{}"
                        minRows={2}
                        styles={{ input: { fontFamily: 'monospace', fontSize: '13px' } }}
                        {...form.getInputProps(subPath)}
                      />
                    );
                  }
                  // Default: text
                  return (
                    <TextInput
                      key={subPath}
                      label={sf.label}
                      required={sf.isRequired}
                      {...form.getInputProps(subPath)}
                    />
                  );
                })}
              </Stack>
            </Paper>
          )}
        </Stack>
      );
    }

    // ── Simple union (discriminatorField === '__type') ──
    // Use plain Radio buttons for type selection
    const inferType = (): string => {
      if (currentValue === null || currentValue === undefined || currentValue === '') {
        return simpleUnionTypes[name] || unionMeta.variants[0]?.tag || '';
      }
      if (typeof currentValue === 'number') return 'number';
      if (typeof currentValue === 'boolean') return 'boolean';
      return 'string';
    };
    const selectedType = inferType();

    const handleTypeChange = (tag: string) => {
      setSimpleUnionTypes((prev) => ({ ...prev, [name]: tag }));
      const variant = unionMeta.variants.find((v) => v.tag === tag);
      if (!variant) return;
      // Reset value to type-appropriate default
      if (variant.type === 'number' || variant.type === 'integer') {
        form.setFieldValue(name as any, '' as any);
      } else if (variant.type === 'boolean') {
        form.setFieldValue(name as any, false as any);
      } else {
        form.setFieldValue(name as any, '' as any);
      }
    };

    const renderSimpleInput = () => {
      const variant = unionMeta.variants.find((v) => v.tag === selectedType);
      if (!variant) return null;

      if (variant.type === 'boolean') {
        return (
          <Switch
            label={`${fieldLabel} value`}
            {...form.getInputProps(name, { type: 'checkbox' })}
          />
        );
      }
      if (variant.type === 'number' || variant.type === 'integer') {
        return (
          <NumberInput
            label={`${fieldLabel} value`}
            required={isRequired}
            {...form.getInputProps(name)}
          />
        );
      }
      // string or other
      return (
        <TextInput
          label={`${fieldLabel} value`}
          required={isRequired}
          {...form.getInputProps(name)}
        />
      );
    };

    return (
      <Stack key={key} gap="xs">
        <Radio.Group
          label={fieldLabel}
          required={isRequired}
          value={selectedType}
          onChange={(val) => handleTypeChange(val)}
        >
          <Group mt="xs">
            {unionMeta.variants.map((v) => (
              <Radio key={v.tag} value={v.tag} label={v.label} />
            ))}
          </Group>
        </Radio.Group>
        {renderSimpleInput()}
      </Stack>
    );
  };

  const renderField = (field: ResourceField) => {
    const { name, label, type, isRequired, isArray, variant } = field;
    const key = name;

    // Array of typed objects — render as repeatable list with sub-fields
    if (field.itemFields && field.itemFields.length > 0) {
      const items = (form.getValues() as Record<string, any>)[name] || [];
      const createEmptyItem = () => {
        const item: Record<string, any> = {};
        for (const sf of field.itemFields!) {
          if (sf.type === 'binary') item[sf.name] = { _mode: 'empty' } as BinaryFormValue;
          else if (sf.enumValues && sf.enumValues.length > 0)
            item[sf.name] = sf.isNullable ? null : (sf.enumValues[0] ?? '');
          else if (sf.type === 'number') item[sf.name] = '';
          else if (sf.type === 'boolean') item[sf.name] = false;
          else if (sf.type === 'object') item[sf.name] = '';
          else item[sf.name] = '';
        }
        return item;
      };

      return (
        <Stack key={key} gap="xs">
          <Group justify="space-between" align="center">
            <Text fw={500} size="sm">
              {label}
            </Text>
            <Button
              size="compact-xs"
              variant="light"
              leftSection={<IconPlus size={14} />}
              onClick={() => form.insertListItem(name, createEmptyItem())}
            >
              Add
            </Button>
          </Group>
          {items.length === 0 && (
            <Text size="sm" c="dimmed" fs="italic">
              No items yet
            </Text>
          )}
          {items.map((_: any, index: number) => (
            <Paper key={index} withBorder p="sm" radius="sm">
              <Group justify="space-between" mb="xs">
                <Text size="xs" c="dimmed" fw={500}>
                  #{index + 1}
                </Text>
                <ActionIcon
                  size="sm"
                  color="red"
                  variant="subtle"
                  onClick={() => form.removeListItem(name, index)}
                >
                  <IconTrash size={14} />
                </ActionIcon>
              </Group>
              <Stack gap="xs">
                {field.itemFields!.map((sf) => {
                  const itemPath = `${name}.${index}.${sf.name}`;
                  const _subVariant = sf.variant || inferDefaultVariant(sf);

                  // Enum → Select
                  if (sf.enumValues && sf.enumValues.length > 0) {
                    return (
                      <Select
                        key={itemPath}
                        label={sf.label}
                        required={sf.isRequired}
                        data={sf.enumValues.map((v) => ({ value: v, label: v }))}
                        clearable={sf.isNullable}
                        {...form.getInputProps(itemPath)}
                      />
                    );
                  }
                  // Object → JSON textarea
                  if (sf.type === 'object') {
                    return (
                      <Textarea
                        key={itemPath}
                        label={sf.label}
                        required={sf.isRequired}
                        placeholder="{}"
                        minRows={2}
                        styles={{ input: { fontFamily: 'monospace', fontSize: '13px' } }}
                        {...form.getInputProps(itemPath)}
                      />
                    );
                  }
                  // Binary → upload/URL editor
                  if (sf.type === 'binary') {
                    const itemApiUrl =
                      (typeof window !== 'undefined' && (import.meta as any).env?.VITE_API_URL) ||
                      '';
                    const itemBv = getByPath(
                      form.getValues() as Record<string, any>,
                      itemPath,
                    ) as BinaryFormValue | null;
                    return (
                      <BinaryFieldEditor
                        key={itemPath}
                        label={sf.label}
                        required={sf.isRequired}
                        value={itemBv}
                        onChange={(val) => form.setFieldValue(itemPath as any, val as any)}
                        apiUrl={itemApiUrl}
                      />
                    );
                  }
                  // Boolean
                  if (sf.type === 'boolean') {
                    return (
                      <Switch
                        key={itemPath}
                        label={sf.label}
                        {...form.getInputProps(itemPath, { type: 'checkbox' })}
                      />
                    );
                  }
                  // Number
                  if (sf.type === 'number') {
                    return (
                      <NumberInput
                        key={itemPath}
                        label={sf.label}
                        required={sf.isRequired}
                        {...form.getInputProps(itemPath)}
                      />
                    );
                  }
                  // Array string (comma-separated)
                  if (sf.isArray && sf.type === 'string') {
                    return (
                      <TextInput
                        key={itemPath}
                        label={`${sf.label} (comma-separated)`}
                        required={sf.isRequired}
                        placeholder="value1, value2, value3"
                        {...form.getInputProps(itemPath)}
                      />
                    );
                  }
                  // Default: text input
                  return (
                    <TextInput
                      key={itemPath}
                      label={sf.label}
                      required={sf.isRequired}
                      {...form.getInputProps(itemPath)}
                    />
                  );
                })}
              </Stack>
            </Paper>
          ))}
        </Stack>
      );
    }

    // 根據 variant 渲染不同的輸入組件
    // 如果沒有指定 variant，使用預設的 inputType
    const effectiveVariant = variant || inferDefaultVariant(field);

    // Union fields — Radio Card (default) or Radio Group
    if (type === 'union' && field.unionMeta) {
      return renderUnionField(field, field.unionMeta, key, label, isRequired);
    }

    // Binary/File fields — upload or URL
    if (type === 'binary') {
      const apiUrl =
        (typeof window !== 'undefined' && (import.meta as any).env?.VITE_API_URL) || '';
      const binaryVal = form.getValues()[name as keyof T] as unknown as BinaryFormValue | null;
      return (
        <BinaryFieldEditor
          key={key}
          label={label}
          required={isRequired}
          value={binaryVal}
          onChange={(val) => form.setFieldValue(name as any, val as any)}
          apiUrl={apiUrl}
        />
      );
    }

    // JSON fields
    if (effectiveVariant.type === 'json' || type === 'object') {
      const jsonVariant = effectiveVariant as Extract<FieldVariant, { type: 'json' }>;
      return (
        <Textarea
          key={key}
          label={label}
          required={isRequired}
          placeholder="JSON object"
          minRows={3}
          maxRows={jsonVariant.height ? jsonVariant.height / 24 : undefined}
          {...form.getInputProps(name)}
        />
      );
    }

    // Markdown editor
    if (effectiveVariant.type === 'markdown') {
      const markdownVariant = effectiveVariant as Extract<FieldVariant, { type: 'markdown' }>;
      return (
        <Textarea
          key={key}
          label={label}
          required={isRequired}
          placeholder="Markdown content"
          minRows={markdownVariant.height ? markdownVariant.height / 24 : 5}
          {...form.getInputProps(name)}
        />
      );
    }

    // Array text input (comma-separated) — skip array ref fields (handled by RefMultiSelect below)
    if (isArray && type === 'string' && !(field.ref && field.ref.type === 'resource_id')) {
      return (
        <TextInput
          key={key}
          label={`${label} (comma-separated)`}
          required={isRequired}
          placeholder="value1, value2, value3"
          {...form.getInputProps(name)}
        />
      );
    }

    // Tags input (similar to array but with better UI)
    if (effectiveVariant.type === 'tags') {
      // 暫時使用 TextInput，未來可以添加專門的 TagsInput 組件
      return (
        <TextInput
          key={key}
          label={label}
          required={isRequired}
          placeholder="tag1, tag2, tag3"
          {...form.getInputProps(name)}
        />
      );
    }

    // Select with options
    if (effectiveVariant.type === 'select') {
      const selectVariant = effectiveVariant as Extract<FieldVariant, { type: 'select' }>;
      const inputProps = form.getInputProps(name);
      return (
        <Select
          key={key}
          label={label}
          required={isRequired}
          data={selectVariant.options || []}
          clearable={field.isNullable}
          {...inputProps}
          onChange={(val) => {
            // When cleared, Mantine gives null — set it directly to avoid
            // Zod validation seeing an empty string for nullable enums.
            form.setFieldValue(name as any, (val ?? null) as any);
          }}
        />
      );
    }

    // Boolean - Checkbox
    if (type === 'boolean' && effectiveVariant.type === 'checkbox') {
      return (
        <Checkbox key={key} label={label} {...form.getInputProps(name, { type: 'checkbox' })} />
      );
    }

    // Boolean - Switch (default for boolean)
    if (type === 'boolean') {
      return <Switch key={key} label={label} {...form.getInputProps(name, { type: 'checkbox' })} />;
    }

    // Date/time input
    if (type === 'date' || effectiveVariant.type === 'date') {
      return (
        <DateTimePicker
          key={key}
          label={label}
          required={isRequired}
          valueFormat="YYYY-MM-DD HH:mm:ss"
          clearable
          {...form.getInputProps(name)}
        />
      );
    }

    // Number - Slider
    if (type === 'number' && effectiveVariant.type === 'slider') {
      // 暫時使用 NumberInput，未來可以添加 Slider 組件
      const sliderVariant = effectiveVariant as Extract<FieldVariant, { type: 'slider' }>;
      return (
        <NumberInput
          key={key}
          label={label}
          required={isRequired}
          min={sliderVariant.sliderMin}
          max={sliderVariant.sliderMax}
          step={sliderVariant.step}
          {...form.getInputProps(name)}
        />
      );
    }

    // Number input
    if (type === 'number') {
      const numberVariant = effectiveVariant as Extract<FieldVariant, { type: 'number' }>;
      return (
        <NumberInput
          key={key}
          label={label}
          required={isRequired}
          min={numberVariant.min}
          max={numberVariant.max}
          step={numberVariant.step}
          {...form.getInputProps(name)}
        />
      );
    }

    // Textarea for long text
    if (effectiveVariant.type === 'textarea') {
      const textareaVariant = effectiveVariant as Extract<FieldVariant, { type: 'textarea' }>;
      return (
        <Textarea
          key={key}
          label={label}
          required={isRequired}
          rows={textareaVariant.rows || 3}
          {...form.getInputProps(name)}
        />
      );
    }

    // Ref field — render as searchable select for the referenced resource
    if (field.ref && field.ref.type === 'resource_id') {
      // Array ref (N:N) — multi-select
      if (field.isArray) {
        return (
          <RefMultiSelect
            key={key}
            label={label}
            required={isRequired}
            fieldRef={field.ref}
            value={(form.getValues()[name as keyof T] as string[] | undefined) ?? []}
            onChange={(val) => form.setFieldValue(name as any, val as any)}
            error={form.errors[name as string] as string | undefined}
          />
        );
      }
      // Scalar ref (1:N / 1:1) — single select
      return (
        <RefSelect
          key={key}
          label={label}
          required={isRequired}
          fieldRef={field.ref}
          value={form.getValues()[name as keyof T] as string | null}
          onChange={(val) => form.setFieldValue(name as any, val as any)}
          error={form.errors[name as string] as string | undefined}
          clearable={field.isNullable}
        />
      );
    }

    // RefRevision field — render as searchable select for revision IDs
    if (field.ref && field.ref.type === 'revision_id') {
      // Array ref revision — multi-select
      if (field.isArray) {
        return (
          <RefRevisionMultiSelect
            key={key}
            label={label}
            required={isRequired}
            fieldRef={field.ref}
            value={(form.getValues()[name as keyof T] as string[] | undefined) ?? []}
            onChange={(val) => form.setFieldValue(name as any, val as any)}
            error={form.errors[name as string] as string | undefined}
          />
        );
      }
      // Scalar ref revision — single select
      return (
        <RefRevisionSelect
          key={key}
          label={label}
          required={isRequired}
          fieldRef={field.ref}
          value={form.getValues()[name as keyof T] as string | null}
          onChange={(val) => form.setFieldValue(name as any, val as any)}
          error={form.errors[name as string] as string | undefined}
          clearable={field.isNullable}
        />
      );
    }

    // Default: text input
    return (
      <TextInput key={key} label={label} required={isRequired} {...form.getInputProps(name)} />
    );
  };

  /** Render a collapsed group as a JSON textarea */
  const renderCollapsedGroup = (group: { path: string; label: string }) => {
    return (
      <Textarea
        key={`collapsed-${group.path}`}
        label={`${group.label} (JSON)`}
        placeholder="{}"
        minRows={4}
        autosize
        styles={{ input: { fontFamily: 'monospace', fontSize: '13px' } }}
        {...form.getInputProps(group.path)}
      />
    );
  };

  return (
    <Stack gap="md">
      {/* Mode switcher + depth control */}
      <Group justify="space-between" align="center">
        <SegmentedControl
          size="xs"
          value={editMode}
          onChange={(value) => {
            if (value === 'json') handleSwitchToJson();
            else handleSwitchToForm();
          }}
          data={[
            { label: 'Form', value: 'form' },
            { label: 'JSON', value: 'json' },
          ]}
        />
        {editMode === 'form' && maxAvailableDepth > 1 && (
          <Tooltip
            label="Form field expansion depth: lower values collapse nested objects into JSON editors"
            withArrow
          >
            <Group gap={4}>
              <IconLayersSubtract size={16} />
              <Text size="xs" c="dimmed">
                Depth
              </Text>
              <NumberInput
                size="xs"
                value={formDepth}
                onChange={(val) => setFormDepth(typeof val === 'number' ? val : 1)}
                min={1}
                max={maxAvailableDepth}
                step={1}
                w={60}
                styles={{ input: { textAlign: 'center' } }}
              />
            </Group>
          </Tooltip>
        )}
      </Group>

      {/* Form mode */}
      {editMode === 'form' && (
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="md">
            {visibleFields.map(renderField)}
            {collapsedGroups.map(renderCollapsedGroup)}
            <Group justify="flex-end" mt="md">
              {onCancel && (
                <Button variant="subtle" onClick={onCancel}>
                  Cancel
                </Button>
              )}
              <Button type="submit">{submitLabel}</Button>
            </Group>
          </Stack>
        </form>
      )}

      {/* JSON mode */}
      {editMode === 'json' && (
        <Stack gap="md">
          {jsonError && (
            <Alert color="red" variant="light">
              {jsonError}
            </Alert>
          )}
          <Textarea
            placeholder='{"field": "value"}'
            value={jsonText}
            onChange={(e) => {
              setJsonText(e.currentTarget.value);
              setJsonError(null);
            }}
            minRows={10}
            autosize
            styles={{ input: { fontFamily: 'monospace', fontSize: '13px' } }}
          />
          <Group justify="flex-end" mt="md">
            {onCancel && (
              <Button variant="subtle" onClick={onCancel}>
                Cancel
              </Button>
            )}
            <Button onClick={handleJsonSubmit}>{submitLabel}</Button>
          </Group>
        </Stack>
      )}
    </Stack>
  );
}
