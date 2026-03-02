/**
 * Meta 搜尋表單 - 內建的 meta 欄位篩選（創建時間、更新時間、創建者、更新者）
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Group, Button, Stack, Text, TextInput } from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { IconSearch, IconFilterOff } from '@tabler/icons-react';
import type { MetaFilters } from './types';

/** Date → ISO string */
function dateToISO(d: Date | null): string {
  if (!d) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  const h = d.getHours(),
    m = d.getMinutes(),
    s = d.getSeconds();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(h)}:${pad(m)}:${pad(s)}`;
}

/** 處理結束時間：如果用戶只選日期（時間為 00:00:00），自動設為當天 23:59:59 */
function adjustEndTime(d: Date | null): Date | null {
  if (!d) return null;
  if (d.getHours() === 0 && d.getMinutes() === 0 && d.getSeconds() === 0) {
    const adjusted = new Date(d);
    adjusted.setHours(23, 59, 59);
    return adjusted;
  }
  return d;
}

/** 將 ISO 字串轉換回 Date 物件 */
function parseISO(isoStr: string | undefined): Date | null {
  if (!isoStr) return null;
  const d = new Date(isoStr);
  return isNaN(d.getTime()) ? null : d;
}

interface MetaSearchFormProps {
  onSubmit: (filters: MetaFilters) => void;
  initialValues?: MetaFilters;
  hideButtons?: boolean;
  onChange?: (filters: MetaFilters, isDirty: boolean) => void;
}

export function MetaSearchForm({
  onSubmit,
  initialValues,
  hideButtons,
  onChange,
}: MetaSearchFormProps) {
  const [createdStart, setCreatedStart] = useState<Date | null>(null);
  const [createdEnd, setCreatedEnd] = useState<Date | null>(null);
  const [updatedStart, setUpdatedStart] = useState<Date | null>(null);
  const [updatedEnd, setUpdatedEnd] = useState<Date | null>(null);
  const [createdBy, setCreatedBy] = useState('');
  const [updatedBy, setUpdatedBy] = useState('');
  const [isDirty, setIsDirty] = useState(false);

  // 用來追蹤 initialValues 的字串化版本，判斷是否有變化
  const prevInitialRef = useRef<string>('');

  // 從 initialValues 同步表單狀態（初始化或重置）
  useEffect(() => {
    const currentInitial = JSON.stringify(initialValues ?? {});
    if (currentInitial === prevInitialRef.current) return;
    prevInitialRef.current = currentInitial;

    if (!initialValues || Object.keys(initialValues).length === 0) {
      // URL 被清空，重置表單
      setCreatedStart(null);
      setCreatedEnd(null);
      setUpdatedStart(null);
      setUpdatedEnd(null);
      setCreatedBy('');
      setUpdatedBy('');
      setIsDirty(false);
    } else {
      // 從 URL 初始化
      setCreatedStart(parseISO(initialValues.created_time_start));
      setCreatedEnd(parseISO(initialValues.created_time_end));
      setUpdatedStart(parseISO(initialValues.updated_time_start));
      setUpdatedEnd(parseISO(initialValues.updated_time_end));
      setCreatedBy(initialValues.created_by ?? '');
      setUpdatedBy(initialValues.updated_by ?? '');
    }
  }, [initialValues]);

  const buildFilters = useCallback((): MetaFilters => {
    const f: MetaFilters = {};
    const cs = dateToISO(createdStart);
    const ce = dateToISO(createdEnd);
    const us = dateToISO(updatedStart);
    const ue = dateToISO(updatedEnd);
    if (cs) f.created_time_start = cs;
    if (ce) f.created_time_end = ce;
    if (us) f.updated_time_start = us;
    if (ue) f.updated_time_end = ue;
    if (createdBy) f.created_by = createdBy;
    if (updatedBy) f.updated_by = updatedBy;
    return f;
  }, [createdStart, createdEnd, updatedStart, updatedEnd, createdBy, updatedBy]);

  // 當 filters 變化時通知外部
  useEffect(() => {
    if (isDirty) {
      onChange?.(buildFilters(), true);
    }
  }, [isDirty, buildFilters, onChange]);

  const markDirty = () => setIsDirty(true);

  const handleSubmit = () => {
    const filters = buildFilters();
    onSubmit(filters);
    setIsDirty(false);
    onChange?.(filters, false);
  };

  const handleClear = () => {
    setCreatedStart(null);
    setCreatedEnd(null);
    setUpdatedStart(null);
    setUpdatedEnd(null);
    setCreatedBy('');
    setUpdatedBy('');
    onSubmit({});
    setIsDirty(false);
    onChange?.({}, false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSubmit();
  };

  const activeCount = Object.keys(buildFilters()).length;

  return (
    <Stack gap="sm">
      {/* 創建時間區間 */}
      <Group gap="sm" align="flex-end">
        <DateTimePicker
          label="創建時間（從）"
          placeholder="選擇起始時間"
          value={createdStart}
          onChange={(v) => {
            setCreatedStart(v);
            markDirty();
          }}
          clearable
          valueFormat="YYYY-MM-DD HH:mm"
          size="sm"
          style={{ flex: 1 }}
        />
        <Text size="sm" c="dimmed" pb={8}>
          —
        </Text>
        <DateTimePicker
          label="創建時間（到）"
          placeholder="選擇結束時間"
          value={createdEnd}
          onChange={(v) => {
            setCreatedEnd(adjustEndTime(v));
            markDirty();
          }}
          clearable
          valueFormat="YYYY-MM-DD HH:mm"
          minDate={createdStart || undefined}
          size="sm"
          style={{ flex: 1 }}
        />
      </Group>

      {/* 更新時間區間 */}
      <Group gap="sm" align="flex-end">
        <DateTimePicker
          label="更新時間（從）"
          placeholder="選擇起始時間"
          value={updatedStart}
          onChange={(v) => {
            setUpdatedStart(v);
            markDirty();
          }}
          clearable
          valueFormat="YYYY-MM-DD HH:mm"
          size="sm"
          style={{ flex: 1 }}
        />
        <Text size="sm" c="dimmed" pb={8}>
          —
        </Text>
        <DateTimePicker
          label="更新時間（到）"
          placeholder="選擇結束時間"
          value={updatedEnd}
          onChange={(v) => {
            setUpdatedEnd(adjustEndTime(v));
            markDirty();
          }}
          clearable
          valueFormat="YYYY-MM-DD HH:mm"
          minDate={updatedStart || undefined}
          size="sm"
          style={{ flex: 1 }}
        />
      </Group>

      {/* 人員 + 狀態 */}
      <Group gap="sm" align="flex-end" grow>
        <TextInput
          label="創建者"
          placeholder="例如: admin"
          value={createdBy}
          onChange={(e) => {
            setCreatedBy(e.target.value);
            markDirty();
          }}
          onKeyDown={handleKeyDown}
          size="sm"
        />
        <TextInput
          label="更新者"
          placeholder="例如: admin"
          value={updatedBy}
          onChange={(e) => {
            setUpdatedBy(e.target.value);
            markDirty();
          }}
          onKeyDown={handleKeyDown}
          size="sm"
        />
      </Group>

      {/* 操作 */}
      {!hideButtons && (
        <Group gap="xs" justify="flex-end">
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
    </Stack>
  );
}
