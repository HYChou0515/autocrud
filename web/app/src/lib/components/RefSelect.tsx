/**
 * RefSelect — a searchable select input that fetches options from the referenced resource's API.
 *
 * Used in forms when a field has `ref` metadata (from Annotated[str, Ref(...)]).
 * Replaces a plain TextInput with a Select dropdown that lists available resources.
 *
 * RefMultiSelect — same but for list[Annotated[str, Ref(...)]] (N:N relationships).
 */
import { useCallback, useEffect, useState } from 'react';
import { Select, MultiSelect, Loader } from '@mantine/core';
import { getResource } from '../resources';
import type { FieldRef } from '../resources';

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
        const displayName = data.name || data.title || data.label || resourceId;
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
