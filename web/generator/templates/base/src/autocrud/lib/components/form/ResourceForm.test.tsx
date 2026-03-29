/**
 * ResourceForm — Regression tests for submit button loading state.
 *
 * Covers:
 * - Submit button does NOT have loading state when submitting is false/undefined
 * - Submit button HAS loading state when submitting=true (form mode)
 * - Submit button HAS loading state when submitting=true (JSON mode)
 * - Both Cancel and Submit buttons rendered correctly
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import React from 'react';

// ---------------------------------------------------------------------------
// Mocks — vi.hoisted ensures variables are available during module mock hoisting
// ---------------------------------------------------------------------------

const { mockUseResourceFormReturn } = vi.hoisted(() => {
  const _mockForm = {
    onSubmit: (_handler: any) => (e: any) => {
      e?.preventDefault?.();
    },
    getValues: () => ({}),
    getInputProps: () => ({}),
    setFieldError: vi.fn(),
  };

  const mockUseResourceFormReturn = {
    form: _mockForm,
    editMode: 'form' as const,
    jsonText: '',
    setJsonText: vi.fn(),
    jsonError: null,
    setJsonError: vi.fn(),
    handleSwitchToJson: vi.fn(),
    handleSwitchToForm: vi.fn(),
    handleJsonSubmit: vi.fn(),
    maxAvailableDepth: 1,
    formDepth: 1,
    setFormDepth: vi.fn(),
    visibleFields: [] as any[],
    collapsedGroups: [] as any[],
    simpleUnionTypes: {} as Record<string, string>,
    setSimpleUnionTypes: vi.fn(),
    handleSubmit: vi.fn(),
    blobUploadState: {
      isUploading: false,
      currentFieldName: null,
      currentFileName: null,
      totalFiles: 0,
      completedFiles: 0,
      progress: { loaded: 0, total: 0, percent: 0, elapsed: 0, eta: null },
      error: null,
    },
    cancelBlobUpload: vi.fn(),
  };

  return { mockUseResourceFormReturn };
});

vi.mock('./useResourceForm', () => ({
  useResourceForm: vi.fn().mockReturnValue(mockUseResourceFormReturn),
}));

vi.mock('../field/FormFieldRenderer', () => ({
  FieldRenderer: () => null,
}));

vi.mock('@/autocrud/lib/utils/formUtils', () => ({
  getByPath: vi.fn(),
  collapseFieldToJson: vi.fn().mockReturnValue('{}'),
  groupFieldsByParent: vi.fn().mockReturnValue([]),
}));

vi.mock('../../hooks/useBlobUpload', () => ({
  formatBytes: (bytes: number) => `${bytes}B`,
  formatDuration: (s: number | null) => (s == null ? '--' : `${Math.round(s)}s`),
}));

import { ResourceForm } from './ResourceForm';
import { useResourceForm } from './useResourceForm';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeConfig(): any {
  return {
    name: 'test',
    label: 'Test',
    fields: [],
    apiClient: {},
  };
}

function renderForm(props: Partial<React.ComponentProps<typeof ResourceForm>> = {}) {
  return render(
    <MantineProvider>
      <ResourceForm config={makeConfig()} onSubmit={vi.fn()} submitLabel="Create" {...props} />
    </MantineProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ResourceForm submit button loading state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset to form mode
    (useResourceForm as any).mockReturnValue({
      ...mockUseResourceFormReturn,
      editMode: 'form',
    });
  });

  it('submit button does NOT have loading when submitting is undefined', () => {
    const { container } = renderForm();
    const btn = container.querySelector('button[type="submit"]')!;
    expect(btn).toBeTruthy();
    expect(btn.hasAttribute('data-loading')).toBe(false);
  });

  it('submit button does NOT have loading when submitting=false', () => {
    const { container } = renderForm({ submitting: false });
    const btn = container.querySelector('button[type="submit"]')!;
    expect(btn).toBeTruthy();
    expect(btn.hasAttribute('data-loading')).toBe(false);
  });

  it('submit button HAS loading state when submitting=true (form mode)', () => {
    const { container } = renderForm({ submitting: true });
    const btn = container.querySelector('button[type="submit"]')!;
    expect(btn).toBeTruthy();
    expect(btn.hasAttribute('data-loading')).toBe(true);
  });

  it('submit button HAS loading state when submitting=true (JSON mode)', () => {
    (useResourceForm as any).mockReturnValue({
      ...mockUseResourceFormReturn,
      editMode: 'json',
      jsonText: '{}',
    });

    const { container } = renderForm({ submitting: true });
    // In JSON mode, submit is a regular button (not type=submit)
    const buttons = container.querySelectorAll('button');
    const btn = Array.from(buttons).find(
      (b) => b.textContent === 'Create' && b.getAttribute('type') !== 'submit',
    )!;
    expect(btn).toBeTruthy();
    expect(btn.hasAttribute('data-loading')).toBe(true);
  });
});

// ===========================================================================
// Blob upload progress display
// ===========================================================================
describe('ResourceForm blob upload progress', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows upload progress bar when blob upload is in progress', () => {
    (useResourceForm as any).mockReturnValue({
      ...mockUseResourceFormReturn,
      editMode: 'form',
      blobUploadState: {
        isUploading: true,
        currentFieldName: 'avatar',
        currentFileName: 'photo.jpg',
        totalFiles: 2,
        completedFiles: 1,
        progress: { loaded: 5000, total: 10000, percent: 50, elapsed: 5, eta: 5 },
        error: null,
      },
    });

    const { container, getByText } = renderForm();
    // Progress header
    expect(getByText('Uploading files (1/2)')).toBeTruthy();
    // Current file name
    expect(getByText(/photo\.jpg/)).toBeTruthy();
    // Elapsed time
    expect(getByText(/Elapsed: 5s/)).toBeTruthy();
    // ETA
    expect(getByText(/ETA: 5s/)).toBeTruthy();
    // Submit button should be loading
    const btn = container.querySelector('button[type="submit"]')!;
    expect(btn.hasAttribute('data-loading')).toBe(true);
  });

  it('shows cancel button during upload', () => {
    (useResourceForm as any).mockReturnValue({
      ...mockUseResourceFormReturn,
      editMode: 'form',
      blobUploadState: {
        isUploading: true,
        currentFieldName: 'file',
        currentFileName: 'data.bin',
        totalFiles: 1,
        completedFiles: 0,
        progress: { loaded: 100, total: 1000, percent: 10, elapsed: 1, eta: 9 },
        error: null,
      },
    });

    const { getAllByText } = renderForm();
    const cancelBtns = getAllByText('Cancel');
    // At least one cancel button should be rendered during blob upload
    expect(cancelBtns.length).toBeGreaterThanOrEqual(1);
  });

  it('shows error alert when blob upload fails', () => {
    (useResourceForm as any).mockReturnValue({
      ...mockUseResourceFormReturn,
      editMode: 'form',
      blobUploadState: {
        isUploading: false,
        currentFieldName: null,
        currentFileName: null,
        totalFiles: 1,
        completedFiles: 0,
        progress: { loaded: 0, total: 1000, percent: 0, elapsed: 2, eta: null },
        error: 'Network error',
      },
    });

    const { getByText } = renderForm();
    expect(getByText(/Network error/)).toBeTruthy();
  });

  it('does NOT show progress bar when no upload is happening', () => {
    (useResourceForm as any).mockReturnValue({
      ...mockUseResourceFormReturn,
      editMode: 'form',
      blobUploadState: {
        isUploading: false,
        currentFieldName: null,
        currentFileName: null,
        totalFiles: 0,
        completedFiles: 0,
        progress: { loaded: 0, total: 0, percent: 0, elapsed: 0, eta: null },
        error: null,
      },
    });

    const { container } = renderForm();
    // Should not find the progress text
    expect(container.textContent).not.toContain('Uploading files');
  });
});
