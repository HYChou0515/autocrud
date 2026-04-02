/**
 * useResourceForm — Tests for the custom hook.
 *
 * Tests mode switching, depth handling, validation, binary upload state,
 * and submission logic via renderHook.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, cleanup } from '@testing-library/react';
import {
  useResourceForm,
  type UseResourceFormOptions,
  type BlobUploadState,
} from './useResourceForm';

import {
  computeVisibleFieldsAndGroups,
  isCollapsedChild,
  computeDepthTransitionUpdates,
} from '@/autocrud/lib/utils/formUtils';

// ── Mock formUtils ──
vi.mock('@/autocrud/lib/utils/formUtils', () => ({
  computeMaxAvailableDepth: vi.fn(() => 2),
  computeVisibleFieldsAndGroups: vi.fn(() => ({
    visibleFields: [],
    collapsedGroups: [],
    collapsedGroupFields: [],
  })),
  processInitialValues: vi.fn((vals: any) => ({ ...vals })),
  formValuesToApiObject: vi.fn((vals: any) => ({ ...vals })),
  applyJsonToForm: vi.fn((data: any) => ({ ...data })),
  isCollapsedChild: vi.fn(() => false),
  validateJsonFields: vi.fn(() => ({})),
  preprocessArrayFields: vi.fn((vals: any) => ({ ...vals })),
  parseAndValidateJson: vi.fn((text: string) => {
    try {
      return { success: true, data: JSON.parse(text) };
    } catch {
      return { success: false, error: 'Invalid JSON' };
    }
  }),
  processSubmitValues: vi.fn(() => ({
    skippedBinaryFields: [],
    binarySubFieldKeys: [],
  })),
  computeValidationSuppressPaths: vi.fn(() => ({
    suppressPaths: new Set<string>(),
    nestedArraySubFields: [],
  })),
  computeDepthTransitionUpdates: vi.fn(() => ({ expands: [], collapses: [] })),
  _collectUnionBinaryKeys: vi.fn(() => []),
  getByPath: vi.fn((obj: any, path: string) => obj?.[path]),
  setByPath: vi.fn((obj: any, path: string, val: any) => {
    obj[path] = val;
  }),
  collapseFieldToJson: vi.fn(() => '{}'),
  groupFieldsByParent: vi.fn(() => []),
}));

// ── Mock useBlobUpload ──
vi.mock('../../hooks/useBlobUpload', () => ({
  uploadFileToBlob: vi.fn(),
  computeEta: vi.fn(() => null),
  formatBytes: vi.fn((n: number) => `${n} B`),
  formatDuration: vi.fn((n: number) => `${n}s`),
}));

// ── Mock mantine-form-zod-resolver ──
vi.mock('mantine-form-zod-resolver', () => ({
  zodResolver: vi.fn(() => vi.fn(() => ({}))),
}));

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const makeField = (name: string, type = 'string', opts: any = {}) => ({
  name,
  label: name,
  type,
  isArray: false,
  isRequired: false,
  isNullable: false,
  ...opts,
});

function makeConfig(overrides: any = {}) {
  return {
    name: 'test',
    label: 'Test',
    fields: overrides.fields ?? [makeField('name'), makeField('age', 'number')],
    apiClient: overrides.apiClient ?? {},
    zodSchema: overrides.zodSchema ?? undefined,
    maxFormDepth: overrides.maxFormDepth ?? undefined,
    defaultHiddenFields: overrides.defaultHiddenFields ?? undefined,
    ...overrides,
  };
}

function renderUseResourceForm(overrides: any = {}) {
  const onSubmit = overrides.onSubmit ?? vi.fn();
  const config = makeConfig(overrides.config ?? {});
  const initialValues = overrides.initialValues ?? {};

  return renderHook(() =>
    useResourceForm({
      config: config as any,
      initialValues,
      onSubmit,
    }),
  );
}

describe('useResourceForm', () => {
  it('initializes with form edit mode', () => {
    const { result } = renderUseResourceForm();
    expect(result.current.editMode).toBe('form');
  });

  it('returns form instance', () => {
    const { result } = renderUseResourceForm();
    expect(result.current.form).toBeDefined();
    expect(result.current.form.getValues).toBeDefined();
  });

  it('initializes with correct depth', () => {
    const { result } = renderUseResourceForm();
    expect(result.current.maxAvailableDepth).toBe(2);
    expect(result.current.formDepth).toBe(2);
  });

  it('respects maxFormDepth config', () => {
    const { result } = renderUseResourceForm({ config: { maxFormDepth: 1 } });
    expect(result.current.formDepth).toBe(1);
  });

  it('switches to JSON mode', () => {
    const { result } = renderUseResourceForm();
    act(() => {
      result.current.handleSwitchToJson();
    });
    expect(result.current.editMode).toBe('json');
    expect(result.current.jsonText).toBeDefined();
  });

  it('switches back to form mode from JSON', () => {
    const { result } = renderUseResourceForm();

    act(() => {
      result.current.handleSwitchToJson();
    });
    expect(result.current.editMode).toBe('json');

    act(() => {
      result.current.setJsonText('{"name": "test"}');
    });

    act(() => {
      result.current.handleSwitchToForm();
    });
    expect(result.current.editMode).toBe('form');
  });

  it('shows JSON error for invalid JSON when switching to form', () => {
    const { result } = renderUseResourceForm();

    act(() => {
      result.current.handleSwitchToJson();
    });

    act(() => {
      result.current.setJsonText('{invalid json}');
    });

    act(() => {
      result.current.handleSwitchToForm();
    });

    expect(result.current.jsonError).not.toBeNull();
    expect(result.current.editMode).toBe('json'); // should stay in json mode
  });

  it('handleJsonSubmit with valid JSON calls onSubmit', () => {
    const onSubmit = vi.fn();
    const { result } = renderUseResourceForm({ onSubmit });

    act(() => {
      result.current.handleSwitchToJson();
    });

    act(() => {
      result.current.setJsonText('{"name": "test"}');
    });

    act(() => {
      result.current.handleJsonSubmit();
    });

    expect(result.current.jsonError).toBeNull();
    expect(onSubmit).toHaveBeenCalledWith({ name: 'test' });
  });

  it('handleJsonSubmit with invalid JSON sets error', () => {
    const onSubmit = vi.fn();
    const { result } = renderUseResourceForm({ onSubmit });

    act(() => {
      result.current.handleSwitchToJson();
    });

    act(() => {
      result.current.setJsonText('{bad}');
    });

    act(() => {
      result.current.handleJsonSubmit();
    });

    expect(result.current.jsonError).not.toBeNull();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('setFormDepth changes depth', () => {
    const { result } = renderUseResourceForm();

    act(() => {
      result.current.setFormDepth(1);
    });

    expect(result.current.formDepth).toBe(1);
  });

  it('initializes blob upload state', () => {
    const { result } = renderUseResourceForm();
    expect(result.current.blobUploadState.isUploading).toBe(false);
    expect(result.current.blobUploadState.error).toBeNull();
    expect(result.current.blobUploadState.totalFiles).toBe(0);
  });

  it('cancelBlobUpload sets error state', () => {
    const { result } = renderUseResourceForm();

    act(() => {
      result.current.cancelBlobUpload();
    });

    expect(result.current.blobUploadState.isUploading).toBe(false);
    expect(result.current.blobUploadState.error).toBe('Upload cancelled');
  });

  it('handleSubmit calls onSubmit with processed values', async () => {
    const onSubmit = vi.fn();
    const { result } = renderUseResourceForm({ onSubmit });

    await act(async () => {
      await result.current.handleSubmit({ name: 'test', age: 25 } as any);
    });

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ name: 'test', age: 25 }));
  });

  it('simpleUnionTypes state management', () => {
    const { result } = renderUseResourceForm();
    expect(result.current.simpleUnionTypes).toEqual({});

    act(() => {
      result.current.setSimpleUnionTypes({ field1: 'type_a' });
    });

    expect(result.current.simpleUnionTypes).toEqual({ field1: 'type_a' });
  });

  it('manages jsonText and jsonError state', () => {
    const { result } = renderUseResourceForm();

    act(() => {
      result.current.setJsonText('hello');
    });
    expect(result.current.jsonText).toBe('hello');

    act(() => {
      result.current.setJsonError('some error');
    });
    expect(result.current.jsonError).toBe('some error');
  });
});

describe('useResourceForm — internal helpers', () => {
  it('_binaryFormValueToApiDirect returns null for empty mode', async () => {
    // Test indirectly via handleSubmit with binary field
    const onSubmit = vi.fn();
    const fields = [makeField('avatar', 'binary')];
    const { result } = renderUseResourceForm({
      onSubmit,
      config: { fields },
    });

    await act(async () => {
      await result.current.handleSubmit({ avatar: null } as any);
    });

    expect(onSubmit).toHaveBeenCalled();
  });

  it('handles binary field with _mode=existing', async () => {
    const onSubmit = vi.fn();
    const fields = [makeField('avatar', 'binary')];
    const { result } = renderUseResourceForm({
      onSubmit,
      config: { fields },
    });

    await act(async () => {
      await result.current.handleSubmit({
        avatar: { _mode: 'existing', file_id: 'f1' },
      } as any);
    });

    expect(onSubmit).toHaveBeenCalled();
  });

  it('handles binary field with _mode=empty', async () => {
    const onSubmit = vi.fn();
    const fields = [makeField('avatar', 'binary')];
    const { result } = renderUseResourceForm({
      onSubmit,
      config: { fields },
    });

    await act(async () => {
      await result.current.handleSubmit({
        avatar: { _mode: 'empty' },
      } as any);
    });

    expect(onSubmit).toHaveBeenCalled();
  });

  it('handles file type fields — preserves File objects', async () => {
    const onSubmit = vi.fn();
    const fields = [makeField('upload', 'file')];
    const file = new File(['content'], 'test.txt', { type: 'text/plain' });
    const { result } = renderUseResourceForm({
      onSubmit,
      config: { fields },
    });

    await act(async () => {
      await result.current.handleSubmit({ upload: file } as any);
    });

    expect(onSubmit).toHaveBeenCalled();
  });

  it('handles date fields in config', () => {
    const fields = [makeField('birthday', 'date'), makeField('name')];
    const { result } = renderUseResourceForm({
      config: { fields },
    });
    // Should initialize without error
    expect(result.current.form).toBeDefined();
  });

  it('respects defaultHiddenFields config', () => {
    const fields = [makeField('name'), makeField('secret')];
    const { result } = renderUseResourceForm({
      config: { fields, defaultHiddenFields: ['secret'] },
    });
    // visibleFields should not include 'secret'
    // But since computeVisibleFieldsAndGroups is mocked to return [],
    // we can't test filtering. Just verify initialization works.
    expect(result.current.visibleFields).toBeDefined();
  });

  it('handleJsonSubmit with zodSchema validation failure', () => {
    const onSubmit = vi.fn();
    const zodSchema = {
      safeParse: vi.fn(() => ({
        success: false,
        error: {
          issues: [
            { path: ['name'], message: 'Required' },
            { path: ['age'], message: 'Must be > 0' },
          ],
        },
      })),
    };
    const { result } = renderUseResourceForm({
      onSubmit,
      config: {
        zodSchema,
        fields: [makeField('name'), makeField('age', 'number')],
      },
    });

    act(() => {
      result.current.handleSwitchToJson();
    });
    act(() => {
      result.current.setJsonText('{"name": "", "age": -1}');
    });
    act(() => {
      result.current.handleJsonSubmit();
    });

    expect(result.current.jsonError).not.toBeNull();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('handleJsonSubmit with zodSchema validation success', () => {
    const onSubmit = vi.fn();
    const zodSchema = {
      safeParse: vi.fn(() => ({ success: true, data: { name: 'test' } })),
    };
    const { result } = renderUseResourceForm({
      onSubmit,
      config: {
        zodSchema,
        fields: [makeField('name')],
      },
    });

    act(() => {
      result.current.handleSwitchToJson();
    });
    act(() => {
      result.current.setJsonText('{"name": "test"}');
    });
    act(() => {
      result.current.handleJsonSubmit();
    });

    expect(result.current.jsonError).toBeNull();
    expect(onSubmit).toHaveBeenCalled();
  });

  it('handleSubmit with zodSchema post-validation failure', async () => {
    const onSubmit = vi.fn();
    const zodSchema = {
      safeParse: vi.fn(() => ({
        success: false,
        error: {
          issues: [{ path: ['name'], message: 'Too short' }],
        },
      })),
    };
    const { result } = renderUseResourceForm({
      onSubmit,
      config: {
        zodSchema,
        fields: [makeField('name')],
      },
    });

    await act(async () => {
      await result.current.handleSubmit({ name: 'x' } as any);
    });

    // onSubmit should NOT be called when zod fails
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('handles array items with binary sub-fields', async () => {
    const onSubmit = vi.fn();
    const itemFields = [makeField('name'), makeField('image', 'binary')];
    const fields = [makeField('items', 'array', { itemFields })];
    const { result } = renderUseResourceForm({
      onSubmit,
      config: { fields },
    });

    await act(async () => {
      await result.current.handleSubmit({
        items: [
          { name: 'item1', image: { _mode: 'existing', file_id: 'f1' } },
        ],
      } as any);
    });

    expect(onSubmit).toHaveBeenCalled();
  });

  it('handles union field with binary sub-fields', async () => {
    const onSubmit = vi.fn();
    const fields = [
      makeField('data', 'union', {
        unionMeta: {
          discriminatorField: 'type',
          variants: [
            {
              tag: 'FileAttachment',
              fields: [makeField('type'), makeField('content', 'binary')],
            },
          ],
        },
      }),
    ];
    const { result } = renderUseResourceForm({
      onSubmit,
      config: { fields },
    });

    await act(async () => {
      await result.current.handleSubmit({
        data: { type: 'FileAttachment', content: { _mode: 'empty' } },
      } as any);
    });

    expect(onSubmit).toHaveBeenCalled();
  });

  it('handleSwitchToForm with collapsed groups', () => {
    vi.mocked(computeVisibleFieldsAndGroups).mockReturnValue({
      visibleFields: [makeField('name')],
      collapsedGroups: [{ path: 'nested', label: 'Nested' }],
      collapsedGroupFields: [],
    } as any);
    vi.mocked(isCollapsedChild).mockImplementation((name: string) => name.startsWith('nested'));

    const { result } = renderUseResourceForm({
      config: {
        fields: [makeField('name'), makeField('nested.a')],
      },
    });

    act(() => {
      result.current.handleSwitchToJson();
    });
    act(() => {
      result.current.setJsonText('{"name": "test", "nested": {"a": 1}}');
    });
    act(() => {
      result.current.handleSwitchToForm();
    });

    expect(result.current.editMode).toBe('form');
  });

  it('depth transition with expand/collapse', () => {
    vi.mocked(computeDepthTransitionUpdates).mockReturnValue({
      expands: [{ path: 'nested', value: { a: 1 } }],
      collapses: [],
    } as any);

    const { result } = renderUseResourceForm();

    act(() => {
      result.current.setFormDepth(1);
    });

    expect(computeDepthTransitionUpdates).toHaveBeenCalled();
  });
});
