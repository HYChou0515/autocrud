/**
 * useResourceForm — Custom hook encapsulating all ResourceForm state,
 * effects, validation, and submission logic.
 *
 * Pure orchestration: delegates to formUtils for all data transformations.
 * Binary file uploads are deferred until form submission for better UX.
 */

import { useState, useMemo, useCallback, useRef } from 'react';
import { useForm, type UseFormReturnType } from '@mantine/form';
import { zodResolver } from 'mantine-form-zod-resolver';
import type { ResourceConfig, ResourceField } from '../../resources';
import {
  getByPath,
  setByPath,
  computeVisibleFieldsAndGroups,
  computeMaxAvailableDepth,
  processInitialValues,
  formValuesToApiObject as formValuesToApiObjectUtil,
  applyJsonToForm as applyJsonToFormUtil,
  isCollapsedChild as isCollapsedChildUtil,
  validateJsonFields,
  preprocessArrayFields,
  parseAndValidateJson,
  processSubmitValues,
  computeValidationSuppressPaths,
  computeDepthTransitionUpdates,
  _collectUnionBinaryKeys,
  type BinaryFormValue,
} from '@/autocrud/lib/utils/formUtils';
import { uploadFileToBlob, computeEta, type BlobUploadProgress } from '../../hooks/useBlobUpload';

export interface UseResourceFormOptions<T> {
  config: ResourceConfig<T>;
  initialValues: Partial<T>;
  onSubmit: (values: T) => void | Promise<void>;
}

/** Aggregate state for deferred blob uploads during form submission */
export interface BlobUploadState {
  /** Whether blob files are currently being uploaded */
  isUploading: boolean;
  /** Field name of the current file being uploaded */
  currentFieldName: string | null;
  /** File name of the current file being uploaded */
  currentFileName: string | null;
  /** Total number of files to upload */
  totalFiles: number;
  /** Number of files completed so far */
  completedFiles: number;
  /** Aggregate progress across all files */
  progress: BlobUploadProgress;
  /** Error message if upload failed */
  error: string | null;
}

const INITIAL_BLOB_UPLOAD_STATE: BlobUploadState = {
  isUploading: false,
  currentFieldName: null,
  currentFileName: null,
  totalFiles: 0,
  completedFiles: 0,
  progress: { loaded: 0, total: 0, percent: 0, elapsed: 0, eta: null },
  error: null,
};

export interface UseResourceFormReturn<T extends Record<string, any>> {
  form: UseFormReturnType<T>;
  editMode: 'form' | 'json';
  jsonText: string;
  setJsonText: (text: string) => void;
  jsonError: string | null;
  setJsonError: (error: string | null) => void;
  handleSwitchToJson: () => void;
  handleSwitchToForm: () => void;
  handleJsonSubmit: () => void;
  maxAvailableDepth: number;
  formDepth: number;
  setFormDepth: (depth: number) => void;
  visibleFields: ResourceField[];
  collapsedGroups: { path: string; label: string }[];
  simpleUnionTypes: Record<string, string>;
  setSimpleUnionTypes: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  handleSubmit: (values: T) => Promise<void>;
  /** Aggregate blob upload state during form submission */
  blobUploadState: BlobUploadState;
  /** Cancel all in-progress blob uploads */
  cancelBlobUpload: () => void;
}

export function useResourceForm<T extends Record<string, any>>({
  config,
  initialValues,
  onSubmit,
}: UseResourceFormOptions<T>): UseResourceFormReturn<T> {
  // ── Mode state ──
  const [editMode, setEditMode] = useState<'form' | 'json'>('form');
  const [jsonText, setJsonText] = useState('');
  const [jsonError, setJsonError] = useState<string | null>(null);

  // ── Depth state ──
  const maxAvailableDepth = useMemo(() => computeMaxAvailableDepth(config.fields), [config.fields]);
  const [formDepth, setFormDepth] = useState<number>(config.maxFormDepth ?? maxAvailableDepth);

  // ── Union state ──
  const [simpleUnionTypes, setSimpleUnionTypes] = useState<Record<string, string>>({});

  // ── Visible fields & collapsed groups ──
  const hiddenFieldSet = useMemo(
    () => new Set(config.defaultHiddenFields ?? []),
    [config.defaultHiddenFields],
  );
  const {
    visibleFields: rawVisibleFields,
    collapsedGroups,
    collapsedGroupFields: _collapsedGroupFields,
  } = useMemo(
    () => computeVisibleFieldsAndGroups(config.fields, formDepth),
    [config.fields, formDepth],
  );
  // Filter out defaultHiddenFields — they still participate in form data but are not rendered
  const visibleFields = useMemo(
    () =>
      hiddenFieldSet.size > 0
        ? rawVisibleFields.filter((f) => !hiddenFieldSet.has(f.name))
        : rawVisibleFields,
    [rawVisibleFields, hiddenFieldSet],
  );

  // ── Date fields ──
  const dateFieldNames = useMemo(
    () =>
      config.fields
        .filter((f) => f.type === 'date' || f.variant?.type === 'date')
        .map((f) => f.name),
    [config.fields],
  );

  // ── Initial values ──
  const processedInitialValues = processInitialValues(
    initialValues as Record<string, any>,
    config.fields,
    collapsedGroups,
    dateFieldNames,
  );

  // ── Validation ──
  const zodValidate = config.zodSchema ? zodResolver(config.zodSchema) : undefined;

  const combinedValidate = (values: T) => {
    const errors = validateJsonFields(
      values as Record<string, any>,
      config.fields,
      collapsedGroups,
    );
    if (zodValidate) {
      try {
        const zodValues = preprocessArrayFields(values as Record<string, any>, config.fields);
        const zodErrors = zodValidate(zodValues as T);
        const { suppressPaths, nestedArraySubFields } = computeValidationSuppressPaths(
          config.fields,
          collapsedGroups,
        );
        for (const key of Object.keys(zodErrors)) {
          if (suppressPaths.has(key)) {
            delete zodErrors[key];
          }
          if (collapsedGroups.some((g) => key.startsWith(g.path + '.'))) {
            delete zodErrors[key];
          }
          if (
            nestedArraySubFields.some(({ parent, sub }) =>
              new RegExp(`^${parent}\\.\\d+\\.${sub}$`).test(key),
            )
          ) {
            delete zodErrors[key];
          }
        }
        return { ...zodErrors, ...errors };
      } catch {
        return errors;
      }
    }
    return errors;
  };

  // ── Form instance ──
  const form = useForm<T>({
    initialValues: processedInitialValues as T,
    validate: combinedValidate,
  });

  // ── Depth transition (synchronous, no useEffect) ──
  // Tracks the previous collapsed group paths. Initialised lazily to match
  // the initial formDepth so that the first handleSetFormDepth call can
  // compute the correct diff.
  const prevCollapsedGroupPathsRef = useRef<Set<string>>(
    new Set(collapsedGroups.map((g) => g.path)),
  );

  /**
   * Synchronous depth-change handler.
   *
   * Updates form values BEFORE calling setFormDepth so that React's
   * batched re-render sees both the new depth AND the correct form values
   * on the very first render frame.  This eliminates the "uncontrolled →
   * controlled" React warning caused by the old useEffect approach.
   */
  const handleSetFormDepth = useCallback(
    (newDepth: number) => {
      // Compute what the collapsed groups will look like at the new depth
      const { collapsedGroups: nextCollapsedGroups } = computeVisibleFieldsAndGroups(
        config.fields,
        newDepth,
      );

      const prevPaths = prevCollapsedGroupPathsRef.current;
      const values = form.getValues() as Record<string, any>;

      const { expands, collapses } = computeDepthTransitionUpdates(
        values,
        prevPaths,
        nextCollapsedGroups,
        config.fields,
      );

      // Apply expand/collapse synchronously
      for (const { path, value } of expands) {
        form.setFieldValue(path as any, value as any);
      }
      for (const { path, value } of collapses) {
        form.setFieldValue(path as any, value as any);
      }

      prevCollapsedGroupPathsRef.current = new Set(nextCollapsedGroups.map((g) => g.path));

      // Finally change depth — React batches this with the setFieldValue
      // calls above, producing a single re-render with consistent values.
      setFormDepth(newDepth);
    },
    [config.fields, form],
  );

  // ── Mode switching helpers ──
  const handleSwitchToJson = () => {
    const values = form.getValues() as Record<string, any>;
    const apiObj = formValuesToApiObjectUtil(
      values,
      config.fields,
      collapsedGroups,
      dateFieldNames,
    );
    setJsonText(JSON.stringify(apiObj, null, 2));
    setJsonError(null);
    setEditMode('json');
  };

  const handleSwitchToForm = () => {
    const result = parseAndValidateJson(jsonText);
    if (!result.success) {
      setJsonError(result.error || 'Invalid JSON');
      return;
    }
    const newValues = applyJsonToFormUtil(
      result.data,
      config.fields,
      collapsedGroups,
      dateFieldNames,
    );
    for (const field of config.fields) {
      if (isCollapsedChildUtil(field.name, collapsedGroups)) continue;
      const val =
        newValues[field.name] !== undefined
          ? newValues[field.name]
          : getByPath(newValues, field.name);
      form.setFieldValue(field.name, val);
    }
    for (const group of collapsedGroups) {
      form.setFieldValue(group.path, newValues[group.path]);
    }
    setJsonError(null);
    setEditMode('form');
  };

  const handleJsonSubmit = () => {
    const result = parseAndValidateJson(jsonText);
    if (!result.success) {
      setJsonError(result.error || 'Invalid JSON');
      return;
    }
    const parsed = result.data;
    if (config.zodSchema) {
      const zodResult = config.zodSchema.safeParse(parsed);
      if (!zodResult.success) {
        const fieldErrors = zodResult.error.issues.map((issue: any) => {
          const path = issue.path.join('.');
          const fieldDef = config.fields.find((f) => f.name === path);
          const label = fieldDef?.label || path || 'Root';
          return `${label}: ${issue.message}`;
        });
        setJsonError(fieldErrors.join('\n'));
        return;
      }
    }
    setJsonError(null);
    return onSubmit(parsed as T);
  };

  // ── Blob upload state (deferred: uploads happen at submit time) ──
  const [blobUploadState, setBlobUploadState] =
    useState<BlobUploadState>(INITIAL_BLOB_UPLOAD_STATE);
  const blobAbortRef = useRef<AbortController | null>(null);
  const blobTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const cancelBlobUpload = useCallback(() => {
    blobAbortRef.current?.abort();
    blobAbortRef.current = null;
    if (blobTimerRef.current) {
      clearInterval(blobTimerRef.current);
      blobTimerRef.current = null;
    }
    setBlobUploadState((prev) => ({
      ...prev,
      isUploading: false,
      error: 'Upload cancelled',
    }));
  }, []);

  // ── Submit ──
  const handleSubmit = async (values: T) => {
    try {
      const binaryFieldValues = new Map<string, BinaryFormValue | null>();
      const arrayItemBinaryValues = new Map<string, BinaryFormValue | null>();
      // Preserve File objects before JSON deep copy destroys them
      const fileFieldValues = new Map<string, File | null>();
      for (const field of config.fields) {
        if (field.type === 'binary') {
          const bv = getByPath(values as Record<string, any>, field.name) as BinaryFormValue | null;
          binaryFieldValues.set(field.name, bv);
        }
        if (field.type === 'file') {
          const fv = getByPath(values as Record<string, any>, field.name) as File | null;
          fileFieldValues.set(field.name, fv);
        }
        if (field.itemFields) {
          const items = (values as Record<string, any>)[field.name];
          if (Array.isArray(items)) {
            for (let i = 0; i < items.length; i++) {
              for (const sf of field.itemFields) {
                if (sf.type === 'binary') {
                  const bv = items[i]?.[sf.name] as BinaryFormValue | null;
                  arrayItemBinaryValues.set(`${field.name}.${i}.${sf.name}`, bv);
                }
              }
            }
          }
        }
        // Also preserve binary values inside union variant sub-fields
        if (field.type === 'union' && field.unionMeta) {
          const val = getByPath(values as Record<string, any>, field.name);
          _extractUnionBinaryValues(val, field, field.name, arrayItemBinaryValues);
        }
      }

      const processed = JSON.parse(JSON.stringify(values)) as Record<string, any>;
      const { skippedBinaryFields, binarySubFieldKeys } = processSubmitValues(
        processed,
        config.fields,
        collapsedGroups,
        dateFieldNames,
      );

      // ── Deferred blob upload: collect all pending uploads ──
      type PendingUpload = {
        key: string;
        bv: BinaryFormValue | null | undefined;
        fieldName: string;
        fileName: string;
        fileSize: number;
      };
      const pendingUploads: PendingUpload[] = [];

      // Collect from sub-field keys (array items, union variants)
      for (const key of binarySubFieldKeys) {
        const bv = arrayItemBinaryValues.get(key);
        if (bv && ((bv._mode === 'file' && bv.file) || (bv._mode === 'url' && bv.url))) {
          const fileName = bv._mode === 'file' && bv.file ? bv.file.name : (bv.url ?? 'download');
          const fileSize = bv._mode === 'file' && bv.file ? bv.file.size : 0;
          pendingUploads.push({ key, bv, fieldName: key, fileName, fileSize });
        } else {
          // Handle existing / empty modes directly
          const apiVal = _binaryFormValueToApiDirect(bv);
          setByPath(processed, key, apiVal);
        }
      }

      // Collect from top-level binary fields
      for (const fieldName of skippedBinaryFields) {
        const bv = binaryFieldValues.get(fieldName);
        if (bv && ((bv._mode === 'file' && bv.file) || (bv._mode === 'url' && bv.url))) {
          const fileName = bv._mode === 'file' && bv.file ? bv.file.name : (bv.url ?? 'download');
          const fileSize = bv._mode === 'file' && bv.file ? bv.file.size : 0;
          pendingUploads.push({ key: fieldName, bv, fieldName, fileName, fileSize });
        } else {
          // Handle existing / empty modes directly
          const apiVal = _binaryFormValueToApiDirect(bv);
          setByPath(processed, fieldName, apiVal);
        }
      }

      // ── Upload pending files with aggregate progress tracking ──
      if (pendingUploads.length > 0) {
        const totalSize = pendingUploads.reduce((sum, p) => sum + p.fileSize, 0);
        const abortController = new AbortController();
        blobAbortRef.current = abortController;

        const startTime = Date.now();
        let completedBytes = 0; // bytes from fully completed files

        // Progress refs for timer-based elapsed/ETA update
        const progressRef = { completedBytes: 0, currentFileLoaded: 0 };

        setBlobUploadState({
          isUploading: true,
          currentFieldName: null,
          currentFileName: null,
          totalFiles: pendingUploads.length,
          completedFiles: 0,
          progress: { loaded: 0, total: totalSize, percent: 0, elapsed: 0, eta: null },
          error: null,
        });

        // Start timer for elapsed/ETA updates
        blobTimerRef.current = setInterval(() => {
          const elapsed = (Date.now() - startTime) / 1000;
          const loaded = progressRef.completedBytes + progressRef.currentFileLoaded;
          const percent = totalSize > 0 ? Math.round((loaded / totalSize) * 100) : 0;
          const eta = computeEta(loaded, totalSize, elapsed);
          setBlobUploadState((prev) => ({
            ...prev,
            progress: { loaded, total: totalSize, percent: Math.min(percent, 99), elapsed, eta },
          }));
        }, 500);

        try {
          for (let i = 0; i < pendingUploads.length; i++) {
            if (abortController.signal.aborted) {
              throw new Error('Upload cancelled');
            }

            const pending = pendingUploads[i];
            setBlobUploadState((prev) => ({
              ...prev,
              currentFieldName: pending.fieldName,
              currentFileName: pending.fileName,
              completedFiles: i,
            }));

            let fileToUpload: File;
            if (pending.bv?._mode === 'url' && pending.bv.url) {
              // Fetch URL content first
              const resp = await fetch(pending.bv.url);
              const blob = await resp.blob();
              fileToUpload = new File([blob], 'download', {
                type: blob.type || 'application/octet-stream',
              });
              // Update the actual file size now that we know it
              pending.fileSize = fileToUpload.size;
            } else if (pending.bv?._mode === 'file' && pending.bv.file) {
              fileToUpload = pending.bv.file;
            } else {
              continue;
            }

            const result = await uploadFileToBlob(fileToUpload, {
              signal: abortController.signal,
              onProgress: (loaded, _total) => {
                progressRef.currentFileLoaded = loaded;
                const totalLoaded = completedBytes + loaded;
                const elapsed = (Date.now() - startTime) / 1000;
                const percent = totalSize > 0 ? Math.round((totalLoaded / totalSize) * 100) : 0;
                const eta = computeEta(totalLoaded, totalSize, elapsed);
                setBlobUploadState((prev) => ({
                  ...prev,
                  progress: {
                    loaded: totalLoaded,
                    total: totalSize,
                    percent: Math.min(percent, 99),
                    elapsed,
                    eta,
                  },
                }));
              },
            });

            if (!result) {
              throw new Error(`Upload cancelled for ${pending.fileName}`);
            }

            setByPath(processed, pending.key, {
              file_id: result.file_id,
              content_type: result.content_type,
              size: result.size,
            });

            completedBytes += pending.fileSize;
            progressRef.completedBytes = completedBytes;
            progressRef.currentFileLoaded = 0;
          }

          // All uploads done
          if (blobTimerRef.current) {
            clearInterval(blobTimerRef.current);
            blobTimerRef.current = null;
          }
          const finalElapsed = (Date.now() - startTime) / 1000;
          setBlobUploadState({
            isUploading: false,
            currentFieldName: null,
            currentFileName: null,
            totalFiles: pendingUploads.length,
            completedFiles: pendingUploads.length,
            progress: {
              loaded: totalSize,
              total: totalSize,
              percent: 100,
              elapsed: finalElapsed,
              eta: 0,
            },
            error: null,
          });
        } catch (uploadError: any) {
          if (blobTimerRef.current) {
            clearInterval(blobTimerRef.current);
            blobTimerRef.current = null;
          }
          const msg =
            uploadError?.response?.data?.detail || uploadError?.message || 'Upload failed';
          setBlobUploadState((prev) => ({
            ...prev,
            isUploading: false,
            error: msg,
          }));
          blobAbortRef.current = null;
          throw uploadError;
        }
        blobAbortRef.current = null;
      }

      // Restore File objects after JSON deep copy
      for (const [fieldName, file] of fileFieldValues) {
        setByPath(processed, fieldName, file);
      }

      if (config.zodSchema) {
        const result = config.zodSchema.safeParse(processed);
        if (!result.success) {
          console.warn(
            '[useResourceForm] Zod validation failed after binary processing:',
            result.error.issues,
          );
          for (const issue of result.error.issues) {
            form.setFieldError(issue.path.join('.'), issue.message);
          }
          return;
        }
      }

      return onSubmit(processed as T);
    } catch (error) {
      console.error('[useResourceForm] Submit failed during binary processing:', error);
      throw error;
    }
  };

  return {
    form,
    editMode,
    jsonText,
    setJsonText,
    jsonError,
    setJsonError,
    handleSwitchToJson,
    handleSwitchToForm,
    handleJsonSubmit,
    maxAvailableDepth,
    formDepth,
    setFormDepth: handleSetFormDepth,
    visibleFields,
    collapsedGroups,
    simpleUnionTypes,
    setSimpleUnionTypes,
    handleSubmit,
    blobUploadState,
    cancelBlobUpload,
  };
}

/**
 * Convert a BinaryFormValue to API-ready payload for non-upload modes.
 * Handles 'existing' and 'empty' modes synchronously (no upload needed).
 *
 * @internal
 */
function _binaryFormValueToApiDirect(
  val: BinaryFormValue | null | undefined,
): Record<string, any> | null {
  if (!val || val._mode === 'empty') return null;
  if (val._mode === 'existing') {
    return { file_id: val.file_id };
  }
  // 'file' and 'url' modes should have been handled by the upload loop
  return null;
}

/**
 * Extract BinaryFormValue objects from union variant sub-fields BEFORE JSON deep copy.
 *
 * JSON.stringify destroys File references, so we need to preserve them in a Map first.
 * Uses the same path schema as `_collectUnionBinaryKeys` so keys match up after deep copy.
 *
 * @internal
 */
function _extractUnionBinaryValues(
  val: any,
  field: { unionMeta?: any; isArray?: boolean },
  basePath: string,
  out: Map<string, BinaryFormValue | null>,
): void {
  const meta = field.unionMeta;
  if (!meta || val == null) return;

  const scanItem = (item: Record<string, any>, path: string) => {
    const discField = meta.discriminatorField;
    const tag = item?.[discField];
    const variant = tag != null ? meta.variants?.find((v: any) => v.tag === tag) : undefined;
    const candidateFields: any[] = variant?.fields ?? [];

    if (candidateFields.length === 0 && !variant) {
      for (const v of meta.variants ?? []) {
        for (const sf of v.fields ?? []) {
          if (sf.type === 'binary' && item?.[sf.name] != null) {
            out.set(`${path}.${sf.name}`, item[sf.name] as BinaryFormValue | null);
          }
        }
      }
      return;
    }

    for (const sf of candidateFields) {
      if (sf.type === 'binary') {
        out.set(`${path}.${sf.name}`, item?.[sf.name] as BinaryFormValue | null);
      }
    }
  };

  if (field.isArray && Array.isArray(val)) {
    for (let i = 0; i < val.length; i++) {
      if (val[i] && typeof val[i] === 'object') {
        scanItem(val[i], `${basePath}.${i}`);
      }
    }
  } else if (typeof val === 'object') {
    scanItem(val, basePath);
  }
}
