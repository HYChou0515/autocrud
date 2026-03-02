/**
 * useResourceForm — Tests for depth transition timing.
 *
 * Verifies that when formDepth changes (e.g. 1→2), form values are updated
 * synchronously BEFORE React re-renders with the new visibleFields.
 * This prevents "uncontrolled to controlled" React warnings.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, cleanup } from '@testing-library/react';
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
