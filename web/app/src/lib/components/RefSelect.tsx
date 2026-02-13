/**
 * RefSelect — a searchable select input that fetches options from the referenced resource's API.
 *
 * Used in forms when a field has `ref` metadata (from Annotated[str, Ref(...)]).
 * Replaces a plain TextInput with a Select dropdown that lists available resources.
 */
import { useCallback, useEffect, useState } from 'react';
import { Select, Loader } from '@mantine/core';
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

export function RefSelect({
  label,
  required,
  fieldRef,
  value,
  onChange,
  error,
  clearable = true,
}: RefSelectProps) {
  const [options, setOptions] = useState<SelectOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchValue, setSearchValue] = useState('');

  const fetchOptions = useCallback(async () => {
    const targetResource = getResource(fieldRef.resource);
    if (!targetResource?.apiClient) return;

    setLoading(true);
    try {
      const resp = await targetResource.apiClient.listFull({ limit: 100, is_deleted: false });
      const items = resp.data || [];
      const newOptions: SelectOption[] = items.map((item: any) => {
        const resourceId = item.meta?.resource_id ?? '';
        // Try to find a human-readable label from the data
        const data = item.data ?? {};
        const displayName = data.name || data.title || data.label || resourceId;
        return {
          value: resourceId,
          label: `${displayName} (${resourceId.slice(0, 8)}…)`,
        };
      });
      setOptions(newOptions);
    } catch (err) {
      console.error(`RefSelect: failed to fetch ${fieldRef.resource}`, err);
      setOptions([]);
    } finally {
      setLoading(false);
    }
  }, [fieldRef.resource]);

  useEffect(() => {
    fetchOptions();
  }, [fetchOptions]);

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
