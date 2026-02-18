/**
 * useResourceForm — Custom hook encapsulating all ResourceForm state,
 * effects, validation, and submission logic.
 *
 * Pure orchestration: delegates to formUtils for all data transformations.
 */

import { useState, useMemo, useEffect, useRef } from 'react';
import { useForm, type UseFormReturnType } from '@mantine/form';
import { zodResolver } from 'mantine-form-zod-resolver';
import type { ResourceConfig, ResourceField } from '../resources';
import {
  getByPath,
  setByPath,
  binaryFormValueToApi,
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
  collapseFieldToJson,
  expandFieldFromJson,
  type BinaryFormValue,
} from '@/lib/utils/formUtils';

export interface UseResourceFormOptions<T> {
  config: ResourceConfig<T>;
  initialValues: Partial<T>;
  onSubmit: (values: T) => void | Promise<void>;
}

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
  const {
    visibleFields,
    collapsedGroups,
    collapsedGroupFields: _collapsedGroupFields,
  } = useMemo(
    () => computeVisibleFieldsAndGroups(config.fields, formDepth),
    [config.fields, formDepth],
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

  // ── Depth transition effect ──
  const prevCollapsedGroupPathsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const prevPaths = prevCollapsedGroupPathsRef.current;
    const currPaths = new Set(collapsedGroups.map((g) => g.path));
    if (prevPaths.size === 0 && currPaths.size === 0) {
      prevCollapsedGroupPathsRef.current = currPaths;
      return;
    }
    const values = form.getValues() as Record<string, any>;

    for (const group of collapsedGroups) {
      if (!prevPaths.has(group.path)) {
        const val = getByPath(values, group.path);
        if (typeof val !== 'string') {
          const field = config.fields.find((f) => f.name === group.path);
          const jsonStr = collapseFieldToJson(
            val,
            field ?? { name: group.path, label: group.label },
          );
          form.setFieldValue(group.path as any, jsonStr as any);
        }
      }
    }

    for (const prevPath of prevPaths) {
      if (!currPaths.has(prevPath)) {
        const val = getByPath(values, prevPath);
        if (typeof val === 'string') {
          const field = config.fields.find((f) => f.name === prevPath);
          if (field) {
            const expanded = expandFieldFromJson(val, field);
            if (expanded !== undefined) {
              form.setFieldValue(prevPath as any, expanded as any);
            }
          }
        }
      }
    }

    prevCollapsedGroupPathsRef.current = currPaths;
  }, [collapsedGroups]);

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

  // ── Submit ──
  const handleSubmit = async (values: T) => {
    const binaryFieldValues = new Map<string, BinaryFormValue | null>();
    const arrayItemBinaryValues = new Map<string, BinaryFormValue | null>();
    for (const field of config.fields) {
      if (field.type === 'binary') {
        const bv = getByPath(values as Record<string, any>, field.name) as BinaryFormValue | null;
        binaryFieldValues.set(field.name, bv);
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
    }

    const processed = JSON.parse(JSON.stringify(values)) as Record<string, any>;
    const { skippedBinaryFields, binarySubFieldKeys } = processSubmitValues(
      processed,
      config.fields,
      collapsedGroups,
      dateFieldNames,
    );

    for (const key of binarySubFieldKeys) {
      const bv = arrayItemBinaryValues.get(key);
      setByPath(processed, key, await binaryFormValueToApi(bv));
    }
    for (const fieldName of skippedBinaryFields) {
      const bv = binaryFieldValues.get(fieldName);
      setByPath(processed, fieldName, await binaryFormValueToApi(bv));
    }

    if (config.zodSchema) {
      const result = config.zodSchema.safeParse(processed);
      if (!result.success) {
        for (const issue of result.error.issues) {
          form.setFieldError(issue.path.join('.'), issue.message);
        }
        return;
      }
    }

    return onSubmit(processed as T);
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
    setFormDepth,
    visibleFields,
    collapsedGroups,
    simpleUnionTypes,
    setSimpleUnionTypes,
    handleSubmit,
  };
}
