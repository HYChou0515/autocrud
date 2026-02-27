/**
 * RefSelect — a searchable select input that fetches options from the referenced resource's API.
 *
 * Used in forms when a field has `ref` metadata (from Annotated[str, Ref(...)]).
 * Replaces a plain TextInput with a Select dropdown that lists available resources.
 *
 * RefMultiSelect — same but for list[Annotated[str, Ref(...)]] (N:N relationships).
 *
 * RefRevisionSelect — version-aware reference select that lets users pick either
 * a resource_id (meaning "latest") or a specific revision_id (pinned).
 * RefRevisionMultiSelect — same but for list fields.
 */
import { useCallback, useEffect, useState } from 'react';
import { Select, MultiSelect, Loader, ActionIcon, Group, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconTableFilled } from '@tabler/icons-react';
import { getResource } from '../../../resources';
import type { FieldRef } from '../../../resources';
import { RefTableSelectModal } from './RefTableSelectModal';

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
  const [tableOpened, { open: openTable, close: closeTable }] = useDisclosure(false);

  return (
    <>
      <Group wrap="nowrap" align="flex-end" gap={4}>
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
          style={{ flex: 1 }}
        />
        <Tooltip label="用表格選擇">
          <ActionIcon variant="light" size="lg" onClick={openTable} mb={error ? 22 : 0}>
            <IconTableFilled size={18} />
          </ActionIcon>
        </Tooltip>
      </Group>
      <RefTableSelectModal
        opened={tableOpened}
        onClose={closeTable}
        onConfirm={(selected) => onChange(selected[0] ?? null)}
        resourceName={fieldRef.resource}
        mode="single"
        selectedValues={value ? [value] : []}
        valueField="resource_id"
      />
    </>
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
  const [tableOpened, { open: openTable, close: closeTable }] = useDisclosure(false);

  return (
    <>
      <Group wrap="nowrap" align="flex-end" gap={4}>
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
          style={{ flex: 1 }}
        />
        <Tooltip label="用表格選擇">
          <ActionIcon variant="light" size="lg" onClick={openTable} mb={error ? 22 : 0}>
            <IconTableFilled size={18} />
          </ActionIcon>
        </Tooltip>
      </Group>
      <RefTableSelectModal
        opened={tableOpened}
        onClose={closeTable}
        onConfirm={(selected) => onChange(selected)}
        resourceName={fieldRef.resource}
        mode="multi"
        selectedValues={value}
        valueField="resource_id"
      />
    </>
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

interface GroupedSelectOption {
  group: string;
  items: SelectOption[];
}

/**
 * Hook to fetch version-aware reference options.
 * Returns two groups: "Latest" (resource_id) and "Specific Revision" (revision_id).
 */
function useRefRevisionOptions(resource: string) {
  const [options, setOptions] = useState<GroupedSelectOption[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchOptions = useCallback(async () => {
    const targetResource = getResource(resource);
    if (!targetResource?.apiClient) return;

    setLoading(true);
    try {
      const resp = await targetResource.apiClient.listFull({ limit: 100, is_deleted: false });
      const items = resp.data || [];

      const latestItems: SelectOption[] = [];
      const revisionItems: SelectOption[] = [];

      for (const item of items) {
        const meta = (item as any).meta ?? {};
        const data = (item as any).data ?? {};
        const resourceId: string = meta.resource_id ?? '';
        const revisionId: string = meta.current_revision_id ?? '';
        const preferred = getByPath(data, targetResource.displayNameField);
        const displayName =
          typeof preferred === 'string' && preferred.trim().length > 0
            ? preferred
            : data.name || data.title || data.label || resourceId;

        // "Latest" option — stores resource_id
        const shortResId =
          resourceId.length > 12
            ? `${resourceId.slice(0, 4)}…${resourceId.slice(-4)}`
            : resourceId;
        latestItems.push({
          value: resourceId,
          label: `${displayName} (${shortResId})`,
        });

        // "Specific Revision" option — stores revision_id
        const shortRevision =
          revisionId.length > 12
            ? `${revisionId.slice(0, 4)}…${revisionId.slice(-4)}`
            : revisionId;
        revisionItems.push({
          value: revisionId,
          label: `${displayName} (rev: ${shortRevision})`,
        });
      }

      setOptions([
        { group: 'Latest', items: latestItems },
        { group: 'Pinned Revision', items: revisionItems },
      ]);
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
 * Select for version-aware reference fields (Ref with ref_type='revision_id').
 * Lets users pick either a resource_id (latest) or a specific revision_id (pinned).
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
  const [tableOpened, { open: openTable, close: closeTable }] = useDisclosure(false);

  return (
    <>
      <Group wrap="nowrap" align="flex-end" gap={4}>
        <Select
          label={label}
          required={required}
          placeholder={`Select ${fieldRef.resource} (latest or revision)…`}
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
          style={{ flex: 1 }}
        />
        <Tooltip label="用表格選擇">
          <ActionIcon variant="light" size="lg" onClick={openTable} mb={error ? 22 : 0}>
            <IconTableFilled size={18} />
          </ActionIcon>
        </Tooltip>
      </Group>
      <RefTableSelectModal
        opened={tableOpened}
        onClose={closeTable}
        onConfirm={(selected) => onChange(selected[0] ?? null)}
        resourceName={fieldRef.resource}
        mode="single"
        selectedValues={value ? [value] : []}
        valueField="current_revision_id"
      />
    </>
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
 * Multi-select for version-aware reference list fields.
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
  const [tableOpened, { open: openTable, close: closeTable }] = useDisclosure(false);

  return (
    <>
      <Group wrap="nowrap" align="flex-end" gap={4}>
        <MultiSelect
          label={label}
          required={required}
          placeholder={`Select ${fieldRef.resource} (latest or revisions)…`}
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
          style={{ flex: 1 }}
        />
        <Tooltip label="用表格選擇">
          <ActionIcon variant="light" size="lg" onClick={openTable} mb={error ? 22 : 0}>
            <IconTableFilled size={18} />
          </ActionIcon>
        </Tooltip>
      </Group>
      <RefTableSelectModal
        opened={tableOpened}
        onClose={closeTable}
        onConfirm={(selected) => onChange(selected)}
        resourceName={fieldRef.resource}
        mode="multi"
        selectedValues={value}
        valueField="current_revision_id"
      />
    </>
  );
}
