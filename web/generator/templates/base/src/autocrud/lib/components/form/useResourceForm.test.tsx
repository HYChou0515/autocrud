/**
 * useResourceForm — Tests for depth transition timing + submitting state.
 *
 * Verifies that when formDepth changes (e.g. 1→2), form values are updated
 * synchronously BEFORE React re-renders with the new visibleFields.
 * This prevents "uncontrolled to controlled" React warnings.
 *
 * Also verifies the `submitting` state is true while onSubmit is pending.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import type { ResourceConfig, ResourceField } from '../../resources';
import { useResourceForm } from './useResourceForm';
import { getByPath } from '@/autocrud/lib/utils/formUtils';

/** Minimal helper to create a ResourceField. */
function makeField(overrides: Partial<ResourceField> & { name: string }): ResourceField {
  return {
    label: overrides.name,
    type: 'string',
    isArray: false,
    isRequired: false,
    isNullable: false,
    ...overrides,
  };
}

/**
 * Build a minimal ResourceConfig with mock apiClient.
 */
function makeConfig(
  fields: ResourceField[],
  overrides: Partial<ResourceConfig> = {},
): ResourceConfig {
  const noop = vi.fn().mockResolvedValue({ data: {} });
  return {
    name: 'test',
    label: 'Test',
    pluralLabel: 'Tests',
    schema: 'Test',
    fields,
    apiClient: {
      create: noop,
      list: noop,
      count: noop,
      get: noop,
      update: noop,
      delete: noop,
      permanentlyDelete: noop,
      restore: noop,
      revisionList: noop,
      switchRevision: noop,
    },
    ...overrides,
  };
}

/**
 * Test component that tracks form value consistency on EVERY render.
 *
 * On each render, for every visible field that is NOT a collapsed group,
 * it checks whether form.getInputProps(field.name).value is undefined.
 * If any render has inconsistent values, it records them.
 *
 * This catches the "uncontrolled → controlled" root cause: a render frame
 * where visibleFields includes fields whose form values aren't set yet.
 */
function ConsistencyTracker({
  config,
  initialValues,
  onInconsistency,
}: {
  config: ResourceConfig;
  initialValues: any;
  onInconsistency: (fields: string[]) => void;
}) {
  const hook = useResourceForm({
    config,
    initialValues,
    onSubmit: async () => {},
  });

  // Check consistency on EVERY render (including intermediate ones)
  const collapsedPaths = new Set(hook.collapsedGroups.map((g) => g.path));
  const inconsistent: string[] = [];
  for (const field of hook.visibleFields) {
    if (collapsedPaths.has(field.name)) continue; // collapsed groups render as Textarea, OK
    const value = getByPath(hook.form.getValues() as Record<string, any>, field.name);
    if (value === undefined) {
      inconsistent.push(field.name);
    }
  }
  if (inconsistent.length > 0) {
    onInconsistency(inconsistent);
  }

  return (
    <div>
      <span data-testid="depth">{hook.formDepth}</span>
      <button data-testid="set-depth-2" onClick={() => hook.setFormDepth(2)}>
        Depth 2
      </button>
      <button data-testid="set-depth-1" onClick={() => hook.setFormDepth(1)}>
        Depth 1
      </button>
    </div>
  );
}

describe('useResourceForm depth transition timing', () => {
  afterEach(cleanup);

  const fields: ResourceField[] = [
    makeField({ name: 'name', type: 'string', isRequired: true }),
    makeField({ name: 'payload.event_type', type: 'string' }),
    makeField({ name: 'payload.event_x.good', type: 'string' }),
    makeField({ name: 'payload.event_x.great', type: 'string' }),
  ];

  const initialValues = {
    name: 'test',
    payload: {
      event_type: 'quest',
      event_x: { good: 'a', great: 'b' },
    },
  };

  it('should have consistent form values on every render during depth 1→2 transition', () => {
    const config = makeConfig(fields, { maxFormDepth: 1 });
    const renderIssues: string[][] = [];
    const onInconsistency = (fields: string[]) => renderIssues.push([...fields]);

    const { getByTestId } = render(
      <ConsistencyTracker
        config={config}
        initialValues={initialValues}
        onInconsistency={onInconsistency}
      />,
    );

    // Verify initial depth
    expect(getByTestId('depth').textContent).toBe('1');

    // Transition to depth 2
    fireEvent.click(getByTestId('set-depth-2'));

    // Verify depth changed
    expect(getByTestId('depth').textContent).toBe('2');

    // No render should have had undefined values for visible non-collapsed fields
    expect(renderIssues).toHaveLength(0);
  });

  it('should have consistent form values on every render during depth 2→1 transition', () => {
    const config = makeConfig(fields, { maxFormDepth: 2 });
    const renderIssues: string[][] = [];
    const onInconsistency = (fields: string[]) => renderIssues.push([...fields]);

    const { getByTestId } = render(
      <ConsistencyTracker
        config={config}
        initialValues={initialValues}
        onInconsistency={onInconsistency}
      />,
    );

    // Verify initial depth
    expect(getByTestId('depth').textContent).toBe('2');

    // Transition to depth 1
    fireEvent.click(getByTestId('set-depth-1'));

    // Verify depth changed
    expect(getByTestId('depth').textContent).toBe('1');

    // No render should have had undefined values
    expect(renderIssues).toHaveLength(0);
  });
});

/**
 * Test component that exposes submitting state from useResourceForm.
 */
function SubmittingTracker({
  config,
  onSubmit,
}: {
  config: ResourceConfig;
  onSubmit: (values: any) => Promise<void>;
}) {
  const hook = useResourceForm({
    config,
    initialValues: { name: 'test' },
    onSubmit,
  });

  return (
    <div>
      <span data-testid="submitting">{String(hook.submitting)}</span>
      <button
        data-testid="trigger-submit"
        onClick={() => hook.handleSubmit({ name: 'test' } as any).catch(() => {})}
      >
        Submit
      </button>
    </div>
  );
}

describe('useResourceForm submitting state', () => {
  afterEach(cleanup);

  const fields: ResourceField[] = [makeField({ name: 'name', type: 'string', isRequired: true })];

  it('submitting is false by default', () => {
    const config = makeConfig(fields);
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    const { getByTestId } = render(<SubmittingTracker config={config} onSubmit={onSubmit} />);

    expect(getByTestId('submitting').textContent).toBe('false');
  });

  it('submitting is true while onSubmit is pending', async () => {
    const config = makeConfig(fields);
    let resolveSubmit!: () => void;
    const onSubmit = vi.fn().mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveSubmit = resolve;
        }),
    );

    const { getByTestId } = render(<SubmittingTracker config={config} onSubmit={onSubmit} />);

    // Initially false
    expect(getByTestId('submitting').textContent).toBe('false');

    // Click submit
    await act(async () => {
      fireEvent.click(getByTestId('trigger-submit'));
    });

    // Should be true while pending
    expect(getByTestId('submitting').textContent).toBe('true');

    // Resolve the submit promise
    await act(async () => {
      resolveSubmit();
    });

    // Should be false after resolving
    expect(getByTestId('submitting').textContent).toBe('false');
  });

  it('submitting resets to false when onSubmit throws', async () => {
    const config = makeConfig(fields);
    const onSubmit = vi.fn().mockRejectedValue(new Error('API error'));

    const { getByTestId } = render(<SubmittingTracker config={config} onSubmit={onSubmit} />);

    // Click submit — handleSubmit catches the error from onSubmit via finally
    await act(async () => {
      fireEvent.click(getByTestId('trigger-submit'));
      // Allow microtask for the rejected promise to settle
      await new Promise((r) => setTimeout(r, 0));
    });

    // Should reset to false after rejection
    expect(getByTestId('submitting').textContent).toBe('false');
  });
});
