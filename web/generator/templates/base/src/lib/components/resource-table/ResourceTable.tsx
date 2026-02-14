/**
 * ResourceTable - Generic resource list table with server-side pagination and sorting
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useLocation } from '@tanstack/react-router';
import {
  Container,
  Title,
  Group,
  Button,
  Stack,
  Text,
  Tooltip,
  ActionIcon,
  TextInput,
  Alert,
  Collapse,
  Paper,
  Badge,
  Box,
  Code,
  Divider,
  SegmentedControl,
  Textarea,
  NumberInput,
  Select,
  CloseButton,
  Image,
} from '@mantine/core';
import {
  IconPlus,
  IconRefresh,
  IconSearch,
  IconX,
  IconAlertCircle,
  IconFilterOff,
  IconChevronDown,
  IconChevronUp,
  IconDatabase,
  IconCode,
  IconArrowRight,
  IconFileCode,
  IconPhoto,
  IconFile,
  IconMusic,
  IconVideo,
  IconFileText,
  IconFileZip,
} from '@tabler/icons-react';
import {
  MantineReactTable,
  useMantineReactTable,
  type MRT_ColumnDef,
  type MRT_PaginationState,
  type MRT_SortingState,
  type MRT_RowData,
} from 'mantine-react-table';
import type { FullResource } from '../../../types/api';
import { useResourceList } from '../../hooks/useResourceList';
import { formatTime } from '../TimeDisplay';
import { ResourceIdCell } from './ResourceIdCell';
import { RefLink, RefLinkList, RefRevisionLink, RefRevisionLinkList } from '../RefLink';
import { SearchForm } from './SearchForm';
import { MetaSearchForm } from './MetaSearchForm';
import type { ResourceTableProps, SearchCondition, MetaFilters, ColumnVariant } from './types';
import { conditionToQB, sortByToSorts } from './utils';

/** Size threshold (in bytes) below which images are shown as inline thumbnails in the table. */
const INLINE_IMAGE_MAX_SIZE = 512 * 1024; // 512 KB

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function getBlobUrl(fileId: string): string {
  return `${API_BASE_URL}/blobs/${fileId}`;
}

function isImageContentType(ct: string | undefined): boolean {
  return !!ct && ct.startsWith('image/');
}

function formatBinarySize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Return an appropriate icon component for a given MIME content type. */
function getContentTypeIcon(contentType: string | undefined, size = 16) {
  if (!contentType) return <IconFile size={size} />;
  if (contentType.startsWith('image/'))
    return <IconPhoto size={size} color="var(--mantine-color-teal-6)" />;
  if (contentType.startsWith('video/'))
    return <IconVideo size={size} color="var(--mantine-color-grape-6)" />;
  if (contentType.startsWith('audio/'))
    return <IconMusic size={size} color="var(--mantine-color-orange-6)" />;
  if (contentType.startsWith('text/'))
    return <IconFileText size={size} color="var(--mantine-color-blue-6)" />;
  if (contentType.includes('pdf'))
    return <IconFileText size={size} color="var(--mantine-color-red-6)" />;
  if (
    contentType.includes('zip') ||
    contentType.includes('tar') ||
    contentType.includes('gzip') ||
    contentType.includes('compressed')
  )
    return <IconFileZip size={size} color="var(--mantine-color-yellow-6)" />;
  if (
    contentType.includes('json') ||
    contentType.includes('xml') ||
    contentType.includes('javascript')
  )
    return <IconFileCode size={size} color="var(--mantine-color-violet-6)" />;
  return <IconFile size={size} />;
}

/**
 * Render a binary field value in the table.
 * Shows inline image thumbnail for small images, or icon + type + size for others.
 */
function renderBinaryCell(value: Record<string, unknown>): React.ReactNode {
  const fileId = value.file_id as string | undefined;
  const contentType = value.content_type as string | undefined;
  const size = (value.size as number) || 0;

  // For small images, show inline thumbnail
  if (fileId && isImageContentType(contentType) && size <= INLINE_IMAGE_MAX_SIZE) {
    const blobUrl = getBlobUrl(fileId);
    return (
      <Tooltip label={`${contentType} · ${formatBinarySize(size)}`} withArrow>
        <Image
          src={blobUrl}
          maw={80}
          mah={48}
          fit="contain"
          radius="sm"
          style={{ cursor: 'pointer' }}
        />
      </Tooltip>
    );
  }

  // Otherwise show icon + info
  const sizeStr = formatBinarySize(size);
  const label = contentType || 'File';

  return (
    <Tooltip
      label={fileId ? `${label} · ${sizeStr} — click to download` : `${label} · ${sizeStr}`}
      withArrow
    >
      <Group gap={4} wrap="nowrap" style={{ cursor: fileId ? 'pointer' : 'default' }}>
        {getContentTypeIcon(contentType, 16)}
        <Text size="xs" c="dimmed" truncate style={{ maxWidth: 120 }}>
          {sizeStr}
        </Text>
      </Group>
    </Tooltip>
  );
}

/**
 * Render an object value as a compact preview with hover tooltip showing full JSON.
 * Used automatically by ResourceTable when a cell value is a plain object.
 */
function renderObjectPreview(value: Record<string, unknown>): React.ReactNode {
  const keys = Object.keys(value);

  if (keys.length === 0) {
    return (
      <Text c="dimmed" size="sm">
        {'{}'}
      </Text>
    );
  }

  const firstKey = keys[0];
  const firstValue = value[firstKey];
  const previewText =
    keys.length === 1
      ? `${firstKey}: ${JSON.stringify(firstValue)}`
      : `${firstKey}: ${JSON.stringify(firstValue)}, +${keys.length - 1} more`;

  const shortPreview = previewText.length > 40 ? previewText.slice(0, 37) + '...' : previewText;

  return (
    <Tooltip
      label={
        <Code block style={{ maxWidth: '400px', maxHeight: '300px', overflow: 'auto' }}>
          {JSON.stringify(value, null, 2)}
        </Code>
      }
      position="bottom-start"
      withArrow
      withinPortal
    >
      <Group gap={4} wrap="nowrap" style={{ cursor: 'help' }}>
        <IconFileCode size={14} />
        <Text size="sm" style={{ fontFamily: 'monospace' }}>
          {shortPreview}
        </Text>
      </Group>
    </Tooltip>
  );
}

/**
 * Generic resource list table with server-side pagination and sorting
 *
 * @example
 * // 預設：顯示所有欄位
 * <ResourceTable config={config} basePath="/guilds" />
 *
 * @example
 * // 控制欄位順序
 * <ResourceTable config={config} basePath="/guilds" columns={{
 *   order: ['name', 'created_at', 'resource_id']
 * }} />
 *
 * @example
 * // 覆蓋特定欄位的顯示方式
 * <ResourceTable config={config} basePath="/guilds" columns={{
 *   overrides: {
 *     created_at: { variant: 'full-time', label: '建立時間' },
 *     resource_id: { hidden: true }
 *   }
 * }} />
 *
 * @example
 * // 顯示預設隱藏的 meta 欄位
 * <ResourceTable config={config} basePath="/guilds" columns={{
 *   overrides: {
 *     created_by: { hidden: false },           // 顯示建立者
 *     updated_by: { hidden: false },           // 顯示更新者
 *     current_revision_id: { hidden: false },  // 顯示版本 ID
 *     schema_version: { hidden: false },       // 顯示 Schema 版本
 *     is_deleted: { hidden: false }            // 顯示刪除狀態
 *   }
 * }} />
 *
 * @example
 * // 啟用後端篩選表單（label 預設為 name）
 * <ResourceTable
 *   config={config}
 *   basePath="/characters"
 *   searchableFields={[
 *     { name: 'level', type: 'number' },
 *     { name: 'class', label: '職業', type: 'select', options: [
 *       { label: '戰士', value: 'warrior' },
 *       { label: '法師', value: 'mage' }
 *     ]},
 *     { name: 'is_active', type: 'boolean' },
 *   ]}
 * />
 *
 * @example
 * // 停用 QB 語法搜尋
 * <ResourceTable config={config} basePath="/guilds" disableQB />
 */
export function ResourceTable<T extends MRT_RowData>({
  config,
  basePath,
  columns,
  searchableFields,
  disableQB = true,
}: ResourceTableProps<T>) {
  const navigate = useNavigate();
  const location = useLocation();
  const [pagination, setPagination] = useState<MRT_PaginationState>({ pageIndex: 0, pageSize: 20 });
  const [sorting, setSorting] = useState<MRT_SortingState>([]);

  // 即時篩選（client-side）- 只篩當前頁面已載入的資料
  const [globalFilter, setGlobalFilter] = useState('');

  // 進階搜尋（server-side）- 統一狀態管理
  const [searchMode, setSearchMode] = useState<'condition' | 'qb'>('condition');
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // 已提交的搜尋狀態（用於 API 查詢）
  const [activeSearch, setActiveSearch] = useState<{
    mode: 'condition' | 'qb';
    condition: { meta: MetaFilters; data: SearchCondition[] };
    qb: string;
    resultLimit?: number; // 後端返回結果數量限制
    sortBy?: { field: string; order: 'asc' | 'desc' }[]; // 後端排序
  }>({
    mode: 'condition',
    condition: { meta: {}, data: [] },
    qb: '',
    resultLimit: undefined,
    sortBy: undefined,
  });

  // 當前編輯中的狀態（未提交）
  const [editingState, setEditingState] = useState<{
    condition: { meta: MetaFilters; data: SearchCondition[] };
    qb: string;
    resultLimit?: number;
    sortBy?: { field: string; order: 'asc' | 'desc' }[];
  }>({
    condition: { meta: {}, data: [] },
    qb: '',
    resultLimit: undefined,
    sortBy: undefined,
  });

  // 用來追蹤上次的 pathname，檢測頁面切換
  const lastPathnameRef = useRef<string>(location.pathname);
  // 用來避免內部更新觸發循環
  const isInternalUpdate = useRef(false);

  // 從 URL 讀取搜尋參數（監聽整個 href 變化）
  useEffect(() => {
    // 檢測是否切換了頁面（pathname 變化）- 清空所有 state
    if (location.pathname !== lastPathnameRef.current) {
      lastPathnameRef.current = location.pathname;
      // 頁面切換時清空所有搜尋狀態
      setSearchMode('condition');
      setAdvancedOpen(false);
      setActiveSearch({
        mode: 'condition',
        condition: { meta: {}, data: [] },
        qb: '',
        resultLimit: undefined,
        sortBy: undefined,
      });
      setEditingState({
        condition: { meta: {}, data: [] },
        qb: '',
        resultLimit: undefined,
        sortBy: undefined,
      });
      setPagination((prev) => ({ ...prev, pageIndex: 0 }));
      return;
    }

    // 如果是內部更新觸發的，跳過
    if (isInternalUpdate.current) {
      isInternalUpdate.current = false;
      return;
    }

    // 用 location.href 取得完整的 search string
    const urlParams = new URLSearchParams(location.href.split('?')[1] || '');

    // QB 參數
    const qbFromUrl = urlParams.get('qb');

    // Meta 參數
    const metaFromUrl: MetaFilters = {};
    const cts = urlParams.get('created_time_start');
    const cte = urlParams.get('created_time_end');
    const uts = urlParams.get('updated_time_start');
    const ute = urlParams.get('updated_time_end');
    const cb = urlParams.get('created_by');
    const ub = urlParams.get('updated_by');
    if (cts) metaFromUrl.created_time_start = cts;
    if (cte) metaFromUrl.created_time_end = cte;
    if (uts) metaFromUrl.updated_time_start = uts;
    if (ute) metaFromUrl.updated_time_end = ute;
    if (cb) metaFromUrl.created_by = cb;
    if (ub) metaFromUrl.updated_by = ub;

    // data_conditions 參數
    const dcStr = urlParams.get('data_conditions');
    let parsedConditions: SearchCondition[] = [];
    if (dcStr) {
      try {
        const parsed = JSON.parse(dcStr) as {
          field_path: string;
          operator: string;
          value: unknown;
        }[];
        parsedConditions = parsed.map((c) => ({
          field: c.field_path,
          operator: c.operator,
          value: c.value ?? '', // 確保 value 不是 undefined
        })) as SearchCondition[];
      } catch {
        /* ignore parse error */
      }
    }

    // resultLimit 和 sortBy 參數
    const resultLimitStr = urlParams.get('result_limit');
    const resultLimit = resultLimitStr ? parseInt(resultLimitStr, 10) : undefined;

    const sortByStr = urlParams.get('sort_by');
    let sortBy: { field: string; order: 'asc' | 'desc' }[] | undefined;
    if (sortByStr) {
      try {
        sortBy = JSON.parse(sortByStr) as { field: string; order: 'asc' | 'desc' }[];
      } catch {
        /* ignore parse error */
      }
    }

    // 根據 URL 參數設定搜尋狀態
    const newActiveSearch = {
      mode: qbFromUrl ? ('qb' as const) : ('condition' as const),
      condition: { meta: metaFromUrl, data: parsedConditions },
      qb: qbFromUrl ?? '',
      resultLimit,
      sortBy,
    };
    setActiveSearch(newActiveSearch);
    setEditingState({
      condition: { meta: metaFromUrl, data: parsedConditions },
      qb: qbFromUrl ?? '',
      resultLimit,
      sortBy,
    });

    // 如果 URL 有 QB 參數，切換到 QB 模式
    if (qbFromUrl) {
      setSearchMode('qb');
    }

    // 有任何搜尋參數時展開進階搜尋面板
    const hasSearchParams =
      !!qbFromUrl || Object.keys(metaFromUrl).length > 0 || parsedConditions.length > 0;
    setAdvancedOpen(hasSearchParams);
  }, [location.href]);

  // 正規化 searchableFields - label 預設為 name
  const normalizedSearchableFields = useMemo(
    () => searchableFields?.map((f) => ({ ...f, label: f.label || f.name })) ?? [],
    [searchableFields],
  );

  // 排序選項：searchableFields（如果有定義）或所有欄位 + meta 欄位
  const sortFieldOptions = useMemo(() => {
    const dataFields =
      normalizedSearchableFields.length > 0 ? normalizedSearchableFields : config.fields;

    return [
      ...dataFields.map((f) => ({ value: f.name, label: f.label })),
      // Meta 欄位
      { value: 'created_time', label: '建立時間' },
      { value: 'updated_time', label: '更新時間' },
      { value: 'created_by', label: '建立者' },
      { value: 'updated_by', label: '更新者' },
    ];
  }, [normalizedSearchableFields, config.fields]);

  const params = useMemo(() => {
    const baseParams: Record<string, unknown> = {
      limit: pagination.pageSize,
      offset: pagination.pageIndex * pagination.pageSize,
    };

    // 根據 activeSearch 的模式設定參數
    if (activeSearch.mode === 'qb' && activeSearch.qb) {
      // QB 模式：只傳 qb 字串（limit 和 sorts 已包含在 QB 中）
      baseParams.qb = activeSearch.qb;
    } else {
      // Condition 模式：傳遞各別參數
      const { meta, data } = activeSearch.condition;

      // 後端結果數量限制（優先於 pagination.pageSize）
      if (activeSearch.resultLimit) {
        baseParams.limit = activeSearch.resultLimit;
      }

      // 後端排序（優先於前端 table sorting）
      if (activeSearch.sortBy && activeSearch.sortBy.length > 0) {
        const sortsStr = sortByToSorts(activeSearch.sortBy);
        if (sortsStr) {
          baseParams.sorts = sortsStr;
        }
      }

      // 後端篩選參數（data_conditions）
      if (data.length > 0) {
        const dataConditions = data.map((condition) => ({
          field_path: condition.field,
          operator: condition.operator,
          value: condition.value,
        }));
        baseParams.data_conditions = JSON.stringify(dataConditions);
      }

      // Meta 篩選參數
      if (meta.created_time_start) baseParams.created_time_start = meta.created_time_start;
      if (meta.created_time_end) baseParams.created_time_end = meta.created_time_end;
      if (meta.updated_time_start) baseParams.updated_time_start = meta.updated_time_start;
      if (meta.updated_time_end) baseParams.updated_time_end = meta.updated_time_end;
      if (meta.created_by) baseParams.created_bys = [meta.created_by];
      if (meta.updated_by) baseParams.updated_bys = [meta.updated_by];
    }

    return baseParams;
  }, [pagination.pageSize, pagination.pageIndex, activeSearch]);

  // 當搜尋參數變化時同步到 URL（使用 TanStack Router 的 navigate）
  useEffect(() => {
    // 建構 search params
    const searchParams: Record<string, string> = {};

    if (activeSearch.mode === 'qb' && activeSearch.qb) {
      searchParams.qb = activeSearch.qb;
    } else {
      const { meta, data } = activeSearch.condition;

      if (data.length > 0) {
        const dataConditions = data.map((c) => ({
          field_path: c.field,
          operator: c.operator,
          value: c.value,
        }));
        searchParams.data_conditions = JSON.stringify(dataConditions);
      }

      if (meta.created_time_start) searchParams.created_time_start = meta.created_time_start;
      if (meta.created_time_end) searchParams.created_time_end = meta.created_time_end;
      if (meta.updated_time_start) searchParams.updated_time_start = meta.updated_time_start;
      if (meta.updated_time_end) searchParams.updated_time_end = meta.updated_time_end;
      if (meta.created_by) searchParams.created_by = meta.created_by;
      if (meta.updated_by) searchParams.updated_by = meta.updated_by;
    }

    // 後端結果數量限制和排序（兩種模式通用）
    if (activeSearch.resultLimit) {
      searchParams.result_limit = String(activeSearch.resultLimit);
    }
    if (activeSearch.sortBy && activeSearch.sortBy.length > 0) {
      searchParams.sort_by = JSON.stringify(activeSearch.sortBy);
    }

    // 標記為內部更新，避免觸發從 URL 讀取的 useEffect
    isInternalUpdate.current = true;

    // 使用 TanStack Router 的 navigate 更新 URL
    navigate({
      to: location.pathname,
      search: searchParams,
      replace: true,
    });
  }, [activeSearch, navigate, location.pathname]);

  // 更新編輯中的 Meta 條件
  const handleMetaConditionChange = useCallback((filters: MetaFilters, _isDirty: boolean) => {
    setEditingState((prev) => ({
      ...prev,
      condition: { ...prev.condition, meta: filters },
    }));
  }, []);

  // 更新編輯中的 Data 條件
  const handleDataConditionChange = useCallback(
    (conditions: SearchCondition[], _isDirty: boolean) => {
      setEditingState((prev) => ({
        ...prev,
        condition: { ...prev.condition, data: conditions },
      }));
    },
    [],
  );

  // 更新編輯中的 QB 文字
  const handleQBTextChange = useCallback((text: string) => {
    setEditingState((prev) => ({
      ...prev,
      qb: text,
    }));
  }, []);

  // 更新結果數量限制
  const handleResultLimitChange = useCallback((value: number | string) => {
    const limit =
      typeof value === 'number' ? value : value === '' ? undefined : parseInt(value, 10);
    setEditingState((prev) => ({
      ...prev,
      resultLimit: limit,
    }));
  }, []);

  // 更新排序
  const handleSortByChange = useCallback(
    (sortBy: { field: string; order: 'asc' | 'desc' }[] | undefined) => {
      setEditingState((prev) => ({
        ...prev,
        sortBy,
      }));
    },
    [],
  );

  // Condition 模式搜尋（提交編輯狀態）
  const handleConditionSearch = useCallback(() => {
    setActiveSearch({
      mode: 'condition',
      condition: editingState.condition,
      qb: '',
      resultLimit: editingState.resultLimit,
      sortBy: editingState.sortBy,
    });
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [editingState]);

  // Condition 模式清除
  const handleConditionClear = useCallback(() => {
    const emptyState = {
      condition: { meta: {}, data: [] },
      qb: '',
      resultLimit: undefined,
      sortBy: undefined,
    };
    setEditingState(emptyState);
    setActiveSearch({
      mode: 'condition',
      ...emptyState,
    });
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, []);

  // QB 模式搜尋（提交編輯狀態）
  const handleQBSubmit = useCallback(() => {
    setActiveSearch({
      mode: 'qb',
      condition: { meta: {}, data: [] },
      qb: editingState.qb,
      resultLimit: editingState.resultLimit,
      sortBy: editingState.sortBy,
    });
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [editingState]);

  // QB 模式清除
  const handleQBClear = useCallback(() => {
    const emptyState = {
      condition: { meta: {}, data: [] },
      qb: '',
      resultLimit: undefined,
      sortBy: undefined,
    };
    setEditingState(emptyState);
    setActiveSearch({
      mode: 'qb',
      ...emptyState,
    });
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, []);

  // 「轉為 QB」按鈕 - 從當前條件轉換
  const handleSwitchToQB = useCallback(() => {
    const qb = conditionToQB(
      editingState.condition.meta,
      editingState.condition.data,
      editingState.resultLimit,
      editingState.sortBy,
    );
    setEditingState((prev) => ({
      ...prev,
      qb,
    }));
    setSearchMode('qb');
  }, [editingState.condition, editingState.resultLimit, editingState.sortBy]);

  // 模式切換（用於 SegmentedControl）- 保持編輯狀態
  const handleModeSwitch = useCallback((value: string) => {
    setSearchMode(value as 'condition' | 'qb');
  }, []);

  // 計算有效的搜尋條件數量
  const activeBackendCount = useMemo(() => {
    if (activeSearch.mode === 'qb') {
      return activeSearch.qb ? 1 : 0;
    }
    return activeSearch.condition.data.length + Object.keys(activeSearch.condition.meta).length;
  }, [activeSearch]);

  const { data, total, loading, error, refresh } = useResourceList(config, params);

  const tableColumns = useMemo<MRT_ColumnDef<FullResource<T>, unknown>[]>(() => {
    // Helper function to render cell based on variant
    const renderCell = (variant: ColumnVariant, value: unknown): React.ReactNode => {
      if (value == null) return '';

      switch (variant) {
        case 'string':
          return String(value);
        case 'relative-time':
          return formatTime(String(value), 'relative');
        case 'full-time':
          return formatTime(String(value), 'full');
        case 'short-time':
          return formatTime(String(value), 'short');
        case 'date':
          return formatTime(String(value), 'date');
        case 'boolean':
          return value ? '✅' : '❌';
        case 'array':
          if (Array.isArray(value)) {
            if (value.length === 0)
              return (
                <Text c="dimmed" size="sm">
                  []
                </Text>
              );
            if (typeof value[0] === 'object' && value[0] !== null) {
              return renderObjectPreview({ [`${value.length} items`]: value } as Record<
                string,
                unknown
              >);
            }
            return value.join(', ');
          }
          return String(value);
        case 'json':
          if (typeof value === 'object' && value !== null) {
            return renderObjectPreview(value as Record<string, unknown>);
          }
          return String(value);
        case 'auto':
        default:
          // Auto detection
          if (typeof value === 'boolean') return value ? '✅' : '❌';
          if (Array.isArray(value)) {
            if (value.length === 0)
              return (
                <Text c="dimmed" size="sm">
                  []
                </Text>
              );
            if (value.length > 0 && typeof value[0] === 'object' && value[0] !== null) {
              return renderObjectPreview({ [`${value.length} items`]: value } as Record<
                string,
                unknown
              >);
            }
            return value.join(', ');
          }
          if (typeof value === 'object') {
            // Binary type detection
            const obj = value as Record<string, unknown>;
            if ('file_id' in obj && 'size' in obj) {
              return renderBinaryCell(obj);
            }
            return renderObjectPreview(obj);
          }
          if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)) {
            return formatTime(value, 'relative');
          }
          return String(value);
      }
    };

    // Build column definitions with default settings
    interface ColumnDef {
      id: string;
      header: string;
      accessorFn: (row: FullResource<T>) => unknown;
      size?: number;
      variant?: ColumnVariant;
      defaultHidden?: boolean;
      customRender?: (value: unknown) => React.ReactNode;
    }

    const allColumns: ColumnDef[] = [
      {
        id: 'resource_id',
        header: 'Resource ID',
        accessorFn: (row) => row?.meta?.resource_id,
        size: 180,
        variant: 'string',
        customRender: (value) => <ResourceIdCell rid={String(value)} />,
      },
    ];

    // Add data fields
    for (const field of config.fields) {
      if (field.variant?.type === 'json') continue;

      // Binary fields get a custom renderer with icon/thumbnail
      if (field.type === 'binary') {
        allColumns.push({
          id: field.name,
          header: field.label,
          accessorFn: (row) => {
            const parts = field.name.split('.');
            let val: any = row?.data;
            for (const p of parts) val = val?.[p];
            return val;
          },
          size: 120,
          variant: 'auto',
          customRender: (value) => {
            if (value && typeof value === 'object' && 'file_id' in (value as any)) {
              return renderBinaryCell(value as Record<string, unknown>);
            }
            return (
              <Text c="dimmed" size="sm">
                —
              </Text>
            );
          },
        });
        continue;
      }

      let defaultVariant: ColumnVariant = 'auto';
      if (field.type === 'boolean') defaultVariant = 'boolean';
      else if (field.isArray) defaultVariant = 'array';
      else if (field.type === 'date' || field.variant?.type === 'date')
        defaultVariant = 'relative-time';

      // Ref fields get a custom render as RefLink (scalar) or RefLinkList (array)
      let refCustomRender: ((value: unknown) => React.ReactNode) | undefined;
      if (field.ref && field.ref.type === 'resource_id') {
        if (field.isArray) {
          refCustomRender = (value: unknown) => (
            <RefLinkList values={value as string[] | null} fieldRef={field.ref!} maxVisible={3} />
          );
        } else {
          refCustomRender = (value: unknown) => (
            <RefLink value={value as string | null} fieldRef={field.ref!} />
          );
        }
      } else if (field.ref && field.ref.type === 'revision_id') {
        if (field.isArray) {
          refCustomRender = (value: unknown) => (
            <RefRevisionLinkList
              values={value as string[] | null}
              fieldRef={field.ref!}
              maxVisible={3}
            />
          );
        } else {
          refCustomRender = (value: unknown) => (
            <RefRevisionLink value={value as string | null} fieldRef={field.ref!} />
          );
        }
      }

      allColumns.push({
        id: field.name,
        header: field.label,
        accessorFn: (row) => {
          // Support nested paths like 'payload.event_type'
          const parts = field.name.split('.');
          let val: any = row?.data;
          for (const p of parts) {
            val = val?.[p];
          }
          return val;
        },
        variant: defaultVariant,
        ...(refCustomRender ? { customRender: refCustomRender } : {}),
      });
    }

    // Add metadata columns (all available, some hidden by default)
    allColumns.push(
      {
        id: 'current_revision_id',
        header: 'Revision ID',
        accessorFn: (row) => row?.meta?.current_revision_id,
        variant: 'string',
        defaultHidden: true,
        customRender: (value) => <ResourceIdCell rid={String(value)} />,
      },
      {
        id: 'schema_version',
        header: 'Schema Version',
        accessorFn: (row) => row?.meta?.schema_version,
        variant: 'string',
        defaultHidden: true, // 預設隱藏
      },
      {
        id: 'is_deleted',
        header: 'Deleted',
        accessorFn: (row) => row?.meta?.is_deleted,
        variant: 'boolean',
        defaultHidden: true, // 預設隱藏
      },
      {
        id: 'created_time',
        header: 'Created',
        accessorFn: (row) => row?.meta?.created_time,
        variant: 'relative-time',
        defaultHidden: false, // 預設顯示
      },
      {
        id: 'created_by',
        header: 'Created By',
        accessorFn: (row) => row?.meta?.created_by,
        variant: 'string',
        defaultHidden: true, // 預設隱藏
      },
      {
        id: 'updated_time',
        header: 'Updated',
        accessorFn: (row) => row?.meta?.updated_time,
        variant: 'relative-time',
        defaultHidden: false, // 預設顯示
      },
      {
        id: 'updated_by',
        header: 'Updated By',
        accessorFn: (row) => row?.meta?.updated_by,
        variant: 'string',
        defaultHidden: true, // 預設隱藏
      },
    );

    // Apply overrides
    const overrides = columns?.overrides ?? {};
    const processedColumns = allColumns.map((col) => {
      const override = overrides[col.id];

      // 決定是否隱藏：override.hidden > defaultHidden > false
      const hidden =
        override?.hidden !== undefined ? override.hidden : (col.defaultHidden ?? false);

      return {
        ...col,
        header: override?.label ?? col.header,
        size: override?.size ?? col.size,
        variant: override?.variant ?? col.variant,
        hidden,
        customRender: override?.render ?? col.customRender, // 保留原本的 customRender
      };
    });

    // Apply ordering
    let orderedColumns = processedColumns;
    if (columns?.order) {
      const orderMap = new Map(columns.order.map((id, idx) => [id, idx]));
      orderedColumns = processedColumns.sort((a, b) => {
        const aOrder = orderMap.get(a.id) ?? Infinity;
        const bOrder = orderMap.get(b.id) ?? Infinity;
        return aOrder - bOrder;
      });
    }

    // Filter hidden columns and convert to MRT format
    return orderedColumns
      .filter((col) => !col.hidden)
      .map((col) => ({
        id: col.id,
        header: col.header,
        accessorFn: col.accessorFn,
        size: col.size,
        Cell: ({ cell }) => {
          const value = cell.getValue();
          // 優先使用自訂 render 函數
          if (col.customRender) {
            return col.customRender(value);
          }
          // 否則使用 variant
          return renderCell(col.variant ?? 'auto', value);
        },
      }));
  }, [config.fields, columns]);

  const table = useMantineReactTable({
    columns: tableColumns,
    data,
    manualPagination: true,
    rowCount: total,
    enableGlobalFilter: true,
    state: { isLoading: loading, pagination, sorting, globalFilter },
    onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    mantineTableBodyRowProps: ({ row }) => ({
      onClick: () =>
        navigate({
          to: `${basePath}/$resourceId`,
          params: { resourceId: row.original?.meta?.resource_id ?? '' },
        }),
      style: { cursor: 'pointer' },
    }),
    initialState: { density: 'xs' },
  });

  return (
    <Container size="xl" py="xl">
      <Stack gap="md">
        <Group justify="space-between">
          <div>
            <Title order={2}>{config.label}</Title>
            <Text c="dimmed" size="sm">
              {total} total resources
            </Text>
          </div>
          <Group>
            <Button variant="light" leftSection={<IconRefresh size={16} />} onClick={refresh}>
              Refresh
            </Button>
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={() => navigate({ to: `${basePath}/create` })}
            >
              Create
            </Button>
          </Group>
        </Group>

        {/* 即時篩選 - 只篩當前頁面的資料 */}
        <Group gap="xs" align="center">
          <TextInput
            placeholder="在此頁中篩選..."
            value={globalFilter ?? ''}
            onChange={(e) => setGlobalFilter(e.currentTarget.value)}
            leftSection={<IconSearch size={16} />}
            rightSection={
              globalFilter ? (
                <ActionIcon variant="subtle" onClick={() => setGlobalFilter('')}>
                  <IconX size={16} />
                </ActionIcon>
              ) : null
            }
            style={{ flex: 1 }}
            size="sm"
          />
          <Tooltip label="從伺服器查詢更多資料" position="bottom">
            <Button
              variant={activeBackendCount > 0 ? 'light' : 'subtle'}
              color={activeBackendCount > 0 ? 'blue' : 'gray'}
              size="sm"
              leftSection={<IconDatabase size={16} />}
              rightSection={
                advancedOpen ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />
              }
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
        </Group>

        {/* 進階搜尋面板（後端查詢） */}
        <Collapse in={advancedOpen}>
          <Paper p="md" withBorder radius="md" bg="gray.0">
            <Stack gap="md">
              {/* 標題與模式切換 */}
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

              {/* 條件模式 - 使用 CSS 隱藏以保留表單狀態 */}
              <Box style={{ display: searchMode === 'condition' ? 'block' : 'none' }}>
                {/* Meta 篩選 */}
                <MetaSearchForm
                  onSubmit={handleConditionSearch}
                  initialValues={editingState.condition.meta}
                  hideButtons
                  onChange={handleMetaConditionChange}
                />

                {/* 資料欄位篩選 */}
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

                {/* 結果數量限制和排序（兩種模式通用） */}
                <Divider label="查詢選項" labelPosition="center" my="sm" />

                {/* 結果數量限制 */}
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

                {/* 多層排序 */}
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

                {/* 統一操作按鈕 */}
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
                        JSON.stringify(editingState.sortBy) ===
                          JSON.stringify(activeSearch.sortBy) &&
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

              {/* QB 模式 */}
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

        {/* 錯誤訊息 */}
        {error && (
          <Alert
            icon={<IconAlertCircle size={16} />}
            title="搜尋錯誤"
            color="red"
            withCloseButton
            onClose={handleQBClear}
          >
            {error.message}
          </Alert>
        )}

        <MantineReactTable table={table} />
      </Stack>
    </Container>
  );
}
