/**
 * 後端篩選表單 - 用結構化表單搜尋特定欄位
 *
 * Bug 1 fix: onChange notifications are deferred to a useEffect instead of
 * being called inside setState updater functions, which previously caused
 * "Cannot update a component while rendering a different component" warnings.
 *
 * Bug 4 fix: Field selector uses Autocomplete to allow arbitrary dot-path
 * input (e.g. "stats.hp") for deep field searching.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Group,
  Button,
  Stack,
  Text,
  ActionIcon,
  TextInput,
  Select,
  NumberInput,
  Switch,
  Autocomplete,
  type AutocompleteProps,
  type ComboboxItem,
  type ComboboxParsedItem,
} from '@mantine/core';
import { IconPlus, IconSearch, IconFilterOff, IconTrash } from '@tabler/icons-react';
import type { SearchCondition, NormalizedSearchableField } from './types';
import { operatorLabels, getDefaultOperators } from './types';

// ---------------------------------------------------------------------------
// Pure helpers — exported for testing
// ---------------------------------------------------------------------------

/**
 * Build a name→label Map from searchable fields.
 */
export function buildFieldLabelMap(
  fields: readonly { name: string; label: string }[],
): Map<string, string> {
  const m = new Map<string, string>();
  for (const f of fields) m.set(f.name, f.label);
  return m;
}

/**
 * Filter autocomplete options matching both field name and label.
 * Used in Autocomplete `filter` prop.
 *
 * Generic over T so that Mantine `ComboboxItem` objects pass through
 * without losing their required `label` property.
 */
export function filterFieldOptionsFn<T extends { value: string }>(
  options: readonly T[],
  search: string,
  labelMap: Map<string, string>,
): T[] {
  const lower = search.toLowerCase().trim();
  if (!lower) return options as T[];
  return (options as T[]).filter((opt) => {
    if (opt.value.toLowerCase().includes(lower)) return true;
    const label = labelMap.get(opt.value);
    return label ? label.toLowerCase().includes(lower) : false;
  });
}

interface SearchFormProps {
  fields: NormalizedSearchableField[];
  onSubmit: (conditions: SearchCondition[]) => void;
  initialConditions?: SearchCondition[];
  hideButtons?: boolean;
  onChange?: (conditions: SearchCondition[], isDirty: boolean) => void;
}

export function SearchForm({
  fields,
  onSubmit,
  initialConditions,
  hideButtons,
  onChange,
}: SearchFormProps) {
  const [conditions, setConditions] = useState<SearchCondition[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isDirty, setIsDirty] = useState(false); // 是否有未提交的變更

  // Track whether the current dirty change is user-driven (not from initialConditions sync)
  const isUserDriven = useRef(false);

  // 用來追蹤 initialConditions 的字串化版本，判斷是否有變化
  const prevInitialRef = useRef<string>('');

  // 從 initialConditions 同步表單狀態（初始化或重置）
  useEffect(() => {
    const currentInitial = JSON.stringify(initialConditions ?? []);
    if (currentInitial === prevInitialRef.current) return;
    prevInitialRef.current = currentInitial;

    if (!initialConditions || initialConditions.length === 0) {
      // URL 被清空，重置表單
      setConditions([]);
      setIsOpen(false);
      setIsDirty(false);
    } else {
      // 從 URL 初始化
      setConditions(initialConditions);
      setIsOpen(true);
    }
  }, [initialConditions]);

  // Bug 1 fix: Notify parent via useEffect instead of inside setState updater.
  // Only fires when user-driven changes happen (not from initialConditions sync).
  useEffect(() => {
    if (!isUserDriven.current) return;
    isUserDriven.current = false;
    onChange?.(conditions, isDirty);
  }, [conditions, isDirty, onChange]);

  const addCondition = () => {
    isUserDriven.current = true;
    setConditions((prev) => [
      ...prev,
      {
        field: '',
        operator: 'eq',
        value: '',
      },
    ]);
    setIsDirty(true);
    if (!isOpen) setIsOpen(true);
  };

  const removeCondition = (index: number) => {
    isUserDriven.current = true;
    setConditions((prev) => prev.filter((_, i) => i !== index));
    setIsDirty(true);
  };

  const updateCondition = (index: number, updates: Partial<SearchCondition>) => {
    isUserDriven.current = true;
    setConditions((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], ...updates };
      // 改變欄位時重設操作符和值
      if (updates.field !== undefined) {
        const field = fields.find((f) => f.name === updates.field);
        if (field) {
          const ops = field.operators || getDefaultOperators(field.type);
          next[index].operator = ops[0];
          next[index].value = field.type === 'boolean' ? false : '';
        } else {
          // Bug 4: Unknown field (manual dot-path input) → default to string operators
          const ops = getDefaultOperators('string');
          next[index].operator = ops[0];
          next[index].value = '';
        }
      }
      return next;
    });
    setIsDirty(true);
  };

  const handleSubmit = () => {
    onSubmit(conditions);
    setIsDirty(false);
    // Direct call is fine here — it's an event handler, not during render
    onChange?.(conditions, false);
  };

  const handleClear = () => {
    setConditions([]);
    onSubmit([]);
    setIsDirty(false);
    onChange?.([], false);
  };

  const renderValueInput = (condition: SearchCondition, index: number) => {
    const field = fields.find((f) => f.name === condition.field);
    // Bug 4: fallback to string type for unknown fields (manual dot-path input)
    const fieldType = field?.type ?? 'string';

    const handleKeyDown = (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') handleSubmit();
    };

    switch (fieldType) {
      case 'string':
        return (
          <TextInput
            placeholder="輸入值..."
            value={condition.value != null ? String(condition.value) : ''}
            onChange={(e) => updateCondition(index, { value: e.target.value })}
            onKeyDown={handleKeyDown}
            style={{ flex: 1 }}
            size="sm"
          />
        );
      case 'number':
        return (
          <NumberInput
            placeholder="數值"
            value={
              typeof condition.value === 'number'
                ? condition.value
                : condition.value === ''
                  ? undefined
                  : Number(condition.value)
            }
            onChange={(val) => updateCondition(index, { value: val ?? 0 })}
            onKeyDown={handleKeyDown}
            style={{ flex: 1, minWidth: 100 }}
            size="sm"
          />
        );
      case 'boolean':
        return (
          <Switch
            checked={Boolean(condition.value)}
            onChange={(e) => updateCondition(index, { value: e.target.checked })}
            label={condition.value ? 'True' : 'False'}
            size="sm"
          />
        );
      case 'select':
        return (
          <Select
            placeholder="選擇..."
            data={
              field?.options?.map((opt) => ({ value: String(opt.value), label: opt.label })) || []
            }
            value={condition.value != null ? String(condition.value) : ''}
            onChange={(val) => updateCondition(index, { value: val ?? '' })}
            style={{ flex: 1 }}
            size="sm"
          />
        );
      case 'date':
        return (
          <TextInput
            type="date"
            value={condition.value != null ? String(condition.value) : ''}
            onChange={(e) => updateCondition(index, { value: e.target.value })}
            onKeyDown={handleKeyDown}
            style={{ flex: 1 }}
            size="sm"
          />
        );
      default:
        return (
          <TextInput
            placeholder="輸入值..."
            value={condition.value != null ? String(condition.value) : ''}
            onChange={(e) => updateCondition(index, { value: e.target.value })}
            onKeyDown={handleKeyDown}
            style={{ flex: 1 }}
            size="sm"
          />
        );
    }
  };

  const activeCount = conditions.length;

  // Autocomplete data: plain field names (value = name displayed & returned on select)
  const fieldAutocompleteData = useMemo(() => fields.map((f) => f.name), [fields]);

  // Build a quick name→label lookup for renderOption / filter
  const fieldLabelMap = useMemo(() => buildFieldLabelMap(fields), [fields]);

  // Render dropdown options with descriptive labels
  const renderFieldOption: AutocompleteProps['renderOption'] = useCallback(
    ({ option }: { option: { value: string } }) => {
      const label = fieldLabelMap.get(option.value);
      return label && label !== option.value ? `${label} (${option.value})` : option.value;
    },
    [fieldLabelMap],
  );

  // Custom filter matching both name and label so typing "Level" still finds "level".
  // Mantine OptionsFilter expects (FilterOptionsInput) => ComboboxParsedItem[].
  // Our data is always flat strings, so all parsed items are ComboboxItem.
  const filterFieldOptions: AutocompleteProps['filter'] = useCallback(
    (input: { options: ComboboxParsedItem[]; search: string; limit: number }) => {
      // Narrow to ComboboxItem (exclude group headers)
      const items = input.options.filter((o): o is ComboboxItem => 'value' in o);
      return filterFieldOptionsFn(items, input.search, fieldLabelMap);
    },
    [fieldLabelMap],
  );

  return (
    <Stack gap="sm">
      {conditions.map((condition, index) => {
        const field = fields.find((f) => f.name === condition.field);
        // Fallback operators for unknown / empty fields
        const availableOperators = field
          ? field.operators || getDefaultOperators(field.type)
          : getDefaultOperators('string');

        return (
          <Group key={index} gap="sm" align="center" wrap="nowrap">
            <Text size="sm" c="dimmed" w={20} ta="center">
              {index + 1}
            </Text>
            {/* Autocomplete: plain-string data avoids label/value confusion */}
            <Autocomplete
              data={fieldAutocompleteData}
              renderOption={renderFieldOption}
              filter={filterFieldOptions}
              value={condition.field ?? ''}
              onChange={(val) => updateCondition(index, { field: val || '' })}
              style={{ width: 180 }}
              size="sm"
              placeholder="欄位名稱..."
              comboboxProps={{ withinPortal: true }}
            />
            <Select
              data={availableOperators.map((op) => ({
                value: op,
                label: operatorLabels[op] || op,
              }))}
              value={condition.operator ?? 'eq'}
              onChange={(val) => updateCondition(index, { operator: val || 'eq' })}
              style={{ width: 90 }}
              size="sm"
              comboboxProps={{ withinPortal: true }}
            />
            {renderValueInput(condition, index)}
            <ActionIcon
              color="red"
              variant="subtle"
              size="sm"
              onClick={() => removeCondition(index)}
            >
              <IconTrash size={14} />
            </ActionIcon>
          </Group>
        );
      })}

      <Group gap="sm" justify="space-between">
        <Button
          size="xs"
          variant="subtle"
          leftSection={<IconPlus size={14} />}
          onClick={addCondition}
        >
          新增條件
        </Button>
        {!hideButtons && (
          <Group gap="xs">
            {activeCount > 0 && (
              <Button
                size="xs"
                variant="subtle"
                color="gray"
                leftSection={<IconFilterOff size={14} />}
                onClick={handleClear}
              >
                清除
              </Button>
            )}
            <Button
              size="xs"
              disabled={!isDirty && activeCount === 0}
              leftSection={<IconSearch size={14} />}
              onClick={handleSubmit}
            >
              搜尋
            </Button>
          </Group>
        )}
      </Group>
    </Stack>
  );
}
