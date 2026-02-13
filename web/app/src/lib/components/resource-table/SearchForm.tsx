/**
 * 後端篩選表單 - 用結構化表單搜尋特定欄位
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Group, Button, Stack, Text, ActionIcon, TextInput, Select, NumberInput, Switch } from '@mantine/core';
import { IconPlus, IconSearch, IconFilterOff, IconTrash } from '@tabler/icons-react';
import type { SearchCondition, NormalizedSearchableField } from './types';
import { operatorLabels, getDefaultOperators } from './types';

interface SearchFormProps {
  fields: NormalizedSearchableField[];
  onSubmit: (conditions: SearchCondition[]) => void;
  initialConditions?: SearchCondition[];
  hideButtons?: boolean;
  onChange?: (conditions: SearchCondition[], isDirty: boolean) => void;
}

export function SearchForm({ fields, onSubmit, initialConditions, hideButtons, onChange }: SearchFormProps) {
  const [conditions, setConditions] = useState<SearchCondition[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isDirty, setIsDirty] = useState(false);  // 是否有未提交的變更

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

  // 當條件改變時通知外部
  const notifyChange = useCallback((newConditions: SearchCondition[], newIsDirty: boolean) => {
    onChange?.(newConditions, newIsDirty);
  }, [onChange]);

  const addCondition = () => {
    if (fields.length === 0) return;
    const firstField = fields[0];
    const defaultOperators = firstField.operators || getDefaultOperators(firstField.type);
    setConditions(prev => {
      const next = [...prev, { field: firstField.name, operator: defaultOperators[0], value: firstField.type === 'boolean' ? false : '' }];
      notifyChange(next, true);
      return next;
    });
    setIsDirty(true);
    if (!isOpen) setIsOpen(true);
  };

  const removeCondition = (index: number) => {
    setConditions(prev => {
      const next = prev.filter((_, i) => i !== index);
      notifyChange(next, true);
      return next;
    });
    setIsDirty(true);
  };

  const updateCondition = (index: number, updates: Partial<SearchCondition>) => {
    setConditions(prev => {
      const next = [...prev];
      next[index] = { ...next[index], ...updates };
      // 改變欄位時重設操作符和值
      if (updates.field !== undefined) {
        const field = fields.find(f => f.name === updates.field);
        if (field) {
          const ops = field.operators || getDefaultOperators(field.type);
          next[index].operator = ops[0];
          next[index].value = field.type === 'boolean' ? false : '';
        }
      }
      notifyChange(next, true);
      return next;
    });
    setIsDirty(true);
  };

  const handleSubmit = () => {
    onSubmit(conditions);
    setIsDirty(false);
    notifyChange(conditions, false);
  };

  const handleClear = () => {
    setConditions([]);
    onSubmit([]);
    setIsDirty(false);
    notifyChange([], false);
  };

  const renderValueInput = (condition: SearchCondition, index: number) => {
    const field = fields.find(f => f.name === condition.field);
    if (!field) return null;

    const handleKeyDown = (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') handleSubmit();
    };

    switch (field.type) {
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
            value={typeof condition.value === 'number' ? condition.value : (condition.value === '' ? undefined : Number(condition.value))}
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
            data={field.options?.map(opt => ({ value: String(opt.value), label: opt.label })) || []}
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
        return null;
    }
  };

  if (fields.length === 0) return null;

  const activeCount = conditions.length;

  return (
    <Stack gap="sm">
      {conditions.map((condition, index) => {
        const field = fields.find(f => f.name === condition.field);
        const availableOperators = field ? (field.operators || getDefaultOperators(field.type)) : [];

        return (
          <Group key={index} gap="sm" align="center" wrap="nowrap">
            <Text size="sm" c="dimmed" w={20} ta="center">{index + 1}</Text>
            <Select
              data={fields.map(f => ({ value: f.name, label: f.label }))}
              value={condition.field ?? ''}
              onChange={(val) => updateCondition(index, { field: val || '' })}
              style={{ width: 140 }}
              size="sm"
              comboboxProps={{ withinPortal: true }}
            />
            <Select
              data={availableOperators.map(op => ({ value: op, label: operatorLabels[op] || op }))}
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
