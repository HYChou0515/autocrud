import { useState, useMemo } from 'react';
import { useForm } from '@mantine/form';
import { zodResolver } from 'mantine-form-zod-resolver';
import { TextInput, NumberInput, Textarea, Checkbox, Select, Button, Stack, Group, FileInput, Switch, SegmentedControl, Alert, Text, Tooltip, ActionIcon, Paper } from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { IconForms, IconCode, IconArrowRight, IconLayersSubtract, IconTrash, IconPlus, IconLink, IconX } from '@tabler/icons-react';
import type { ResourceConfig, ResourceField, FieldVariant } from '../resources';
import { RefSelect, RefMultiSelect } from './RefSelect';

/** Get a value from an object using dot-notation path */
function getByPath(obj: Record<string, any>, path: string): any {
  return path.split('.').reduce((o, k) => o?.[k], obj);
}

/** Convert a File to base64 string (without data: prefix) */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      // Strip "data:...;base64," prefix
      const base64 = dataUrl.split(',')[1] || '';
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/** Internal binary field value tracked in form state */
interface BinaryFormValue {
  _mode: 'file' | 'url' | 'existing' | 'empty';
  file?: File | null;
  url?: string;
  // Existing binary info (for display only)
  file_id?: string;
  content_type?: string;
  size?: number;
}

/** Convert a BinaryFormValue to API-ready binary payload */
async function binaryFormValueToApi(val: BinaryFormValue | null | undefined): Promise<Record<string, any> | null> {
  if (!val || val._mode === 'empty') return null;
  if (val._mode === 'existing') {
    // Don't re-send existing binary — return object with file_id so backend keeps it
    return { file_id: val.file_id };
  }
  if (val._mode === 'file' && val.file) {
    const base64 = await fileToBase64(val.file);
    return {
      data: base64,
      content_type: val.file.type || 'application/octet-stream',
    };
  }
  if (val._mode === 'url' && val.url) {
    try {
      const resp = await fetch(val.url);
      const blob = await resp.blob();
      const base64 = await fileToBase64(new File([blob], 'download', { type: blob.type }));
      return {
        data: base64,
        content_type: blob.type || 'application/octet-stream',
      };
    } catch {
      return null;
    }
  }
  return null;
}

/** Inline binary field editor — file upload or URL input */
function BinaryFieldEditor({ label, required, value, onChange, apiUrl }: {
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

  const blobUrl = value?.file_id && apiUrl
    ? `${apiUrl}/blobs/${value.file_id}`
    : null;

  return (
    <Stack gap={4}>
      <Group gap="xs" align="flex-end">
        <Text size="sm" fw={500}>
          {label}{required && <span style={{ color: 'var(--mantine-color-red-6)' }}> *</span>}
        </Text>
        {mode === 'existing' && blobUrl && (
          <Text size="xs" c="dimmed">
            (current: <a href={blobUrl} target="_blank" rel="noreferrer">{value?.content_type}</a>
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
        {(mode !== 'empty') && (
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

/** Set a value in an object using dot-notation path */
function setByPath(obj: Record<string, any>, path: string, value: any): void {
  const keys = path.split('.');
  let current = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    if (current[keys[i]] == null || typeof current[keys[i]] !== 'object') {
      current[keys[i]] = {};
    }
    current = current[keys[i]];
  }
  current[keys[keys.length - 1]] = value;
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
  submitLabel = 'Submit'
}: ResourceFormProps<T>) {
  const [editMode, setEditMode] = useState<'form' | 'json'>('form');
  const [jsonText, setJsonText] = useState('');
  const [jsonError, setJsonError] = useState<string | null>(null);

  // Compute max available depth from all fields
  const maxAvailableDepth = useMemo(() => {
    let max = 1;
    for (const f of config.fields) {
      const d = f.name.split('.').length;
      if (d > max) max = d;
      // Fields with itemFields (array of typed objects) represent an extra depth level
      if (f.itemFields && f.itemFields.length > 0 && d + 1 > max) max = d + 1;
    }
    return max;
  }, [config.fields]);

  // Runtime-adjustable form depth (how deep nested objects expand into form fields)
  const [formDepth, setFormDepth] = useState<number>(
    config.maxFormDepth ?? maxAvailableDepth
  );

  /**
   * Compute visible fields and collapsed groups based on formDepth.
   * - visibleFields: fields rendered as individual form inputs
   * - collapsedGroups: parent paths at the depth boundary → rendered as JSON editors
   * - collapsedGroupFields: mapping from parent path → its child fields (for reconstruction)
   */
  const { visibleFields, collapsedGroups, collapsedGroupFields } = useMemo(() => {
    const visible: ResourceField[] = [];
    const groupedChildren = new Map<string, ResourceField[]>();

    for (const field of config.fields) {
      const depth = field.name.split('.').length;
      if (depth <= formDepth) {
        // If field has itemFields but depth isn't enough to expand them, strip itemFields
        if (field.itemFields && field.itemFields.length > 0 && depth + 1 > formDepth) {
          visible.push({ ...field, itemFields: undefined });
        } else {
          visible.push(field);
        }
      } else {
        // Find the ancestor path at the formDepth boundary
        const parts = field.name.split('.');
        const ancestorPath = parts.slice(0, formDepth).join('.');
        if (!groupedChildren.has(ancestorPath)) {
          groupedChildren.set(ancestorPath, []);
        }
        groupedChildren.get(ancestorPath)!.push(field);
      }
    }

    // Build collapsed group info: parent paths that have collapsed children
    const groups: { path: string; label: string }[] = [];
    for (const parentPath of groupedChildren.keys()) {
      // Don't add a collapsed group if this path already exists as a visible field
      // (e.g. field.type === 'object' already renders as JSON)
      const alreadyVisible = visible.some(f => f.name === parentPath);
      if (!alreadyVisible) {
        const labelParts = parentPath.split('.');
        const label = toLabel(labelParts[labelParts.length - 1]);
        groups.push({ path: parentPath, label });
      }
    }

    return {
      visibleFields: visible,
      collapsedGroups: groups,
      collapsedGroupFields: groupedChildren,
    };
  }, [config.fields, formDepth]);

  // Identify date fields to convert between ISO strings and Date objects
  const dateFieldNames = config.fields
    .filter(f => f.type === 'date' || f.variant?.type === 'date')
    .map(f => f.name);

  // Convert ISO string values to Date objects for date fields
  // and convert null values to appropriate defaults to avoid React warnings
  // Supports dot-notation paths (e.g. "payload.extra_data") for nested fields
  const processedInitialValues = { ...initialValues } as Record<string, any>;
  // Deep clone nested objects so mutations don't affect original data
  for (const key of Object.keys(processedInitialValues)) {
    if (processedInitialValues[key] && typeof processedInitialValues[key] === 'object' && !Array.isArray(processedInitialValues[key]) && !(processedInitialValues[key] instanceof Date)) {
      processedInitialValues[key] = JSON.parse(JSON.stringify(processedInitialValues[key]));
    }
  }
  for (const field of config.fields) {
    const val = getByPath(processedInitialValues, field.name);

    // Array of typed objects (has itemFields) — keep as actual array for list form
    if (field.itemFields && field.itemFields.length > 0) {
      if (Array.isArray(val)) {
        // Process each item's sub-fields for proper form defaults
        const processedItems = val.map((item: any) => {
          const processed = { ...item };
          for (const sf of field.itemFields!) {
            if (sf.type === 'binary') {
              // Convert existing binary data to BinaryFormValue
              const sv = processed[sf.name];
              if (sv && typeof sv === 'object' && sv.file_id) {
                processed[sf.name] = { _mode: 'existing', file_id: sv.file_id, content_type: sv.content_type, size: sv.size } as BinaryFormValue;
              } else {
                processed[sf.name] = { _mode: 'empty' } as BinaryFormValue;
              }
            } else if (sf.isArray && sf.type === 'string' && Array.isArray(processed[sf.name])) {
              // Convert array to comma-separated string for form display
              processed[sf.name] = processed[sf.name].join(', ');
            } else if (processed[sf.name] === null || processed[sf.name] === undefined) {
              if (sf.enumValues && sf.enumValues.length > 0) processed[sf.name] = null;
              else if (sf.type === 'string' || sf.type === undefined) processed[sf.name] = '';
              else if (sf.type === 'number') processed[sf.name] = '';
              else if (sf.type === 'boolean') processed[sf.name] = false;
              else if (sf.type === 'object') processed[sf.name] = '';
            } else if (sf.type === 'object' && typeof processed[sf.name] === 'object') {
              processed[sf.name] = JSON.stringify(processed[sf.name], null, 2);
            }
          }
          return processed;
        });
        setByPath(processedInitialValues, field.name, processedItems);
      } else {
        setByPath(processedInitialValues, field.name, []);
      }
      continue;
    }

    if (dateFieldNames.includes(field.name)) {
      if (typeof val === 'string' && val) {
        setByPath(processedInitialValues, field.name, new Date(val));
      } else if (val == null) {
        setByPath(processedInitialValues, field.name, null);
      }
    } else if (field.isArray && field.ref && field.ref.type === 'resource_id') {
      // Array ref field — keep as array for MultiSelect, default to []
      setByPath(processedInitialValues, field.name, Array.isArray(val) ? val : []);
    } else if (field.type === 'binary') {
      // Convert existing binary data to BinaryFormValue for editing
      if (val && typeof val === 'object' && val.file_id) {
        setByPath(processedInitialValues, field.name, {
          _mode: 'existing',
          file_id: val.file_id,
          content_type: val.content_type,
          size: val.size,
        } as BinaryFormValue);
      } else {
        setByPath(processedInitialValues, field.name, { _mode: 'empty' } as BinaryFormValue);
      }
    } else if (val === null || val === undefined) {
      // Convert null/undefined to empty string for text-like inputs to avoid React warning
      if (field.type === 'string' || field.type === undefined) {
        setByPath(processedInitialValues, field.name, '');
      } else if (field.type === 'number') {
        setByPath(processedInitialValues, field.name, '');
      } else if (field.type === 'boolean') {
        setByPath(processedInitialValues, field.name, false);
      } else if (field.type === 'object') {
        setByPath(processedInitialValues, field.name, '');
      }
    } else if (field.type === 'object' && typeof val === 'object') {
      // Serialize object values to JSON string for textarea display
      setByPath(processedInitialValues, field.name, JSON.stringify(val, null, 2));
    }
  }

  // For collapsed groups (fields beyond formDepth), reconstruct the parent object as JSON string
  for (const group of collapsedGroups) {
    const parentVal = getByPath(processedInitialValues, group.path);
    if (parentVal && typeof parentVal === 'object' && !(parentVal instanceof Date)) {
      setByPath(processedInitialValues, group.path, JSON.stringify(parentVal, null, 2));
    } else if (parentVal == null || parentVal === undefined) {
      setByPath(processedInitialValues, group.path, '{}');
    }
    // If it's already a string (e.g. from a visible 'object' field), keep it
  }

  // Custom validation for JSON object fields + zod schema validation
  const zodValidate = config.zodSchema ? zodResolver(config.zodSchema) : undefined;
  const combinedValidate = (values: T) => {
    // Validate JSON object fields (skip array fields with itemFields — they use actual arrays)
    const errors: Record<string, string> = {};
    for (const field of config.fields) {
      if (field.type === 'object' && !(field.itemFields && field.itemFields.length > 0)) {
        const val = getByPath(values as Record<string, any>, field.name);
        if (typeof val === 'string' && val.trim()) {
          try {
            const parsed = JSON.parse(val);
            if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
              errors[field.name] = 'Must be a JSON object (not array or primitive)';
            }
          } catch {
            errors[field.name] = 'Invalid JSON format';
          }
        }
      }
    }
    // Also validate collapsed group JSON fields
    for (const group of collapsedGroups) {
      const val = getByPath(values as Record<string, any>, group.path);
      if (typeof val === 'string' && val.trim()) {
        try {
          const parsed = JSON.parse(val);
          if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
            errors[group.path] = 'Must be a JSON object (not array or primitive)';
          }
        } catch {
          errors[group.path] = 'Invalid JSON format';
        }
      }
    }
    // Merge with zod validation errors
    if (zodValidate) {
      try {
        // Pre-process values for zod: convert comma-separated strings to arrays for isArray fields
        // Skip array ref fields — they are already arrays from RefMultiSelect
        const zodValues = { ...(values as Record<string, any>) };
        for (const field of config.fields) {
          if (field.isArray && !(field.itemFields && field.itemFields.length > 0) && !(field.ref && field.ref.type === 'resource_id')) {
            const val = zodValues[field.name];
            if (typeof val === 'string') {
              zodValues[field.name] = val ? val.split(',').map((s: string) => s.trim()).filter(Boolean) : [];
            }
          }
          // Also pre-process nested simple-array sub-fields inside array-with-itemFields
          if (field.itemFields && field.itemFields.length > 0 && Array.isArray(zodValues[field.name])) {
            zodValues[field.name] = zodValues[field.name].map((item: any) => {
              if (!item || typeof item !== 'object') return item;
              const processed = { ...item };
              for (const sf of field.itemFields!) {
                if (sf.isArray && typeof processed[sf.name] === 'string') {
                  processed[sf.name] = processed[sf.name] ? processed[sf.name].split(',').map((s: string) => s.trim()).filter(Boolean) : [];
                }
              }
              return processed;
            });
          }
        }
        const zodErrors = zodValidate(zodValues as T);
        // Suppress zod errors for object-type fields (stored as JSON strings) and collapsed group paths
        // BUT NOT for fields with itemFields (they use actual arrays, zod can validate them directly)
        const suppressPaths = new Set([
          ...config.fields.filter(f => f.type === 'object' && !(f.itemFields && f.itemFields.length > 0)).map(f => f.name),
          ...config.fields.filter(f => f.type === 'binary').map(f => f.name),
          // Simple array fields (comma-separated string in form, z.array() in schema) — exclude array ref fields
          ...config.fields.filter(f => f.isArray && !(f.itemFields && f.itemFields.length > 0) && !(f.ref && f.ref.type === 'resource_id')).map(f => f.name),
          ...collapsedGroups.map(g => g.path),
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
          if (collapsedGroups.some(g => key.startsWith(g.path + '.'))) {
            delete zodErrors[key];
          }
          // Suppress errors for nested comma-separated array / binary sub-fields (e.g. equipments.0.special_effects)
          if (nestedArraySubFields.some(({ parent, sub }) => {
            const regex = new RegExp(`^${parent}\\.\\d+\\.${sub}$`);
            return regex.test(key);
          })) {
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
  const objectFieldNames = config.fields
    .filter(f => f.type === 'object')
    .map(f => f.name);

  /** Convert current form values to a clean API-ready object */
  const formValuesToApiObject = (): Record<string, any> => {
    const values = form.getValues() as Record<string, any>;
    const result: Record<string, any> = {};

    // Track which field paths are managed by collapsed groups
    const collapsedPaths = new Set(collapsedGroups.map(g => g.path));
    const isCollapsedChild = (name: string) =>
      collapsedGroups.some(g => name.startsWith(g.path + '.'));

    for (const field of config.fields) {
      // Skip fields whose data is managed by a collapsed group JSON editor
      if (isCollapsedChild(field.name)) continue;

      const val = getByPath(values, field.name);

      // Array of typed objects — process each item's sub-fields
      if (field.itemFields && field.itemFields.length > 0) {
        const items = Array.isArray(val) ? val : [];
        const processedItems = items.map((item: any) => {
          const res: Record<string, any> = {};
          for (const sf of field.itemFields!) {
            let v = item?.[sf.name];
            if (sf.type === 'binary') {
              // Binary in array items — show info only (sync can't convert)
              const bv = v as BinaryFormValue | null;
              if (bv && bv._mode === 'existing' && bv.file_id) {
                v = { file_id: bv.file_id, content_type: bv.content_type, size: bv.size };
              } else if (bv && bv._mode === 'file' && bv.file) {
                v = { _pending_file: bv.file.name, content_type: bv.file.type };
              } else if (bv && bv._mode === 'url' && bv.url) {
                v = { _pending_url: bv.url };
              } else { v = null; }
            } else if (sf.isArray && sf.type === 'string') {
              // Convert comma-separated string to array
              v = typeof v === 'string' ? v.split(',').map((s: string) => s.trim()).filter(Boolean) : (Array.isArray(v) ? v : []);
            } else if (sf.enumValues && sf.enumValues.length > 0 && (v === '' || v === null || v === undefined)) {
              // Nullable enum: empty/null → null; required enum: keep as-is
              v = sf.isNullable ? null : undefined;
            } else if (sf.type === 'number' && (v === '' || v === undefined)) {
              v = sf.isNullable ? null : undefined;
            } else if (sf.type === 'string' && v === '' && sf.isNullable) {
              v = null;
            } else if (sf.type === 'object') {
              if (typeof v === 'string' && v.trim()) {
                try { v = JSON.parse(v); } catch { /* keep */ }
              } else { v = null; }
            }
            res[sf.name] = v;
          }
          return res;
        });
        setByPath(result, field.name, processedItems);
        continue;
      }

      let cleanVal: any = val;
      if (dateFieldNames.includes(field.name)) {
        if (val instanceof Date) {
          cleanVal = val.toISOString();
        } else if (typeof val === 'string' && val) {
          const d = new Date(val);
          cleanVal = !isNaN(d.getTime()) ? d.toISOString() : val;
        } else {
          cleanVal = null;
        }
      } else if (field.type === 'binary') {
        // For JSON mode display, show existing binary info or null
        const bv = val as BinaryFormValue | null;
        if (bv && bv._mode === 'existing' && bv.file_id) {
          cleanVal = { file_id: bv.file_id, content_type: bv.content_type, size: bv.size };
        } else if (bv && bv._mode === 'file' && bv.file) {
          cleanVal = { _pending_file: bv.file.name, content_type: bv.file.type };
        } else if (bv && bv._mode === 'url' && bv.url) {
          cleanVal = { _pending_url: bv.url };
        } else {
          cleanVal = null;
        }
      } else if (field.type === 'object') {
        if (typeof val === 'string' && val.trim()) {
          try { cleanVal = JSON.parse(val); } catch { cleanVal = val; }
        } else {
          cleanVal = null;
        }
      } else if (field.type === 'number') {
        if (val === '' || val === undefined) {
          cleanVal = field.isNullable ? null : undefined;
        }
      } else if (field.type === 'string') {
        if (val === '' && field.isNullable) {
          cleanVal = null;
        }
      }

      setByPath(result, field.name, cleanVal);
    }

    // Parse collapsed group JSON strings back to objects
    for (const group of collapsedGroups) {
      const val = getByPath(values, group.path);
      if (typeof val === 'string' && val.trim()) {
        try { setByPath(result, group.path, JSON.parse(val)); } catch { /* keep as-is */ }
      } else {
        setByPath(result, group.path, null);
      }
    }

    return result;
  };

  /** Apply a parsed JSON object back into form values */
  const applyJsonToForm = (obj: Record<string, any>) => {
    const newValues: Record<string, any> = {};
    const isCollapsedChild = (name: string) =>
      collapsedGroups.some(g => name.startsWith(g.path + '.'));

    for (const field of config.fields) {
      // Skip fields managed by collapsed groups
      if (isCollapsedChild(field.name)) continue;

      const val = getByPath(obj, field.name);

      // Array of typed objects — process items for form
      if (field.itemFields && field.itemFields.length > 0) {
        if (Array.isArray(val)) {
          newValues[field.name] = val.map((item: any) => {
            const processed: Record<string, any> = {};
            for (const sf of field.itemFields!) {
              const v = item?.[sf.name];
              if (sf.type === 'binary') {
                if (v && typeof v === 'object' && v.file_id) {
                  processed[sf.name] = { _mode: 'existing', file_id: v.file_id, content_type: v.content_type, size: v.size };
                } else {
                  processed[sf.name] = { _mode: 'empty' };
                }
              } else if (sf.isArray && sf.type === 'string') {
                // Convert array back to comma-separated string for form display
                processed[sf.name] = Array.isArray(v) ? v.join(', ') : (v ?? '');
              } else if (sf.type === 'object' && v != null && typeof v === 'object') {
                processed[sf.name] = JSON.stringify(v, null, 2);
              } else if (sf.type === 'number') {
                processed[sf.name] = v ?? '';
              } else if (sf.type === 'boolean') {
                processed[sf.name] = v ?? false;
              } else {
                processed[sf.name] = v ?? '';
              }
            }
            return processed;
          });
        } else {
          newValues[field.name] = [];
        }
        continue;
      }

      if (dateFieldNames.includes(field.name)) {
        if (typeof val === 'string' && val) {
          const d = new Date(val);
          newValues[field.name] = !isNaN(d.getTime()) ? d : null;
        } else {
          newValues[field.name] = null;
        }
      } else if (field.type === 'binary') {
        // Convert JSON binary data back to BinaryFormValue
        if (val && typeof val === 'object' && val.file_id) {
          newValues[field.name] = { _mode: 'existing', file_id: val.file_id, content_type: val.content_type, size: val.size };
        } else {
          newValues[field.name] = { _mode: 'empty' };
        }
      } else if (field.type === 'object') {
        if (val != null && typeof val === 'object') {
          newValues[field.name] = JSON.stringify(val, null, 2);
        } else {
          newValues[field.name] = '';
        }
      } else if (field.type === 'number') {
        newValues[field.name] = val ?? '';
      } else if (field.type === 'boolean') {
        newValues[field.name] = val ?? false;
      } else {
        newValues[field.name] = val ?? '';
      }
    }

    // Apply collapsed group values as JSON strings
    for (const group of collapsedGroups) {
      const val = getByPath(obj, group.path);
      if (val != null && typeof val === 'object') {
        newValues[group.path] = JSON.stringify(val, null, 2);
      } else {
        newValues[group.path] = '{}';
      }
    }

    // For dot-path fields, we need to set them via form.setFieldValue
    for (const field of config.fields) {
      if (isCollapsedChild(field.name)) continue;
      const val = newValues[field.name] !== undefined ? newValues[field.name] : getByPath(newValues, field.name);
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
    try {
      const parsed = JSON.parse(jsonText);
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setJsonError('Must be a JSON object');
        return;
      }
      applyJsonToForm(parsed);
      setJsonError(null);
      setEditMode('form');
    } catch {
      setJsonError('Invalid JSON — fix errors before switching to Form mode');
    }
  };

  /** Handle JSON mode submit */
  const handleJsonSubmit = () => {
    let parsed: any;
    try {
      parsed = JSON.parse(jsonText);
    } catch {
      setJsonError('Invalid JSON format');
      return;
    }
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      setJsonError('Must be a JSON object');
      return;
    }
    // Use zod schema for full validation (enum, type checks, patterns, etc.)
    if (config.zodSchema) {
      const result = config.zodSchema.safeParse(parsed);
      if (!result.success) {
        const fieldErrors = result.error.issues.map((issue: any) => {
          const path = issue.path.join('.');
          const fieldDef = config.fields.find(f => f.name === path);
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
      collapsedGroups.some(g => name.startsWith(g.path + '.'));

    // Clean up field values based on type
    for (const field of config.fields) {
      // Skip collapsed children — their data is in the parent JSON string
      if (isCollapsedChild(field.name)) continue;

      const val = getByPath(processed, field.name);

      // Array of typed objects — process each item's sub-fields
      if (field.itemFields && field.itemFields.length > 0) {
        if (Array.isArray(val)) {
          const hasBinarySubs = field.itemFields.some(sf => sf.type === 'binary');
          const cleanItems = await Promise.all(val.map(async (item: any, idx: number) => {
            const res: Record<string, any> = {};
            for (const sf of field.itemFields!) {
              let v = item?.[sf.name];
              if (sf.type === 'binary') {
                // Use pre-extracted binary value (has File object)
                const bv = arrayItemBinaryValues.get(`${field.name}.${idx}.${sf.name}`);
                v = await binaryFormValueToApi(bv);
              } else if (sf.isArray && sf.type === 'string') {
                v = typeof v === 'string' ? v.split(',').map((s: string) => s.trim()).filter(Boolean) : (Array.isArray(v) ? v : []);
              } else if (sf.type === 'number' && (v === '' || v === undefined)) {
                v = sf.isNullable ? null : undefined;
              } else if (sf.type === 'string' && v === '' && sf.isNullable) {
                v = null;
              } else if (sf.type === 'object') {
                if (typeof v === 'string' && v.trim()) {
                  try { v = JSON.parse(v); } catch { /* keep */ }
                } else if (typeof v === 'string' && !v.trim()) { v = null; }
              }
              res[sf.name] = v;
            }
            return res;
          }));
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
      } else if (field.isArray && !(field.itemFields && field.itemFields.length > 0) && !(field.ref && field.ref.type === 'resource_id')) {
        // Simple array field (comma-separated string in form) — convert to array before zod
        // Skip array ref fields — they are already arrays from RefMultiSelect
        if (typeof val === 'string') {
          setByPath(processed, field.name, val ? val.split(',').map((s: string) => s.trim()).filter(Boolean) : []);
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
        try { setByPath(processed, group.path, JSON.parse(val)); } catch { /* keep */ }
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
          else if (sf.enumValues && sf.enumValues.length > 0) item[sf.name] = sf.isNullable ? null : (sf.enumValues[0] ?? '');
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
            <Text fw={500} size="sm">{label}</Text>
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
            <Text size="sm" c="dimmed" fs="italic">No items yet</Text>
          )}
          {items.map((_: any, index: number) => (
            <Paper key={index} withBorder p="sm" radius="sm">
              <Group justify="space-between" mb="xs">
                <Text size="xs" c="dimmed" fw={500}>#{index + 1}</Text>
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
                {field.itemFields!.map(sf => {
                  const itemPath = `${name}.${index}.${sf.name}`;
                  const subVariant = sf.variant || inferDefaultVariant(sf);

                  // Enum → Select
                  if (sf.enumValues && sf.enumValues.length > 0) {
                    return (
                      <Select
                        key={itemPath}
                        label={sf.label}
                        required={sf.isRequired}
                        data={sf.enumValues.map(v => ({ value: v, label: v }))}
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
                    const itemApiUrl = (typeof window !== 'undefined' && (import.meta as any).env?.VITE_API_URL) || '';
                    const itemBv = getByPath(form.getValues() as Record<string, any>, itemPath) as BinaryFormValue | null;
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

    // Binary/File fields — upload or URL
    if (type === 'binary') {
      const apiUrl = (typeof window !== 'undefined' && (import.meta as any).env?.VITE_API_URL) || '';
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
      return (
        <Select
          key={key}
          label={label}
          required={isRequired}
          data={selectVariant.options || []}
          {...form.getInputProps(name)}
        />
      );
    }

    // Boolean - Checkbox
    if (type === 'boolean' && effectiveVariant.type === 'checkbox') {
      return (
        <Checkbox
          key={key}
          label={label}
          {...form.getInputProps(name, { type: 'checkbox' })}
        />
      );
    }

    // Boolean - Switch (default for boolean)
    if (type === 'boolean') {
      return (
        <Switch
          key={key}
          label={label}
          {...form.getInputProps(name, { type: 'checkbox' })}
        />
      );
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

    // Default: text input
    return (
      <TextInput
        key={key}
        label={label}
        required={isRequired}
        {...form.getInputProps(name)}
      />
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
          <Tooltip label="Form field expansion depth: lower values collapse nested objects into JSON editors" withArrow>
            <Group gap={4}>
              <IconLayersSubtract size={16} />
              <Text size="xs" c="dimmed">Depth</Text>
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

/**
 * 根據 field 的 type 推斷預設的 variant
 * 當沒有明確指定 variant 時使用
 */
function inferDefaultVariant(field: ResourceField): FieldVariant {
  const { type, isArray, enumValues } = field;

  // If field has enumValues, use select
  if (enumValues && enumValues.length > 0) {
    const options = enumValues.map(v => ({ value: v, label: v }));
    return { type: 'select', options };
  }

  if (type === 'number') return { type: 'number' };
  if (type === 'boolean') return { type: 'switch' };
  if (type === 'date') return { type: 'date' };
  if (type === 'binary') return { type: 'file' };
  if (type === 'object') return { type: 'json' };
  if (isArray) return { type: 'array', itemType: 'text' };
  
  // Default to text
  return { type: 'text' };
}

/** Convert snake_case to Title Case label */
function toLabel(s: string): string {
  return s.split(/[-_]+/).map(w => w[0].toUpperCase() + w.slice(1)).join(' ');
}
