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
 *
 * Both dropdown mode and table mode share the same data pipeline:
 * `buildRequestParams()` → `useResourceList()`, with support for
 * `alwaysSearchCondition` to pre-filter the selectable items.
 */
import { useMemo, useState } from 'react';
import { Select, MultiSelect, Loader, ActionIcon, Group, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconTableFilled } from '@tabler/icons-react';
import { getResource } from '../../../resources';
import type { FieldRef } from '../../../resources';
import type { FullResource } from '../../../../types/api';
import { useResourceList } from '../../../hooks/useResourceList';
import type { SearchCondition } from '../../table/types';
import { EMPTY_ACTIVE_SEARCH } from '../../table/searchUtils';
import { buildRequestParams } from '../../table/utils';
import { RefTableSelectModal } from './RefTableSelectModal';

// ---------------------------------------------------------------------------
// Shared props & helpers
// ---------------------------------------------------------------------------

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
  /** Search conditions always applied when fetching options.
   *  Useful for narrowing selectable items (e.g. only type='weapon'). */
  alwaysSearchCondition?: SearchCondition[];
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
  /** Search conditions always applied when fetching options. */
  alwaysSearchCondition?: SearchCondition[];
}

interface SelectOption {
  value: string;
  label: string;
}

function getByPath(obj: Record<string, any>, path: string | undefined): unknown {
  if (!path) return undefined;
  return path.split('.').reduce((acc, key) => acc?.[key], obj);
}

/** Default dropdown fetch limit */
const DROPDOWN_FETCH_LIMIT = 100;

/**
 * Build request params for the dropdown list fetch.
 *
 * Uses the shared `buildRequestParams` from the table utils so that
 * `alwaysSearchCondition` is handled identically in dropdown and table modes.
 */
function buildDropdownParams(alwaysSearchCondition?: SearchCondition[]): Record<string, unknown> {
  const params = buildRequestParams({
    mode: 'server',
    pagination: { pageIndex: 0, pageSize: DROPDOWN_FETCH_LIMIT },
    activeSearch: EMPTY_ACTIVE_SEARCH,
    sorting: [],
    columnFilters: [],
    alwaysSearchCondition,
  });
  // Dropdown always filters out soft-deleted resources
  params.is_deleted = false;
  return params;
}

/**
 * Map raw resource list data to SelectOption[] for the dropdown.
 * `valueField` controls which meta field is used as the option value.
 */
function toSelectOptions(
  data: FullResource<unknown>[],
  displayNameField: string | undefined,
  valueField: 'resource_id' | 'current_revision_id',
): SelectOption[] {
  return data.map((item: any) => {
    const meta = item.meta ?? {};
    const d = item.data ?? {};
    const resourceId = meta.resource_id ?? '';
    const preferred = getByPath(d, displayNameField);
    const displayName =
      typeof preferred === 'string' && preferred.trim().length > 0
        ? preferred
        : d.name || d.title || d.label || resourceId;

    if (valueField === 'current_revision_id') {
      const revisionId = meta.current_revision_id ?? '';
      const shortRevision =
        revisionId.length > 12 ? `${revisionId.slice(0, 4)}…${revisionId.slice(-4)}` : revisionId;
      return {
        value: revisionId,
        label: `${displayName} (rev: ${shortRevision})`,
      };
    }

    return {
      value: resourceId,
      label: `${displayName} (${resourceId.slice(0, 8)}…)`,
    };
  });
}

// ---------------------------------------------------------------------------
// RefSelect — single select for Ref fields
// ---------------------------------------------------------------------------

export function RefSelect({
  label,
  required,
  fieldRef,
  value,
  onChange,
  error,
  clearable = true,
  alwaysSearchCondition,
}: RefSelectProps) {
  const config = getResource(fieldRef.resource);
  const params = useMemo(() => buildDropdownParams(alwaysSearchCondition), [alwaysSearchCondition]);
  const { data, loading } = useResourceList(config!, params);
  const options = useMemo(
    () => toSelectOptions(data, config?.displayNameField, 'resource_id'),
    [data, config?.displayNameField],
  );

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
        alwaysSearchCondition={alwaysSearchCondition}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// RefMultiSelect — multi select for Ref fields (N:N)
// ---------------------------------------------------------------------------

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
  alwaysSearchCondition,
}: RefMultiSelectProps) {
  const config = getResource(fieldRef.resource);
  const params = useMemo(() => buildDropdownParams(alwaysSearchCondition), [alwaysSearchCondition]);
  const { data, loading } = useResourceList(config!, params);
  const options = useMemo(
    () => toSelectOptions(data, config?.displayNameField, 'resource_id'),
    [data, config?.displayNameField],
  );

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
        alwaysSearchCondition={alwaysSearchCondition}
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
  /** Search conditions always applied when fetching options. */
  alwaysSearchCondition?: SearchCondition[];
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
  alwaysSearchCondition,
}: RefRevisionSelectProps) {
  const config = getResource(fieldRef.resource);
  const params = useMemo(() => buildDropdownParams(alwaysSearchCondition), [alwaysSearchCondition]);
  const { data, loading } = useResourceList(config!, params);
  const options = useMemo(
    () => toSelectOptions(data, config?.displayNameField, 'current_revision_id'),
    [data, config?.displayNameField],
  );

  const [searchValue, setSearchValue] = useState('');
  const [tableOpened, { open: openTable, close: closeTable }] = useDisclosure(false);

  return (
    <>
      <Group wrap="nowrap" align="flex-end" gap={4}>
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
        alwaysSearchCondition={alwaysSearchCondition}
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
  /** Search conditions always applied when fetching options. */
  alwaysSearchCondition?: SearchCondition[];
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
  alwaysSearchCondition,
}: RefRevisionMultiSelectProps) {
  const config = getResource(fieldRef.resource);
  const params = useMemo(() => buildDropdownParams(alwaysSearchCondition), [alwaysSearchCondition]);
  const { data, loading } = useResourceList(config!, params);
  const options = useMemo(
    () => toSelectOptions(data, config?.displayNameField, 'current_revision_id'),
    [data, config?.displayNameField],
  );

  const [searchValue, setSearchValue] = useState('');
  const [tableOpened, { open: openTable, close: closeTable }] = useDisclosure(false);

  return (
    <>
      <Group wrap="nowrap" align="flex-end" gap={4}>
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
        alwaysSearchCondition={alwaysSearchCondition}
      />
    </>
  );
}
