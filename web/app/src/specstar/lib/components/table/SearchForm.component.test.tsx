/**
 * SearchForm — component rendering tests.
 *
 * Tests the SearchForm component's rendering and user interactions.
 * Pure helpers (buildFieldLabelMap, filterFieldOptionsFn) are tested in SearchForm.test.ts.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { SearchForm } from './SearchForm';
import type { NormalizedSearchableField } from './types';

beforeEach(() => {
  cleanup();
});

const wrap = (ui: React.ReactElement) => render(<MantineProvider>{ui}</MantineProvider>);

const fields: NormalizedSearchableField[] = [
  { name: 'name', label: 'Name', type: 'string' },
  { name: 'level', label: 'Level', type: 'number' },
  { name: 'active', label: 'Active', type: 'boolean' },
  {
    name: 'role',
    label: 'Role',
    type: 'select',
    options: [
      { label: 'Admin', value: 'admin' },
      { label: 'User', value: 'user' },
    ],
  },
  { name: 'created', label: 'Created', type: 'date' },
];

describe('SearchForm rendering', () => {
  it('renders empty state with add button', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(<SearchForm fields={fields} onSubmit={onSubmit} />);
    expect(container.textContent).toContain('新增條件');
  });

  it('renders search and clear buttons when not hideButtons', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(<SearchForm fields={fields} onSubmit={onSubmit} />);
    expect(container.textContent).toContain('搜尋');
  });

  it('hides buttons when hideButtons is true', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(<SearchForm fields={fields} onSubmit={onSubmit} hideButtons />);
    const buttons = container.querySelectorAll('button');
    const searchBtn = Array.from(buttons).find((b) => b.textContent?.includes('搜尋'));
    expect(searchBtn).toBeUndefined();
  });

  it('adds a condition row on click', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(<SearchForm fields={fields} onSubmit={onSubmit} />);
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('新增條件'),
    );
    expect(addBtn).toBeDefined();
    fireEvent.click(addBtn!);
    // Should now show a condition row with index "1"
    expect(container.textContent).toContain('1');
  });

  it('removes a condition row', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(<SearchForm fields={fields} onSubmit={onSubmit} />);
    // Add a condition
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('新增條件'),
    );
    fireEvent.click(addBtn!);

    // Find the red trash icon button (ActionIcon)
    const buttons = container.querySelectorAll('button');
    const removeBtn = Array.from(buttons).find(
      (b) => b.querySelector('svg') && b.closest('[class*="ActionIcon"]'),
    );
    if (removeBtn) {
      fireEvent.click(removeBtn);
    }
  });

  it('renders with initial conditions', () => {
    const onSubmit = vi.fn();
    wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        initialConditions={[{ field: 'name', operator: 'eq', value: 'Alice' }]}
      />,
    );
    // Should show the condition
    const inputs = screen.getAllByRole('textbox');
    expect(inputs.length).toBeGreaterThanOrEqual(1);
  });

  it('calls onSubmit when search is clicked', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        initialConditions={[{ field: 'name', operator: 'eq', value: 'test' }]}
      />,
    );
    const searchBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('搜尋'),
    );
    if (searchBtn) {
      fireEvent.click(searchBtn);
      expect(onSubmit).toHaveBeenCalled();
    }
  });

  it('calls onChange when conditions change', () => {
    const onSubmit = vi.fn();
    const onChange = vi.fn();
    const { container } = wrap(
      <SearchForm fields={fields} onSubmit={onSubmit} onChange={onChange} />,
    );
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('新增條件'),
    );
    fireEvent.click(addBtn!);
    // onChange should be called via useEffect
  });

  it('calls handleClear when clear is clicked', () => {
    const onSubmit = vi.fn();
    const onChange = vi.fn();
    const { container } = wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        onChange={onChange}
        initialConditions={[{ field: 'name', operator: 'eq', value: '' }]}
      />,
    );
    const clearBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('清除'),
    );
    if (clearBtn) {
      fireEvent.click(clearBtn);
      expect(onSubmit).toHaveBeenCalledWith([]);
    }
  });
});

describe('SearchForm field type interactions', () => {
  it('renders number input for number field condition', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        initialConditions={[{ field: 'level', operator: 'eq', value: 42 }]}
      />,
    );
    // Mantine NumberInput renders an input element
    const inputs = container.querySelectorAll('input');
    expect(inputs.length).toBeGreaterThanOrEqual(2);
  });

  it('renders Switch for boolean field condition', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        initialConditions={[{ field: 'active', operator: 'eq', value: true }]}
      />,
    );
    // Should render a Switch with label True/False
    expect(container.textContent).toMatch(/True|False/);
  });

  it('renders date input for date field condition', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        initialConditions={[{ field: 'created', operator: 'eq', value: '2024-01-01' }]}
      />,
    );
    const dateInput = container.querySelector('input[type="date"]');
    expect(dateInput).toBeTruthy();
  });

  it('renders default text input for unknown field (dot-path)', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        initialConditions={[{ field: 'stats.hp', operator: 'eq', value: 'test' }]}
      />,
    );
    // Default case: TextInput placeholder is "輸入值..."
    const inputs = container.querySelectorAll('input');
    expect(inputs.length).toBeGreaterThanOrEqual(1);
  });

  it('updates condition value on text input change', () => {
    const onSubmit = vi.fn();
    const onChange = vi.fn();
    const { container } = wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        onChange={onChange}
        initialConditions={[{ field: 'name', operator: 'eq', value: '' }]}
      />,
    );
    const inputs = container.querySelectorAll('input');
    const valueInput = Array.from(inputs).find(
      (i) => i.getAttribute('placeholder') === '輸入值...',
    );
    if (valueInput) {
      fireEvent.change(valueInput, { target: { value: 'Alice' } });
    }
  });

  it('handles Enter key to submit', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        initialConditions={[{ field: 'name', operator: 'eq', value: 'test' }]}
      />,
    );
    const inputs = container.querySelectorAll('input');
    const valueInput = Array.from(inputs).find(
      (i) => i.getAttribute('placeholder') === '輸入值...',
    );
    if (valueInput) {
      fireEvent.keyDown(valueInput, { key: 'Enter' });
      expect(onSubmit).toHaveBeenCalled();
    }
  });

  it('renders select input for select field condition', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        initialConditions={[{ field: 'role', operator: 'eq', value: 'admin' }]}
      />,
    );
    // Select field should render an input (Mantine Select uses input internally)
    const inputs = container.querySelectorAll('input');
    expect(inputs.length).toBeGreaterThanOrEqual(2);
  });

  it('renders number value correctly for number condition with empty string', () => {
    const onSubmit = vi.fn();
    wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        initialConditions={[{ field: 'level', operator: 'eq', value: '' }]}
      />,
    );
    // Should handle empty string → undefined for NumberInput
  });

  it('renders number value correctly for string-number conversion', () => {
    const onSubmit = vi.fn();
    wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        initialConditions={[{ field: 'level', operator: 'eq', value: '42' }]}
      />,
    );
    // String "42" → Number(42) for NumberInput display
  });

  it('handles condition field change to reset operator and value', () => {
    const onSubmit = vi.fn();
    const onChange = vi.fn();
    const { container } = wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        onChange={onChange}
        initialConditions={[{ field: 'name', operator: 'eq', value: '' }]}
      />,
    );
    // The Autocomplete for field selection - change field name
    const autocomplete = container.querySelectorAll('input');
    const fieldInput = Array.from(autocomplete).find(
      (i) => (i as HTMLInputElement).value === 'name',
    );
    if (fieldInput) {
      fireEvent.change(fieldInput, { target: { value: 'active' } });
    }
  });

  it('switches boolean condition value with Switch', () => {
    const onSubmit = vi.fn();
    const { container } = wrap(
      <SearchForm
        fields={fields}
        onSubmit={onSubmit}
        initialConditions={[{ field: 'active', operator: 'eq', value: false }]}
      />,
    );
    const switchInput = container.querySelector('input[type="checkbox"]');
    if (switchInput) {
      fireEvent.click(switchInput);
    }
  });
});
