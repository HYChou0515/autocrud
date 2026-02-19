/**
 * useAdvancedSearch — Tests for pure helper functions + renderHook integration.
 *
 * Pure functions: parseResultLimit, buildConditionSearch, buildQBSearch,
 *   buildSortFieldOptions, normalizeSearchableFields
 *
 * Hook integration: useAdvancedSearch via renderHook
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  parseResultLimit,
  buildConditionSearch,
  buildQBSearch,
  buildSortFieldOptions,
  normalizeSearchableFields,
  useAdvancedSearch,
  type UseAdvancedSearchOptions,
} from './useAdvancedSearch';
import {
  EMPTY_ACTIVE_SEARCH,
  EMPTY_EDITING,
  type EditingState,
} from '../components/table/searchUtils';
import type { SearchableField } from '../components/table/types';
import type { ResourceConfig } from '../resources';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
let mockLocation = { pathname: '/test', href: '/test' };

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => mockLocation,
}));

vi.mock('../components/table/utils', () => ({
  conditionToQB: vi.fn(
    (meta: any, data: any, limit: any, sortBy: any) =>
      `QB_MOCK(${JSON.stringify({ meta, data, limit, sortBy })})`,
  ),
}));

function makeConfig(fields: { name: string; label: string }[] = []): ResourceConfig {
  return {
    name: 'test',
    label: 'Test',
    pluralLabel: 'Tests',
    schema: 'TestSchema',
    fields: fields.map((f) => ({
      name: f.name,
      label: f.label,
      type: 'string' as const,
      isArray: false,
      isRequired: false,
      isNullable: false,
    })),
    apiClient: {} as any,
  };
}

function defaultOpts(overrides: Partial<UseAdvancedSearchOptions> = {}): UseAdvancedSearchOptions {
  return {
    config: makeConfig(),
    onSearchChange: vi.fn(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// parseResultLimit
// ---------------------------------------------------------------------------

describe('parseResultLimit', () => {
  it('returns number as-is', () => {
    expect(parseResultLimit(42)).toBe(42);
  });

  it('returns 0 as-is', () => {
    expect(parseResultLimit(0)).toBe(0);
  });

  it('returns undefined for empty string', () => {
    expect(parseResultLimit('')).toBeUndefined();
  });

  it('parses numeric string to integer', () => {
    expect(parseResultLimit('100')).toBe(100);
  });

  it('parses string with leading zeros', () => {
    expect(parseResultLimit('007')).toBe(7);
  });

  it('returns NaN for non-numeric string', () => {
    expect(parseResultLimit('abc')).toBeNaN();
  });
});

// ---------------------------------------------------------------------------
// buildConditionSearch
// ---------------------------------------------------------------------------

describe('buildConditionSearch', () => {
  it('returns condition mode with empty editing state', () => {
    const result = buildConditionSearch(EMPTY_EDITING);
    expect(result.mode).toBe('condition');
    expect(result.condition).toEqual({ meta: {}, data: [] });
    expect(result.qb).toBe('');
    expect(result.resultLimit).toBeUndefined();
    expect(result.sortBy).toBeUndefined();
  });

  it('carries over editing state fields', () => {
    const editing: EditingState = {
      condition: {
        meta: { created_by: 'alice' },
        data: [{ field: 'level', operator: 'gte', value: 10 }],
      },
      qb: 'should be ignored',
      resultLimit: 50,
      sortBy: [{ field: 'name', order: 'asc' }],
    };
    const result = buildConditionSearch(editing);
    expect(result.mode).toBe('condition');
    expect(result.condition.meta.created_by).toBe('alice');
    expect(result.condition.data).toHaveLength(1);
    expect(result.qb).toBe(''); // always cleared in condition mode
    expect(result.resultLimit).toBe(50);
    expect(result.sortBy).toEqual([{ field: 'name', order: 'asc' }]);
  });
});

// ---------------------------------------------------------------------------
// buildQBSearch
// ---------------------------------------------------------------------------

describe('buildQBSearch', () => {
  it('returns qb mode with empty editing state', () => {
    const result = buildQBSearch(EMPTY_EDITING);
    expect(result.mode).toBe('qb');
    expect(result.condition).toEqual({ meta: {}, data: [] });
    expect(result.qb).toBe('');
    expect(result.resultLimit).toBeUndefined();
    expect(result.sortBy).toBeUndefined();
  });

  it('carries over qb text and options from editing', () => {
    const editing: EditingState = {
      condition: {
        meta: { created_by: 'alice' },
        data: [{ field: 'x', operator: 'eq', value: 1 }],
      },
      qb: 'QB.all().limit(5)',
      resultLimit: 200,
      sortBy: [{ field: 'hp', order: 'desc' }],
    };
    const result = buildQBSearch(editing);
    expect(result.mode).toBe('qb');
    expect(result.qb).toBe('QB.all().limit(5)');
    expect(result.resultLimit).toBe(200);
    expect(result.sortBy).toEqual([{ field: 'hp', order: 'desc' }]);
    // condition is always reset in qb mode
    expect(result.condition).toEqual({ meta: {}, data: [] });
  });
});

// ---------------------------------------------------------------------------
// buildSortFieldOptions
// ---------------------------------------------------------------------------

describe('buildSortFieldOptions', () => {
  const META_FIELDS = [
    { value: 'created_time', label: '建立時間' },
    { value: 'updated_time', label: '更新時間' },
    { value: 'created_by', label: '建立者' },
    { value: 'updated_by', label: '更新者' },
  ];

  it('uses normalizedFields when non-empty', () => {
    const normalized = [{ name: 'level', label: 'Level' }];
    const configFields = [
      { name: 'hp', label: 'HP' },
      { name: 'mp', label: 'MP' },
    ];
    const options = buildSortFieldOptions(normalized, configFields);
    expect(options[0]).toEqual({ value: 'level', label: 'Level' });
    // Should NOT include configFields
    expect(options.find((o) => o.value === 'hp')).toBeUndefined();
    // Should include meta fields
    expect(options.slice(-4)).toEqual(META_FIELDS);
  });

  it('falls back to configFields when normalizedFields is empty', () => {
    const configFields = [{ name: 'hp', label: 'HP' }];
    const options = buildSortFieldOptions([], configFields);
    expect(options[0]).toEqual({ value: 'hp', label: 'HP' });
    expect(options.slice(-4)).toEqual(META_FIELDS);
  });

  it('always appends exactly 4 meta fields', () => {
    const options = buildSortFieldOptions([], []);
    expect(options).toHaveLength(4);
    expect(options).toEqual(META_FIELDS);
  });

  it('preserves order of input fields', () => {
    const fields = [
      { name: 'c', label: 'C' },
      { name: 'a', label: 'A' },
      { name: 'b', label: 'B' },
    ];
    const options = buildSortFieldOptions(fields, []);
    expect(options[0].value).toBe('c');
    expect(options[1].value).toBe('a');
    expect(options[2].value).toBe('b');
  });
});

// ---------------------------------------------------------------------------
// normalizeSearchableFields
// ---------------------------------------------------------------------------

describe('normalizeSearchableFields', () => {
  it('returns empty array for undefined input', () => {
    expect(normalizeSearchableFields(undefined)).toEqual([]);
  });

  it('returns empty array for empty array', () => {
    expect(normalizeSearchableFields([])).toEqual([]);
  });

  it('defaults label to name when label is missing', () => {
    const fields: SearchableField[] = [{ name: 'level', type: 'number' }];
    const result = normalizeSearchableFields(fields);
    expect(result[0].label).toBe('level');
    expect(result[0].name).toBe('level');
  });

  it('preserves explicit label', () => {
    const fields: SearchableField[] = [{ name: 'level', label: '等級', type: 'number' }];
    const result = normalizeSearchableFields(fields);
    expect(result[0].label).toBe('等級');
  });

  it('preserves all other field properties', () => {
    const fields: SearchableField[] = [
      {
        name: 'class',
        label: '職業',
        type: 'select',
        operators: ['eq', 'ne'],
        options: [{ label: '戰士', value: 'warrior' }],
      },
    ];
    const result = normalizeSearchableFields(fields);
    expect(result[0].type).toBe('select');
    expect(result[0].operators).toEqual(['eq', 'ne']);
    expect(result[0].options).toEqual([{ label: '戰士', value: 'warrior' }]);
  });

  it('handles multiple fields', () => {
    const fields: SearchableField[] = [
      { name: 'a', type: 'string' },
      { name: 'b', label: 'B Label', type: 'number' },
      { name: 'c', type: 'boolean' },
    ];
    const result = normalizeSearchableFields(fields);
    expect(result).toHaveLength(3);
    expect(result[0].label).toBe('a'); // defaulted
    expect(result[1].label).toBe('B Label'); // preserved
    expect(result[2].label).toBe('c'); // defaulted
  });
});

// ===========================================================================
// renderHook integration tests for useAdvancedSearch
// ===========================================================================

describe('useAdvancedSearch (hook)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocation = { pathname: '/test', href: '/test' };
  });

  // ---- Initial state ---------------------------------------------------

  describe('initial state', () => {
    it('starts in condition mode with panel closed', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      expect(result.current.searchMode).toBe('condition');
      expect(result.current.advancedOpen).toBe(false);
    });

    it('starts with empty active search', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      expect(result.current.activeSearch).toEqual(EMPTY_ACTIVE_SEARCH);
    });

    it('starts with empty editing state', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      expect(result.current.editingState).toEqual(EMPTY_EDITING);
    });

    it('starts with activeBackendCount 0', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      expect(result.current.activeBackendCount).toBe(0);
    });

    it('calls onSearchChange on mount with empty search', () => {
      const onSearchChange = vi.fn();
      renderHook(() => useAdvancedSearch(defaultOpts({ onSearchChange })));
      expect(onSearchChange).toHaveBeenCalledWith(EMPTY_ACTIVE_SEARCH);
    });
  });

  // ---- Computed values ---------------------------------------------------

  describe('computed values', () => {
    it('normalizedSearchableFields defaults label to name', () => {
      const fields: SearchableField[] = [{ name: 'level', type: 'number' }];
      const { result } = renderHook(() =>
        useAdvancedSearch(defaultOpts({ searchableFields: fields })),
      );
      expect(result.current.normalizedSearchableFields).toEqual([
        { name: 'level', label: 'level', type: 'number' },
      ]);
    });

    it('sortFieldOptions uses normalizedSearchableFields when present', () => {
      const fields: SearchableField[] = [{ name: 'hp', label: 'HP', type: 'number' }];
      const { result } = renderHook(() =>
        useAdvancedSearch(defaultOpts({ searchableFields: fields })),
      );
      expect(result.current.sortFieldOptions[0]).toEqual({ value: 'hp', label: 'HP' });
      // 4 meta fields at the end
      expect(result.current.sortFieldOptions).toHaveLength(5);
    });

    it('sortFieldOptions falls back to config.fields when no searchableFields', () => {
      const config = makeConfig([{ name: 'wage', label: 'Wage' }]);
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts({ config })));
      expect(result.current.sortFieldOptions[0]).toEqual({ value: 'wage', label: 'Wage' });
    });
  });

  // ---- Editing callbacks -------------------------------------------------

  describe('editing callbacks', () => {
    it('handleMetaConditionChange updates meta filters', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      act(() => {
        result.current.handleMetaConditionChange({ created_by: 'bob' }, true);
      });
      expect(result.current.editingState.condition.meta).toEqual({ created_by: 'bob' });
    });

    it('handleDataConditionChange updates data conditions', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      const conds = [{ field: 'level', operator: 'gte', value: 5 }];
      act(() => {
        result.current.handleDataConditionChange(conds, true);
      });
      expect(result.current.editingState.condition.data).toEqual(conds);
    });

    it('handleQBTextChange updates QB text', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      act(() => {
        result.current.handleQBTextChange('QB.all()');
      });
      expect(result.current.editingState.qb).toBe('QB.all()');
    });

    it('handleResultLimitChange sets numeric limit', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      act(() => {
        result.current.handleResultLimitChange(25);
      });
      expect(result.current.editingState.resultLimit).toBe(25);
    });

    it('handleResultLimitChange clears limit for empty string', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      act(() => {
        result.current.handleResultLimitChange(10);
      });
      expect(result.current.editingState.resultLimit).toBe(10);
      act(() => {
        result.current.handleResultLimitChange('');
      });
      expect(result.current.editingState.resultLimit).toBeUndefined();
    });

    it('handleSortByChange updates sort config', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      const sortBy = [{ field: 'name', order: 'asc' as const }];
      act(() => {
        result.current.handleSortByChange(sortBy);
      });
      expect(result.current.editingState.sortBy).toEqual(sortBy);
    });

    it('handleSortByChange clears sort to undefined', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      act(() => {
        result.current.handleSortByChange([{ field: 'x', order: 'desc' }]);
      });
      act(() => {
        result.current.handleSortByChange(undefined);
      });
      expect(result.current.editingState.sortBy).toBeUndefined();
    });
  });

  // ---- Submit / Clear ----------------------------------------------------

  describe('submit and clear', () => {
    it('handleConditionSearch publishes condition-mode search', () => {
      const onSearchChange = vi.fn();
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts({ onSearchChange })));

      act(() => {
        result.current.handleMetaConditionChange({ created_by: 'alice' }, true);
      });
      act(() => {
        result.current.handleConditionSearch();
      });

      expect(result.current.activeSearch.mode).toBe('condition');
      expect(result.current.activeSearch.condition.meta).toEqual({ created_by: 'alice' });
      expect(result.current.activeSearch.qb).toBe('');
    });

    it('handleConditionClear resets all state', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));

      act(() => {
        result.current.handleMetaConditionChange({ created_by: 'x' }, true);
        result.current.handleConditionSearch();
      });
      act(() => {
        result.current.handleConditionClear();
      });

      expect(result.current.activeSearch).toEqual(EMPTY_ACTIVE_SEARCH);
      expect(result.current.editingState).toEqual(EMPTY_EDITING);
    });

    it('handleQBSubmit publishes qb-mode search', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));

      act(() => {
        result.current.handleQBTextChange('QB.all().limit(10)');
      });
      act(() => {
        result.current.handleQBSubmit();
      });

      expect(result.current.activeSearch.mode).toBe('qb');
      expect(result.current.activeSearch.qb).toBe('QB.all().limit(10)');
      expect(result.current.activeSearch.condition).toEqual({ meta: {}, data: [] });
    });

    it('handleQBClear resets editing and active search (qb mode)', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));

      act(() => {
        result.current.handleQBTextChange('something');
        result.current.handleQBSubmit();
      });
      act(() => {
        result.current.handleQBClear();
      });

      expect(result.current.activeSearch.mode).toBe('qb');
      expect(result.current.activeSearch.qb).toBe('');
      expect(result.current.editingState).toEqual(EMPTY_EDITING);
    });
  });

  // ---- Mode switching ----------------------------------------------------

  describe('mode switching', () => {
    it('handleModeSwitch changes searchMode', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      expect(result.current.searchMode).toBe('condition');

      act(() => {
        result.current.handleModeSwitch('qb');
      });
      expect(result.current.searchMode).toBe('qb');

      act(() => {
        result.current.handleModeSwitch('condition');
      });
      expect(result.current.searchMode).toBe('condition');
    });

    it('handleSwitchToQB converts conditions to QB text and switches', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));

      act(() => {
        result.current.handleMetaConditionChange({ created_by: 'alice' }, true);
      });
      act(() => {
        result.current.handleSwitchToQB();
      });

      expect(result.current.searchMode).toBe('qb');
      // conditionToQB mock returns a stringified version
      expect(result.current.editingState.qb).toContain('QB_MOCK');
      expect(result.current.editingState.qb).toContain('alice');
    });
  });

  // ---- setAdvancedOpen ---------------------------------------------------

  describe('panel toggle', () => {
    it('setAdvancedOpen toggles panel visibility', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));
      expect(result.current.advancedOpen).toBe(false);

      act(() => {
        result.current.setAdvancedOpen(true);
      });
      expect(result.current.advancedOpen).toBe(true);

      act(() => {
        result.current.setAdvancedOpen(false);
      });
      expect(result.current.advancedOpen).toBe(false);
    });
  });

  // ---- activeBackendCount ------------------------------------------------

  describe('activeBackendCount', () => {
    it('reflects submitted conditions', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));

      // Initially 0
      expect(result.current.activeBackendCount).toBe(0);

      act(() => {
        result.current.handleMetaConditionChange({ created_by: 'x' }, true);
      });
      act(() => {
        result.current.handleConditionSearch();
      });

      // 1 meta condition active
      expect(result.current.activeBackendCount).toBeGreaterThan(0);
    });
  });

  // ---- State → URL sync --------------------------------------------------

  describe('URL sync', () => {
    it('calls navigate when activeSearch changes', () => {
      const { result } = renderHook(() => useAdvancedSearch(defaultOpts()));

      act(() => {
        result.current.handleMetaConditionChange({ created_by: 'sync-test' }, true);
      });
      act(() => {
        result.current.handleConditionSearch();
      });

      // navigate should be called with search params
      expect(mockNavigate).toHaveBeenCalled();
      const lastCall = mockNavigate.mock.calls[mockNavigate.mock.calls.length - 1][0];
      expect(lastCall).toHaveProperty('replace', true);
      expect(lastCall).toHaveProperty('to', '/test');
    });
  });
});
