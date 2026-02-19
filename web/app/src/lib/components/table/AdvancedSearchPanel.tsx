/**
 * AdvancedSearchPanel — Server-side search panel extracted from ResourceTable.
 *
 * All state management, URL sync, and editing logic live in the
 * `useAdvancedSearch` hook. This component is a pure JSX shell.
 */

import {
  Group,
  Button,
  Stack,
  Text,
  Badge,
  Box,
  Divider,
  SegmentedControl,
  Textarea,
  NumberInput,
  Select,
  CloseButton,
  Collapse,
  Paper,
  Tooltip,
} from '@mantine/core';
import {
  IconPlus,
  IconSearch,
  IconX,
  IconFilterOff,
  IconChevronDown,
  IconChevronUp,
  IconDatabase,
  IconCode,
  IconArrowRight,
} from '@tabler/icons-react';
import type { ResourceConfig } from '../../resources';
import type { SearchableField } from './types';
import { SearchForm } from './SearchForm';
import { MetaSearchForm } from './MetaSearchForm';
import { useAdvancedSearch } from '../../hooks/useAdvancedSearch';
import type { ActiveSearchState } from './searchUtils';

// ---------------------------------------------------------------------------
// Re-export types for backwards compatibility
// ---------------------------------------------------------------------------

export type { ActiveSearchState } from './searchUtils';

export interface AdvancedSearchPanelProps {
  config: ResourceConfig;
  searchableFields?: SearchableField[];
  disableQB?: boolean;
  /** Called whenever the active (submitted) search state changes. */
  onSearchChange: (search: ActiveSearchState) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AdvancedSearchPanel({
  config,
  searchableFields,
  disableQB = true,
  onSearchChange,
}: AdvancedSearchPanelProps) {
  const {
    searchMode,
    advancedOpen,
    setAdvancedOpen,
    activeSearch,
    editingState,
    handleMetaConditionChange,
    handleDataConditionChange,
    handleQBTextChange,
    handleResultLimitChange,
    handleSortByChange,
    handleConditionSearch,
    handleConditionClear,
    handleQBSubmit,
    handleQBClear,
    handleSwitchToQB,
    handleModeSwitch,
    normalizedSearchableFields,
    sortFieldOptions,
    activeBackendCount,
  } = useAdvancedSearch({ config, searchableFields, disableQB, onSearchChange });

  // ---- Render ----
  return (
    <>
      {/* Toggle button */}
      <Tooltip label="從伺服器查詢更多資料" position="bottom">
        <Button
          variant={activeBackendCount > 0 ? 'light' : 'subtle'}
          color={activeBackendCount > 0 ? 'blue' : 'gray'}
          size="sm"
          leftSection={<IconDatabase size={16} />}
          rightSection={advancedOpen ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />}
          onClick={() => setAdvancedOpen((o) => !o)}
        >
          進階搜尋
          {activeBackendCount > 0 && (
            <Badge size="sm" ml={6} circle>
              {activeBackendCount}
            </Badge>
          )}
        </Button>
      </Tooltip>

      {/* Collapsible panel */}
      <Collapse in={advancedOpen}>
        <Paper p="md" withBorder radius="md" bg="gray.0">
          <Stack gap="md">
            {/* Header + mode switch */}
            <Group justify="space-between" align="center">
              <Group gap={6}>
                <IconDatabase size={16} color="var(--mantine-color-blue-6)" />
                <Text size="sm" fw={500}>
                  進階搜尋
                </Text>
                <Text size="xs" c="dimmed">
                  — 查詢結果由伺服器回傳
                </Text>
              </Group>
              {disableQB && (
                <SegmentedControl
                  size="xs"
                  value={searchMode}
                  onChange={handleModeSwitch}
                  data={[
                    { label: '條件模式', value: 'condition' },
                    { label: 'QB 語法', value: 'qb' },
                  ]}
                />
              )}
            </Group>

            {/* Condition mode */}
            <Box style={{ display: searchMode === 'condition' ? 'block' : 'none' }}>
              <MetaSearchForm
                onSubmit={handleConditionSearch}
                initialValues={editingState.condition.meta}
                hideButtons
                onChange={handleMetaConditionChange}
              />

              {normalizedSearchableFields.length > 0 && (
                <>
                  <Divider label="資料欄位篩選" labelPosition="center" my="sm" />
                  <SearchForm
                    fields={normalizedSearchableFields}
                    onSubmit={handleConditionSearch}
                    initialConditions={editingState.condition.data}
                    hideButtons
                    onChange={handleDataConditionChange}
                  />
                </>
              )}

              <Divider label="查詢選項" labelPosition="center" my="sm" />

              <NumberInput
                label="結果數量限制"
                description="限制後端返回的結果數量（空白 = 使用預設值）"
                placeholder="例如：100"
                value={editingState.resultLimit ?? ''}
                onChange={handleResultLimitChange}
                min={1}
                max={10000}
                size="sm"
                allowDecimal={false}
              />

              {/* Multi-sort */}
              <Box mt="md">
                <Group justify="space-between" mb="xs">
                  <Text size="sm" fw={500}>
                    排序設定
                  </Text>
                  <Button
                    size="xs"
                    variant="light"
                    leftSection={<IconPlus size={14} />}
                    onClick={() =>
                      handleSortByChange([
                        ...(editingState.sortBy || []),
                        { field: '', order: 'asc' },
                      ])
                    }
                  >
                    新增排序
                  </Button>
                </Group>
                <Text size="xs" c="dimmed" mb="sm">
                  後端排序（支援多層排序，優先度由上至下）
                </Text>
                {(!editingState.sortBy || editingState.sortBy.length === 0) && (
                  <Text size="xs" c="dimmed" ta="center" py="md">
                    無排序條件，點擊「新增排序」以開始
                  </Text>
                )}
                <Stack gap="xs">
                  {editingState.sortBy?.map((sort, index) => (
                    <Group key={index} gap="xs" wrap="nowrap">
                      <Text size="sm" c="dimmed" style={{ minWidth: '24px' }}>
                        {index + 1}.
                      </Text>
                      <Select
                        placeholder="選擇欄位"
                        value={sort.field ?? ''}
                        onChange={(value) => {
                          const newSortBy = [...(editingState.sortBy || [])];
                          newSortBy[index] = { ...newSortBy[index], field: value || '' };
                          handleSortByChange(newSortBy);
                        }}
                        data={sortFieldOptions}
                        size="sm"
                        style={{ flex: 1 }}
                        searchable
                      />
                      <SegmentedControl
                        value={sort.order ?? 'asc'}
                        onChange={(value) => {
                          const newSortBy = [...(editingState.sortBy || [])];
                          newSortBy[index] = {
                            ...newSortBy[index],
                            order: value as 'asc' | 'desc',
                          };
                          handleSortByChange(newSortBy);
                        }}
                        data={[
                          { label: '↑ 升序', value: 'asc' },
                          { label: '↓ 降序', value: 'desc' },
                        ]}
                        size="sm"
                        style={{ minWidth: '140px' }}
                      />
                      <CloseButton
                        size="md"
                        onClick={() => {
                          const newSortBy = editingState.sortBy?.filter((_, i) => i !== index);
                          handleSortByChange(
                            newSortBy && newSortBy.length > 0 ? newSortBy : undefined,
                          );
                        }}
                      />
                    </Group>
                  ))}
                </Stack>
              </Box>

              {/* Action buttons */}
              <Group gap="sm" justify="space-between" mt="md">
                {disableQB && (
                  <Tooltip label="將目前條件轉換為 QB 語法">
                    <Button
                      size="xs"
                      variant="subtle"
                      color="gray"
                      leftSection={<IconCode size={14} />}
                      rightSection={<IconArrowRight size={12} />}
                      onClick={handleSwitchToQB}
                    >
                      轉為 QB
                    </Button>
                  </Tooltip>
                )}
                <Group gap="xs" ml="auto">
                  {activeBackendCount > 0 && (
                    <Button
                      size="xs"
                      variant="subtle"
                      color="gray"
                      leftSection={<IconFilterOff size={14} />}
                      onClick={handleConditionClear}
                    >
                      清除全部
                    </Button>
                  )}
                  <Button
                    size="xs"
                    disabled={
                      JSON.stringify(editingState.condition) ===
                        JSON.stringify(activeSearch.condition) &&
                      editingState.resultLimit === activeSearch.resultLimit &&
                      JSON.stringify(editingState.sortBy) === JSON.stringify(activeSearch.sortBy) &&
                      activeSearch.mode === 'condition'
                    }
                    leftSection={<IconSearch size={14} />}
                    onClick={handleConditionSearch}
                  >
                    搜尋
                  </Button>
                </Group>
              </Group>
            </Box>

            {/* QB mode */}
            {searchMode === 'qb' && (
              <Stack gap="sm">
                <Divider label="QB 語法" labelPosition="center" />
                <Text size="xs" c="dimmed">
                  範例: QB["level"] {'>'} 50 & QB.created_time().gte(dt.datetime(2024, 1,
                  1)).order_by("-level", "name").limit(100) | 查全部: QB.all().limit(10)
                </Text>
                <Textarea
                  placeholder={'QB["level"] > 50.order_by(QB.created_time().desc()).limit(100)'}
                  value={editingState.qb ?? ''}
                  onChange={(e) => handleQBTextChange(e.currentTarget.value)}
                  minRows={3}
                  autosize
                  styles={{ input: { fontFamily: 'monospace' } }}
                />
                <Group gap="xs" justify="flex-end">
                  {activeBackendCount > 0 && (
                    <Button
                      size="xs"
                      variant="subtle"
                      color="gray"
                      leftSection={<IconX size={14} />}
                      onClick={handleQBClear}
                    >
                      清除
                    </Button>
                  )}
                  <Button
                    size="xs"
                    disabled={editingState.qb === activeSearch.qb && activeSearch.mode === 'qb'}
                    leftSection={<IconSearch size={14} />}
                    onClick={handleQBSubmit}
                  >
                    查詢
                  </Button>
                </Group>
              </Stack>
            )}
          </Stack>
        </Paper>
      </Collapse>
    </>
  );
}
