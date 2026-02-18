/**
 * RefSelect — a searchable select input that fetches options from the referenced resource's API.
 *
 * Used in forms when a field has `ref` metadata (from Annotated[str, Ref(...)]).
 * Replaces a plain TextInput with a Select dropdown that lists available resources.
 *
 * RefMultiSelect — same but for list[Annotated[str, Ref(...)]] (N:N relationships).
 *
 * RefRevisionSelect — used for RefRevision fields, lists current_revision_id of all resources.
 * RefRevisionMultiSelect — same but for list[Annotated[str, RefRevision(...)]].
 */
import { useCallback, useEffect, useState } from 'react';
import { Select, MultiSelect, Loader } from '@mantine/core';
import { getResource } from '../../resources';
import type { FieldRef } from '../../resources';

interface RefSelectProps {
  /** Field label */
  label: string;
  /** Whether the field is required */
  required?: boolean;
  /** Ref metadata from the field definition */
  fieldRef: FieldRef;
  /** Current value */
  value: string | null;
  /** Change handler */
  onChange: (value: string | null) => void;
  /** Error message (from form validation) */
  error?: string;
  /** Whether the field is clearable (nullable) */
  clearable?: boolean;
}

interface SelectOption {
  value: string;
  label: string;
}

function getByPath(obj: Record<string, any>, path: string | undefined): unknown {
  if (!path) return undefined;
  return path.split('.').reduce((acc, key) => acc?.[key], obj);
}

function useRefOptions(resource: string) {
  const [options, setOptions] = useState<SelectOption[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchOptions = useCallback(async () => {
    const targetResource = getResource(resource);
    if (!targetResource?.apiClient) return;

    setLoading(true);
    try {
      const resp = await targetResource.apiClient.listFull({ limit: 100, is_deleted: false });
      const items = resp.data || [];
      const newOptions: SelectOption[] = items.map((item: any) => {
        const resourceId = item.meta?.resource_id ?? '';
        const data = item.data ?? {};
        const preferred = getByPath(data, targetResource.displayNameField);
        const displayName =
          typeof preferred === 'string' && preferred.trim().length > 0
            ? preferred
            : data.name || data.title || data.label || resourceId;
        return {
          value: resourceId,
          label: `${displayName} (${resourceId.slice(0, 8)}…)`,
        };
      });
      setOptions(newOptions);
    } catch (err) {
      console.error(`RefSelect: failed to fetch ${resource}`, err);
      setOptions([]);
    } finally {
      setLoading(false);
    }
  }, [resource]);

  useEffect(() => {
    fetchOptions();
  }, [fetchOptions]);

  return { options, loading };
}

export function RefSelect({
  label,
  required,
  fieldRef,
  value,
  onChange,
  error,
  clearable = true,
}: RefSelectProps) {
  const { options, loading } = useRefOptions(fieldRef.resource);
  const [searchValue, setSearchValue] = useState('');

  return (
    <Select
      label={label}
      required={required}
      placeholder={`Select ${fieldRef.resource}…`}
      data={options}
      value={value}
      onChange={onChange}
      searchable
      searchValue={searchValue}
      onSearchChange={setSearchValue}
      clearable={clearable}
      nothingFoundMessage={loading ? 'Loading…' : 'No results'}
      error={error}
      rightSection={loading ? <Loader size="xs" /> : undefined}
    />
  );
}

interface RefMultiSelectProps {
  /** Field label */
  label: string;
  /** Whether the field is required */
  required?: boolean;
  /** Ref metadata from the field definition */
  fieldRef: FieldRef;
  /** Current values */
  value: string[];
  /** Change handler */
  onChange: (value: string[]) => void;
  /** Error message (from form validation) */
  error?: string;
}

/**
 * Multi-select for list[Annotated[str, Ref(...)]] fields (N:N relationships).
 */
export function RefMultiSelect({
  label,
  required,
  fieldRef,
  value,
  onChange,
  error,
}: RefMultiSelectProps) {
  const { options, loading } = useRefOptions(fieldRef.resource);
  const [searchValue, setSearchValue] = useState('');

  return (
    <MultiSelect
      label={label}
      required={required}
      placeholder={`Select ${fieldRef.resource}…`}
      data={options}
      value={value}
      onChange={onChange}
      searchable
      searchValue={searchValue}
      onSearchChange={setSearchValue}
      clearable
      nothingFoundMessage={loading ? 'Loading…' : 'No results'}
      error={error}
      rightSection={loading ? <Loader size="xs" /> : undefined}
    />
  );
}

// ============= RefRevision Support =============

interface RefRevisionSelectProps {
  /** Field label */
  label: string;
  /** Whether the field is required */
  required?: boolean;
  /** Ref metadata from the field definition */
  fieldRef: FieldRef;
  /** Current value (revision_id) */
  value: string | null;
  /** Change handler */
  onChange: (value: string | null) => void;
  /** Error message (from form validation) */
  error?: string;
  /** Whether the field is clearable (nullable) */
  clearable?: boolean;
}

function useRefRevisionOptions(resource: string) {
  const [options, setOptions] = useState<SelectOption[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchOptions = useCallback(async () => {
    const targetResource = getResource(resource);
    if (!targetResource?.apiClient) return;

    setLoading(true);
    try {
      const resp = await targetResource.apiClient.listFull({ limit: 100, is_deleted: false });
      const items = resp.data || [];
      const newOptions: SelectOption[] = items.map((item: any) => {
        const meta = item.meta ?? {};
        const data = item.data ?? {};
        const resourceId = meta.resource_id ?? '';
        const revisionId = meta.current_revision_id ?? '';
        const preferred = getByPath(data, targetResource.displayNameField);
        const displayName =
          typeof preferred === 'string' && preferred.trim().length > 0
            ? preferred
            : data.name || data.title || data.label || resourceId;
        const shortRevision =
          revisionId.length > 12 ? `${revisionId.slice(0, 4)}…${revisionId.slice(-4)}` : revisionId;
        return {
          value: revisionId,
          label: `${displayName} (rev: ${shortRevision})`,
        };
      });
      setOptions(newOptions);
    } catch (err) {
      console.error(`RefRevisionSelect: failed to fetch ${resource}`, err);
      setOptions([]);
    } finally {
      setLoading(false);
    }
  }, [resource]);

  useEffect(() => {
    fetchOptions();
  }, [fetchOptions]);

  return { options, loading };
}

/**
 * Select for Annotated[str, RefRevision(...)] fields.
 * Lists all resources' current_revision_id from the target resource type.
 */
export function RefRevisionSelect({
  label,
  required,
  fieldRef,
  value,
  onChange,
  error,
  clearable = true,
}: RefRevisionSelectProps) {
  const { options, loading } = useRefRevisionOptions(fieldRef.resource);
  const [searchValue, setSearchValue] = useState('');

  return (
    <Select
      label={label}
      required={required}
      placeholder={`Select ${fieldRef.resource} revision…`}
      data={options}
      value={value}
      onChange={onChange}
      searchable
      searchValue={searchValue}
      onSearchChange={setSearchValue}
      clearable={clearable}
      nothingFoundMessage={loading ? 'Loading…' : 'No results'}
      error={error}
      rightSection={loading ? <Loader size="xs" /> : undefined}
    />
  );
}

interface RefRevisionMultiSelectProps {
  /** Field label */
  label: string;
  /** Whether the field is required */
  required?: boolean;
  /** Ref metadata from the field definition */
  fieldRef: FieldRef;
  /** Current values (revision_ids) */
  value: string[];
  /** Change handler */
  onChange: (value: string[]) => void;
  /** Error message (from form validation) */
  error?: string;
}

/**
 * Multi-select for list[Annotated[str, RefRevision(...)]] fields.
 */
export function RefRevisionMultiSelect({
  label,
  required,
  fieldRef,
  value,
  onChange,
  error,
}: RefRevisionMultiSelectProps) {
  const { options, loading } = useRefRevisionOptions(fieldRef.resource);
  const [searchValue, setSearchValue] = useState('');

  return (
    <MultiSelect
      label={label}
      required={required}
      placeholder={`Select ${fieldRef.resource} revisions…`}
      data={options}
      value={value}
      onChange={onChange}
      searchable
      searchValue={searchValue}
      onSearchChange={setSearchValue}
      clearable
      nothingFoundMessage={loading ? 'Loading…' : 'No results'}
      error={error}
      rightSection={loading ? <Loader size="xs" /> : undefined}
    />
  );
}
