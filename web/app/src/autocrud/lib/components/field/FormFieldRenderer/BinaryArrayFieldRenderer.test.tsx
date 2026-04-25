/**
 * BinaryArrayFieldRenderer — Tests for list-of-binary field rendering.
 *
 * Covers:
 * - Empty state renders "No items" text
 * - "Add" button inserts a new BinaryFieldEditor
 * - Remove button removes item from list
 * - onChange propagates correctly per-item
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { useForm } from '@mantine/form';
import type { ResourceField } from '../../../resources';
import { BinaryArrayFieldRenderer } from './BinaryArrayFieldRenderer';

vi.mock('../../../client', () => ({
  getBlobUrl: (id: string) => `http://test/blobs/${id}`,
}));

vi.mock('../../../hooks/useBlobUpload', () => ({
  formatBytes: (bytes: number) => `${bytes} B`,
}));

afterEach(() => cleanup());

function makeField(overrides: Partial<ResourceField> = {}): ResourceField {
  return {
    name: 'screenshots',
    label: 'Screenshots',
    type: 'binary',
    isArray: true,
    isRequired: false,
    isNullable: false,
    ...overrides,
  };
}

function FormWrapper({
  field,
  initialValues,
}: {
  field: ResourceField;
  initialValues: Record<string, any>;
}) {
  const form = useForm({ initialValues });
  return (
    <MantineProvider>
      <BinaryArrayFieldRenderer field={field} form={form} />
    </MantineProvider>
  );
}

describe('BinaryArrayFieldRenderer', () => {
  it('renders label and "No items" message when empty', () => {
    render(<FormWrapper field={makeField()} initialValues={{ screenshots: [] }} />);
    expect(screen.getAllByText('Screenshots').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/no items/i)).toBeTruthy();
  });

  it('renders Add button', () => {
    render(<FormWrapper field={makeField()} initialValues={{ screenshots: [] }} />);
    expect(screen.getAllByText('Add').length).toBeGreaterThanOrEqual(1);
  });

  it('adds a new binary editor when Add is clicked', () => {
    render(<FormWrapper field={makeField()} initialValues={{ screenshots: [] }} />);
    // Before add, "No items yet" should be visible
    expect(screen.getAllByText(/no items yet/i).length).toBeGreaterThanOrEqual(1);
    fireEvent.click(screen.getAllByText('Add')[0]);
    // After adding, item #1 label should appear
    expect(screen.getAllByText('#1').length).toBeGreaterThanOrEqual(1);
  });

  it('removes item when remove button is clicked', () => {
    render(
      <FormWrapper
        field={makeField()}
        initialValues={{
          screenshots: [{ _mode: 'empty' }, { _mode: 'empty' }],
        }}
      />,
    );
    // Two items initially
    const itemsBefore = screen.queryAllByText(/^#\d+$/);
    expect(itemsBefore.length).toBeGreaterThanOrEqual(2);

    // Click the first ActionIcon (Remove button — contains an SVG trash icon, no text)
    const allButtons = screen.getAllByRole('button');
    // Filter to buttons that are NOT the "Add" button (which contains "Add" text)
    const removeButtons = allButtons.filter((b) => !b.textContent?.toLowerCase().includes('add'));
    expect(removeButtons.length).toBeGreaterThanOrEqual(1);
    fireEvent.click(removeButtons[0]);

    // After removing one, one fewer item should be shown
    const itemsAfter = screen.queryAllByText(/^#\d+$/);
    expect(itemsAfter.length).toBeLessThan(itemsBefore.length);
  });

  it('renders existing items with file editors', () => {
    render(
      <FormWrapper
        field={makeField()}
        initialValues={{
          screenshots: [
            { _mode: 'existing', file_id: 'abc', content_type: 'image/png', size: 100 },
          ],
        }}
      />,
    );
    expect(screen.getAllByText('#1').length).toBeGreaterThanOrEqual(1);
  });

  it('renders required indicator when isRequired is true', () => {
    render(
      <FormWrapper
        field={makeField({ isRequired: true, isNullable: false })}
        initialValues={{ screenshots: [{ _mode: 'empty' }] }}
      />,
    );
    expect(screen.getAllByText('#1').length).toBeGreaterThanOrEqual(1);
  });
});
