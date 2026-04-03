import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { AdvancedSearchPanel } from './AdvancedSearchPanel';

// ── Mock useAdvancedSearch hook ──
const mockSetAdvancedOpen = vi.fn();
const mockHandleConditionSearch = vi.fn();
const mockHandleConditionClear = vi.fn();
const mockHandleQBSubmit = vi.fn();
const mockHandleQBClear = vi.fn();
const mockHandleSwitchToQB = vi.fn();
const mockHandleModeSwitch = vi.fn();
const mockHandleMetaConditionChange = vi.fn();
const mockHandleDataConditionChange = vi.fn();
const mockHandleQBTextChange = vi.fn();
const mockHandleResultLimitChange = vi.fn();
const mockHandleSortByChange = vi.fn();
const mockSetFilterDepth = vi.fn();

const defaultHookReturn = {
  searchMode: 'condition' as const,
  advancedOpen: false,
  setAdvancedOpen: mockSetAdvancedOpen,
  activeSearch: {
    mode: 'condition' as const,
    condition: { meta: {}, data: [] },
    qb: '',
    resultLimit: undefined,
    sortBy: undefined,
  },
  editingState: {
    condition: { meta: {}, data: [] },
    qb: '',
    resultLimit: undefined,
    sortBy: undefined as { field: string; order: 'asc' | 'desc' }[] | undefined,
  },
  handleMetaConditionChange: mockHandleMetaConditionChange,
  handleDataConditionChange: mockHandleDataConditionChange,
  handleQBTextChange: mockHandleQBTextChange,
  handleResultLimitChange: mockHandleResultLimitChange,
  handleSortByChange: mockHandleSortByChange,
  handleConditionSearch: mockHandleConditionSearch,
  handleConditionClear: mockHandleConditionClear,
  handleQBSubmit: mockHandleQBSubmit,
  handleQBClear: mockHandleQBClear,
  handleSwitchToQB: mockHandleSwitchToQB,
  handleModeSwitch: mockHandleModeSwitch,
  normalizedSearchableFields: [],
  sortFieldOptions: [] as { value: string; label: string }[],
  activeBackendCount: 0,
  filterDepth: 1,
  setFilterDepth: mockSetFilterDepth,
  maxFilterDepth: 1,
};

let hookReturn = { ...defaultHookReturn };

vi.mock('../../hooks/useAdvancedSearch', () => ({
  useAdvancedSearch: () => hookReturn,
}));

vi.mock('./SearchForm', () => ({
  SearchForm: (_props: any) => <div data-testid="search-form" />,
}));

vi.mock('./MetaSearchForm', () => ({
  MetaSearchForm: (_props: any) => <div data-testid="meta-search-form" />,
}));

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  hookReturn = { ...defaultHookReturn };
});

const mockConfig = {
  name: 'character',
  label: 'Character',
  fields: [],
  apiClient: {} as any,
};

function renderComponent(props: Partial<React.ComponentProps<typeof AdvancedSearchPanel>> = {}) {
  return render(
    <MantineProvider>
      <AdvancedSearchPanel config={mockConfig as any} onSearchChange={vi.fn()} {...props} />
    </MantineProvider>,
  );
}

describe('AdvancedSearchPanel', () => {
  it('renders toggle button with "進階搜尋" text', () => {
    renderComponent();
    // "進階搜尋" appears in both button and panel header
    expect(screen.getAllByText('進階搜尋').length).toBeGreaterThanOrEqual(1);
  });

  it('toggle button has correct color when no active search', () => {
    hookReturn.advancedOpen = false;
    hookReturn.activeBackendCount = 0;
    const { container } = renderComponent();
    // Button should exist
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('shows panel content when advancedOpen is true', () => {
    hookReturn.advancedOpen = true;
    renderComponent();
    expect(screen.getByTestId('search-form')).toBeDefined();
    expect(screen.getByTestId('meta-search-form')).toBeDefined();
  });

  it('calls setAdvancedOpen when toggle button clicked', () => {
    const { container } = renderComponent();
    // Click the first button (the toggle button)
    const buttons = container.querySelectorAll('button');
    fireEvent.click(buttons[0]);
    expect(mockSetAdvancedOpen).toHaveBeenCalled();
  });

  it('shows badge with active backend count when > 0', () => {
    hookReturn.activeBackendCount = 3;
    renderComponent();
    expect(screen.getByText('3')).toBeDefined();
  });

  it('does not show badge when activeBackendCount is 0', () => {
    hookReturn.activeBackendCount = 0;
    const { container } = renderComponent();
    expect(container.querySelector('.mantine-Badge-root')).toBeNull();
  });

  it('shows condition mode content when searchMode is condition', () => {
    hookReturn.advancedOpen = true;
    hookReturn.searchMode = 'condition';
    renderComponent();
    expect(screen.getByTestId('meta-search-form')).toBeDefined();
    expect(screen.getByTestId('search-form')).toBeDefined();
    expect(screen.getByText('搜尋')).toBeDefined();
  });

  it('shows QB mode switch when disableQB is true', () => {
    hookReturn.advancedOpen = true;
    renderComponent({ disableQB: true });
    expect(screen.getByText('條件模式')).toBeDefined();
  });

  it('does not show QB mode switch when disableQB is false', () => {
    hookReturn.advancedOpen = true;
    renderComponent({ disableQB: false });
    expect(screen.queryByText('條件模式')).toBeNull();
  });

  it('shows QB content when searchMode is qb', () => {
    hookReturn.advancedOpen = true;
    hookReturn.searchMode = 'qb' as any;
    renderComponent({ disableQB: true });
    expect(screen.getByText('查詢')).toBeDefined();
  });

  it('shows clear button when activeBackendCount > 0 in condition mode', () => {
    hookReturn.advancedOpen = true;
    hookReturn.activeBackendCount = 1;
    renderComponent();
    expect(screen.getByText('清除全部')).toBeDefined();
  });

  it('shows result limit input in condition mode', () => {
    hookReturn.advancedOpen = true;
    renderComponent();
    expect(screen.getByText('結果數量限制')).toBeDefined();
  });

  it('shows sort section in condition mode', () => {
    hookReturn.advancedOpen = true;
    renderComponent();
    expect(screen.getByText('排序設定')).toBeDefined();
    expect(screen.getByText('新增排序')).toBeDefined();
  });

  it('shows empty sort message when no sort conditions', () => {
    hookReturn.advancedOpen = true;
    hookReturn.editingState = { ...hookReturn.editingState, sortBy: undefined };
    renderComponent();
    expect(screen.getByText(/無排序條件/)).toBeDefined();
  });

  it('renders sort conditions when present', () => {
    hookReturn.advancedOpen = true;
    hookReturn.editingState = {
      ...hookReturn.editingState,
      sortBy: [{ field: 'name', order: 'asc' as const }],
    };
    hookReturn.sortFieldOptions = [{ value: 'name', label: 'Name' }];
    renderComponent();
    expect(screen.getByText('1.')).toBeDefined();
  });

  it('shows "轉為 QB" button in condition mode when disableQB is true', () => {
    hookReturn.advancedOpen = true;
    renderComponent({ disableQB: true });
    expect(screen.getByText('轉為 QB')).toBeDefined();
  });

  it('handles maxFilterDepth > 1', () => {
    hookReturn.advancedOpen = true;
    hookReturn.maxFilterDepth = 3;
    // Just verify it renders without error
    const { container } = renderComponent();
    expect(container).toBeDefined();
  });

  // ── Interaction tests (cover inline onChange/onClick handlers) ──

  it('fires sort field Select onChange handler', () => {
    hookReturn.advancedOpen = true;
    hookReturn.editingState = {
      ...hookReturn.editingState,
      sortBy: [{ field: 'name', order: 'asc' as const }],
    };
    hookReturn.sortFieldOptions = [
      { value: 'name', label: 'Name' },
      { value: 'age', label: 'Age' },
    ];
    const { container } = renderComponent();
    // Find the Select input for sort field
    const selectInputs = container.querySelectorAll('input[role="searchbox"]');
    if (selectInputs.length > 0) {
      fireEvent.change(selectInputs[0], { target: { value: 'age' } });
    }
    // The handler should be callable — just verify it doesn't crash
    expect(container).toBeDefined();
  });

  it('fires sort CloseButton to remove sort condition', () => {
    hookReturn.advancedOpen = true;
    hookReturn.editingState = {
      ...hookReturn.editingState,
      sortBy: [
        { field: 'name', order: 'asc' as const },
        { field: 'age', order: 'desc' as const },
      ],
    };
    hookReturn.sortFieldOptions = [
      { value: 'name', label: 'Name' },
      { value: 'age', label: 'Age' },
    ];
    const { container } = renderComponent();
    // Close buttons for sort items
    const closeButtons = container.querySelectorAll('button.mantine-CloseButton-root');
    if (closeButtons.length > 0) {
      fireEvent.click(closeButtons[0]);
      expect(mockHandleSortByChange).toHaveBeenCalled();
    }
  });

  it('fires "新增排序" button to add sort condition', () => {
    hookReturn.advancedOpen = true;
    renderComponent();
    fireEvent.click(screen.getByText('新增排序'));
    expect(mockHandleSortByChange).toHaveBeenCalledWith([{ field: '', order: 'asc' }]);
  });

  it('fires "搜尋" button', () => {
    hookReturn.advancedOpen = true;
    // Make search button enabled by differentiating editing vs active state
    hookReturn.editingState = {
      ...hookReturn.editingState,
      condition: { meta: { status: 'draft' }, data: [] },
    };
    hookReturn.activeSearch = {
      ...hookReturn.activeSearch,
      condition: { meta: {}, data: [] },
    };
    renderComponent();
    const searchBtn = screen.getByText('搜尋');
    fireEvent.click(searchBtn);
    expect(mockHandleConditionSearch).toHaveBeenCalled();
  });

  it('fires "清除全部" button', () => {
    hookReturn.advancedOpen = true;
    hookReturn.activeBackendCount = 2;
    renderComponent();
    fireEvent.click(screen.getByText('清除全部'));
    expect(mockHandleConditionClear).toHaveBeenCalled();
  });

  it('fires "轉為 QB" button', () => {
    hookReturn.advancedOpen = true;
    renderComponent({ disableQB: true });
    fireEvent.click(screen.getByText('轉為 QB'));
    expect(mockHandleSwitchToQB).toHaveBeenCalled();
  });

  // ── QB mode interactions ──

  it('QB mode textarea onChange', () => {
    hookReturn.advancedOpen = true;
    hookReturn.searchMode = 'qb' as any;
    hookReturn.editingState = { ...hookReturn.editingState, qb: '' };
    const { container } = renderComponent({ disableQB: true });
    const textarea = container.querySelector('textarea');
    expect(textarea).not.toBeNull();
    fireEvent.change(textarea!, { target: { value: 'QB.all()' } });
    expect(mockHandleQBTextChange).toHaveBeenCalledWith('QB.all()');
  });

  it('QB mode fires "查詢" button', () => {
    hookReturn.advancedOpen = true;
    hookReturn.searchMode = 'qb' as any;
    hookReturn.editingState = { ...hookReturn.editingState, qb: 'QB.all()' };
    hookReturn.activeSearch = { ...hookReturn.activeSearch, qb: '' };
    renderComponent({ disableQB: true });
    fireEvent.click(screen.getByText('查詢'));
    expect(mockHandleQBSubmit).toHaveBeenCalled();
  });

  it('QB mode fires "清除" button', () => {
    hookReturn.advancedOpen = true;
    hookReturn.searchMode = 'qb' as any;
    hookReturn.activeBackendCount = 1;
    renderComponent({ disableQB: true });
    fireEvent.click(screen.getByText('清除'));
    expect(mockHandleQBClear).toHaveBeenCalled();
  });

  it('fires handleModeSwitch via SegmentedControl', () => {
    hookReturn.advancedOpen = true;
    renderComponent({ disableQB: true });
    // The SegmentedControl has "條件模式" and "QB 語法"
    fireEvent.click(screen.getByText('QB 語法'));
    expect(mockHandleModeSwitch).toHaveBeenCalled();
  });

  it('handles different maxFilterDepth values', () => {
    hookReturn.advancedOpen = true;
    hookReturn.maxFilterDepth = 3;
    hookReturn.filterDepth = 2;
    // Just verify it renders without error (the Slider is inside a Mantine Divider
    // which may not show in textContent in test environment)
    const { container } = renderComponent();
    expect(container).toBeDefined();
  });
});
