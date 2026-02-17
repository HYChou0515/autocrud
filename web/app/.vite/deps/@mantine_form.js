import {
  require_jsx_runtime
} from "./chunk-LBEETZ2E.js";
import {
  require_react
} from "./chunk-OELA7GPI.js";
import {
  __commonJS,
  __toESM
} from "./chunk-G3PMV62Z.js";

// node_modules/.pnpm/fast-deep-equal@3.1.3/node_modules/fast-deep-equal/index.js
var require_fast_deep_equal = __commonJS({
  "node_modules/.pnpm/fast-deep-equal@3.1.3/node_modules/fast-deep-equal/index.js"(exports, module) {
    "use strict";
    module.exports = function equal(a, b) {
      if (a === b) return true;
      if (a && b && typeof a == "object" && typeof b == "object") {
        if (a.constructor !== b.constructor) return false;
        var length, i, keys;
        if (Array.isArray(a)) {
          length = a.length;
          if (length != b.length) return false;
          for (i = length; i-- !== 0; )
            if (!equal(a[i], b[i])) return false;
          return true;
        }
        if (a.constructor === RegExp) return a.source === b.source && a.flags === b.flags;
        if (a.valueOf !== Object.prototype.valueOf) return a.valueOf() === b.valueOf();
        if (a.toString !== Object.prototype.toString) return a.toString() === b.toString();
        keys = Object.keys(a);
        length = keys.length;
        if (length !== Object.keys(b).length) return false;
        for (i = length; i-- !== 0; )
          if (!Object.prototype.hasOwnProperty.call(b, keys[i])) return false;
        for (i = length; i-- !== 0; ) {
          var key = keys[i];
          if (!equal(a[key], b[key])) return false;
        }
        return true;
      }
      return a !== a && b !== b;
    };
  }
});

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/use-form.mjs
var import_react7 = __toESM(require_react(), 1);

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/actions/actions.mjs
var import_react = __toESM(require_react(), 1);
function dispatchEvent(type, detail) {
  window.dispatchEvent(new CustomEvent(type, { detail }));
}
function validateFormName(name) {
  if (!/^[0-9a-zA-Z-]+$/.test(name)) {
    throw new Error(
      `[@mantine/use-form] Form name "${name}" is invalid, it should contain only letters, numbers and dashes`
    );
  }
}
var useIsomorphicEffect = typeof window !== "undefined" ? import_react.useLayoutEffect : import_react.useEffect;
function createFormActions(name) {
  validateFormName(name);
  const setFieldValue = (path, value) => dispatchEvent(`mantine-form:${name}:set-field-value`, { path, value });
  const setValues = (values) => dispatchEvent(`mantine-form:${name}:set-values`, values);
  const setInitialValues = (values) => dispatchEvent(`mantine-form:${name}:set-initial-values`, values);
  const setErrors = (errors) => dispatchEvent(`mantine-form:${name}:set-errors`, errors);
  const setFieldError = (path, error) => dispatchEvent(`mantine-form:${name}:set-field-error`, { path, error });
  const clearFieldError = (path) => dispatchEvent(`mantine-form:${name}:clear-field-error`, path);
  const clearErrors = () => dispatchEvent(`mantine-form:${name}:clear-errors`);
  const reset = () => dispatchEvent(`mantine-form:${name}:reset`);
  const validate = () => dispatchEvent(`mantine-form:${name}:validate`);
  const validateField = (path) => dispatchEvent(`mantine-form:${name}:validate-field`, path);
  const reorderListItem = (path, payload) => dispatchEvent(`mantine-form:${name}:reorder-list-item`, { path, payload });
  const removeListItem = (path, index) => dispatchEvent(`mantine-form:${name}:remove-list-item`, { path, index });
  const insertListItem = (path, item, index) => dispatchEvent(`mantine-form:${name}:insert-list-item`, { path, index, item });
  const setDirty = (value) => dispatchEvent(`mantine-form:${name}:set-dirty`, value);
  const setTouched = (value) => dispatchEvent(`mantine-form:${name}:set-touched`, value);
  const resetDirty = (values) => dispatchEvent(`mantine-form:${name}:reset-dirty`, values);
  const resetTouched = () => dispatchEvent(`mantine-form:${name}:reset-touched`);
  return {
    setFieldValue,
    setValues,
    setInitialValues,
    setErrors,
    setFieldError,
    clearFieldError,
    clearErrors,
    reset,
    validate,
    validateField,
    reorderListItem,
    removeListItem,
    insertListItem,
    setDirty,
    setTouched,
    resetDirty,
    resetTouched
  };
}
function useFormEvent(eventKey, handler) {
  useIsomorphicEffect(() => {
    if (eventKey) {
      window.addEventListener(eventKey, handler);
      return () => window.removeEventListener(eventKey, handler);
    }
    return void 0;
  }, [eventKey]);
}
function useFormActions(name, form) {
  if (name) {
    validateFormName(name);
  }
  useFormEvent(
    `mantine-form:${name}:set-field-value`,
    (event) => form.setFieldValue(event.detail.path, event.detail.value)
  );
  useFormEvent(
    `mantine-form:${name}:set-values`,
    (event) => form.setValues(event.detail)
  );
  useFormEvent(
    `mantine-form:${name}:set-initial-values`,
    (event) => form.setInitialValues(event.detail)
  );
  useFormEvent(
    `mantine-form:${name}:set-errors`,
    (event) => form.setErrors(event.detail)
  );
  useFormEvent(
    `mantine-form:${name}:set-field-error`,
    (event) => form.setFieldError(event.detail.path, event.detail.error)
  );
  useFormEvent(
    `mantine-form:${name}:clear-field-error`,
    (event) => form.clearFieldError(event.detail)
  );
  useFormEvent(`mantine-form:${name}:clear-errors`, form.clearErrors);
  useFormEvent(`mantine-form:${name}:reset`, form.reset);
  useFormEvent(`mantine-form:${name}:validate`, form.validate);
  useFormEvent(
    `mantine-form:${name}:validate-field`,
    (event) => form.validateField(event.detail)
  );
  useFormEvent(
    `mantine-form:${name}:reorder-list-item`,
    (event) => form.reorderListItem(event.detail.path, event.detail.payload)
  );
  useFormEvent(
    `mantine-form:${name}:remove-list-item`,
    (event) => form.removeListItem(event.detail.path, event.detail.index)
  );
  useFormEvent(
    `mantine-form:${name}:insert-list-item`,
    (event) => form.insertListItem(event.detail.path, event.detail.item, event.detail.index)
  );
  useFormEvent(
    `mantine-form:${name}:set-dirty`,
    (event) => form.setDirty(event.detail)
  );
  useFormEvent(
    `mantine-form:${name}:set-touched`,
    (event) => form.setTouched(event.detail)
  );
  useFormEvent(
    `mantine-form:${name}:reset-dirty`,
    (event) => form.resetDirty(event.detail)
  );
  useFormEvent(`mantine-form:${name}:reset-touched`, form.resetTouched);
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/get-input-on-change/get-input-on-change.mjs
function getInputOnChange(setValue) {
  return (val) => {
    if (!val) {
      setValue(val);
    } else if (typeof val === "function") {
      setValue(val);
    } else if (typeof val === "object" && "nativeEvent" in val) {
      const { currentTarget } = val;
      if (currentTarget instanceof HTMLInputElement) {
        if (currentTarget.type === "checkbox") {
          setValue(currentTarget.checked);
        } else {
          setValue(currentTarget.value);
        }
      } else if (currentTarget instanceof HTMLTextAreaElement || currentTarget instanceof HTMLSelectElement) {
        setValue(currentTarget.value);
      }
    } else {
      setValue(val);
    }
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/hooks/use-form-errors/use-form-errors.mjs
var import_react2 = __toESM(require_react(), 1);

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/hooks/use-form-errors/filter-errors/filter-errors.mjs
function filterErrors(errors) {
  if (errors === null || typeof errors !== "object") {
    return {};
  }
  return Object.keys(errors).reduce((acc, key) => {
    const errorValue = errors[key];
    if (errorValue !== void 0 && errorValue !== null && errorValue !== false) {
      acc[key] = errorValue;
    }
    return acc;
  }, {});
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/hooks/use-form-errors/use-form-errors.mjs
function useFormErrors(initialErrors) {
  const [errorsState, setErrorsState] = (0, import_react2.useState)(filterErrors(initialErrors));
  const errorsRef = (0, import_react2.useRef)(errorsState);
  const setErrors = (0, import_react2.useCallback)((errors) => {
    setErrorsState((current) => {
      const newErrors = filterErrors(typeof errors === "function" ? errors(current) : errors);
      errorsRef.current = newErrors;
      return newErrors;
    });
  }, []);
  const clearErrors = (0, import_react2.useCallback)(() => setErrors({}), []);
  const clearFieldError = (0, import_react2.useCallback)(
    (path) => {
      if (errorsRef.current[path] === void 0) {
        return;
      }
      setErrors((current) => {
        const errors = { ...current };
        delete errors[path];
        return errors;
      });
    },
    [errorsState]
  );
  const setFieldError = (0, import_react2.useCallback)(
    (path, error) => {
      if (error == null || error === false) {
        clearFieldError(path);
      } else if (errorsRef.current[path] !== error) {
        setErrors((current) => ({ ...current, [path]: error }));
      }
    },
    [errorsState]
  );
  return {
    errorsState,
    setErrors,
    clearErrors,
    setFieldError,
    clearFieldError
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/hooks/use-form-list/use-form-list.mjs
var import_react3 = __toESM(require_react(), 1);

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/lists/clear-list-state.mjs
function clearListState(field, state) {
  if (state === null || typeof state !== "object") {
    return {};
  }
  const clone = { ...state };
  Object.keys(state).forEach((errorKey) => {
    if (errorKey.includes(`${String(field)}.`)) {
      delete clone[errorKey];
    }
  });
  return clone;
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/lists/change-error-indices.mjs
function getIndexFromKeyAfterPath(key, path) {
  const split = key.substring(path.length + 1).split(".")[0];
  return parseInt(split, 10);
}
function changeErrorIndices(path, index, errors, change) {
  if (index === void 0) {
    return errors;
  }
  const pathString = `${String(path)}`;
  let clearedErrors = errors;
  if (change === -1) {
    clearedErrors = clearListState(`${pathString}.${index}`, clearedErrors);
  }
  const cloned = { ...clearedErrors };
  const changedKeys = /* @__PURE__ */ new Set();
  Object.entries(clearedErrors).filter(([key]) => {
    if (!key.startsWith(`${pathString}.`)) {
      return false;
    }
    const currIndex = getIndexFromKeyAfterPath(key, pathString);
    if (Number.isNaN(currIndex)) {
      return false;
    }
    return currIndex >= index;
  }).forEach(([key, value]) => {
    const currIndex = getIndexFromKeyAfterPath(key, pathString);
    const newKey = key.replace(
      `${pathString}.${currIndex}`,
      `${pathString}.${currIndex + change}`
    );
    cloned[newKey] = value;
    changedKeys.add(newKey);
    if (!changedKeys.has(key)) {
      delete cloned[key];
    }
  });
  return cloned;
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/lists/reorder-errors.mjs
function reorderErrors(path, { from, to }, errors) {
  const oldKeyStart = `${path}.${from}`;
  const newKeyStart = `${path}.${to}`;
  const clone = { ...errors };
  const processedKeys = /* @__PURE__ */ new Set();
  Object.keys(errors).forEach((key) => {
    if (processedKeys.has(key)) {
      return;
    }
    let oldKey;
    let newKey;
    if (key.startsWith(oldKeyStart)) {
      oldKey = key;
      newKey = key.replace(oldKeyStart, newKeyStart);
    } else if (key.startsWith(newKeyStart)) {
      oldKey = key.replace(newKeyStart, oldKeyStart);
      newKey = key;
    }
    if (oldKey && newKey) {
      const value1 = clone[oldKey];
      const value2 = clone[newKey];
      value2 === void 0 ? delete clone[oldKey] : clone[oldKey] = value2;
      value1 === void 0 ? delete clone[newKey] : clone[newKey] = value1;
      processedKeys.add(oldKey);
      processedKeys.add(newKey);
    }
  });
  return clone;
}

// node_modules/.pnpm/klona@2.0.6/node_modules/klona/full/index.mjs
function set(obj, key, val) {
  if (typeof val.value === "object") val.value = klona(val.value);
  if (!val.enumerable || val.get || val.set || !val.configurable || !val.writable || key === "__proto__") {
    Object.defineProperty(obj, key, val);
  } else obj[key] = val.value;
}
function klona(x) {
  if (typeof x !== "object") return x;
  var i = 0, k, list, tmp, str = Object.prototype.toString.call(x);
  if (str === "[object Object]") {
    tmp = Object.create(x.__proto__ || null);
  } else if (str === "[object Array]") {
    tmp = Array(x.length);
  } else if (str === "[object Set]") {
    tmp = /* @__PURE__ */ new Set();
    x.forEach(function(val) {
      tmp.add(klona(val));
    });
  } else if (str === "[object Map]") {
    tmp = /* @__PURE__ */ new Map();
    x.forEach(function(val, key) {
      tmp.set(klona(key), klona(val));
    });
  } else if (str === "[object Date]") {
    tmp = /* @__PURE__ */ new Date(+x);
  } else if (str === "[object RegExp]") {
    tmp = new RegExp(x.source, x.flags);
  } else if (str === "[object DataView]") {
    tmp = new x.constructor(klona(x.buffer));
  } else if (str === "[object ArrayBuffer]") {
    tmp = x.slice(0);
  } else if (str.slice(-6) === "Array]") {
    tmp = new x.constructor(x);
  }
  if (tmp) {
    for (list = Object.getOwnPropertySymbols(x); i < list.length; i++) {
      set(tmp, list[i], Object.getOwnPropertyDescriptor(x, list[i]));
    }
    for (i = 0, list = Object.getOwnPropertyNames(x); i < list.length; i++) {
      if (Object.hasOwnProperty.call(tmp, k = list[i]) && tmp[k] === x[k]) continue;
      set(tmp, k, Object.getOwnPropertyDescriptor(x, k));
    }
  }
  return tmp || x;
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/paths/get-splitted-path.mjs
function getSplittedPath(path) {
  if (typeof path !== "string") {
    return [];
  }
  return path.split(".");
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/paths/get-path.mjs
function getPath(path, values) {
  const splittedPath = getSplittedPath(path);
  if (splittedPath.length === 0 || typeof values !== "object" || values === null) {
    return void 0;
  }
  let value = values[splittedPath[0]];
  for (let i = 1; i < splittedPath.length; i += 1) {
    if (value == null) {
      break;
    }
    value = value[splittedPath[i]];
  }
  return value;
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/paths/set-path.mjs
function setPath(path, value, values) {
  const splittedPath = getSplittedPath(path);
  if (splittedPath.length === 0) {
    return values;
  }
  const cloned = klona(values);
  if (splittedPath.length === 1) {
    cloned[splittedPath[0]] = value;
    return cloned;
  }
  let val = cloned[splittedPath[0]];
  for (let i = 1; i < splittedPath.length - 1; i += 1) {
    if (val === void 0) {
      return cloned;
    }
    val = val[splittedPath[i]];
  }
  val[splittedPath[splittedPath.length - 1]] = value;
  return cloned;
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/paths/reorder-path.mjs
function reorderPath(path, { from, to }, values) {
  const currentValue = getPath(path, values);
  if (!Array.isArray(currentValue)) {
    return values;
  }
  const cloned = [...currentValue];
  const item = currentValue[from];
  cloned.splice(from, 1);
  cloned.splice(to, 0, item);
  return setPath(path, cloned, values);
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/paths/insert-path.mjs
function insertPath(path, value, index, values) {
  const currentValue = getPath(path, values);
  if (!Array.isArray(currentValue)) {
    return values;
  }
  const cloned = [...currentValue];
  cloned.splice(typeof index === "number" ? index : cloned.length, 0, value);
  return setPath(path, cloned, values);
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/paths/remove-path.mjs
function removePath(path, index, values) {
  const currentValue = getPath(path, values);
  if (!Array.isArray(currentValue)) {
    return values;
  }
  return setPath(
    path,
    currentValue.filter((_, itemIndex) => itemIndex !== index),
    values
  );
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/paths/replace-path.mjs
function replacePath(path, item, index, values) {
  const currentValue = getPath(path, values);
  if (!Array.isArray(currentValue)) {
    return values;
  }
  if (currentValue.length <= index) {
    return values;
  }
  const cloned = [...currentValue];
  cloned[index] = item;
  return setPath(path, cloned, values);
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/hooks/use-form-list/use-form-list.mjs
function useFormList({
  $values,
  $errors,
  $status
}) {
  const reorderListItem = (0, import_react3.useCallback)((path, payload) => {
    $status.clearFieldDirty(path);
    $errors.setErrors((errs) => reorderErrors(path, payload, errs));
    $values.setValues({
      values: reorderPath(path, payload, $values.refValues.current),
      updateState: true
    });
  }, []);
  const removeListItem = (0, import_react3.useCallback)((path, index) => {
    $status.clearFieldDirty(path);
    $errors.setErrors((errs) => changeErrorIndices(path, index, errs, -1));
    $values.setValues({
      values: removePath(path, index, $values.refValues.current),
      updateState: true
    });
  }, []);
  const insertListItem = (0, import_react3.useCallback)((path, item, index) => {
    $status.clearFieldDirty(path);
    $errors.setErrors((errs) => changeErrorIndices(path, index, errs, 1));
    $values.setValues({
      values: insertPath(path, item, index, $values.refValues.current),
      updateState: true
    });
  }, []);
  const replaceListItem = (0, import_react3.useCallback)((path, index, item) => {
    $status.clearFieldDirty(path);
    $values.setValues({
      values: replacePath(path, item, index, $values.refValues.current),
      updateState: true
    });
  }, []);
  return { reorderListItem, removeListItem, insertListItem, replaceListItem };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/hooks/use-form-status/use-form-status.mjs
var import_react4 = __toESM(require_react(), 1);
var import_fast_deep_equal = __toESM(require_fast_deep_equal(), 1);

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/get-status/get-status.mjs
function getStatus(status, path) {
  const paths = Object.keys(status);
  if (typeof path === "string") {
    const nestedPaths = paths.filter((statusPath) => statusPath.startsWith(`${path}.`));
    return status[path] || nestedPaths.some((statusPath) => status[statusPath]) || false;
  }
  return paths.some((statusPath) => status[statusPath]);
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/hooks/use-form-status/use-form-status.mjs
function useFormStatus({
  initialDirty,
  initialTouched,
  mode,
  $values
}) {
  const [touchedState, setTouchedState] = (0, import_react4.useState)(initialTouched);
  const [dirtyState, setDirtyState] = (0, import_react4.useState)(initialDirty);
  const touchedRef = (0, import_react4.useRef)(initialTouched);
  const dirtyRef = (0, import_react4.useRef)(initialDirty);
  const setTouched = (0, import_react4.useCallback)((values) => {
    const resolvedValues = typeof values === "function" ? values(touchedRef.current) : values;
    touchedRef.current = resolvedValues;
    if (mode === "controlled") {
      setTouchedState(resolvedValues);
    }
  }, []);
  const setDirty = (0, import_react4.useCallback)(
    (values, forceUpdate = false) => {
      const resolvedValues = typeof values === "function" ? values(dirtyRef.current) : values;
      dirtyRef.current = resolvedValues;
      if (mode === "controlled" || forceUpdate) {
        setDirtyState(resolvedValues);
      }
    },
    []
  );
  const resetTouched = (0, import_react4.useCallback)(() => setTouched({}), []);
  const resetDirty = (0, import_react4.useCallback)((values) => {
    const newSnapshot = values ? { ...$values.refValues.current, ...values } : $values.refValues.current;
    $values.setValuesSnapshot(newSnapshot);
    setDirty({});
  }, []);
  const setFieldTouched = (0, import_react4.useCallback)((path, touched) => {
    setTouched((currentTouched) => {
      if (getStatus(currentTouched, path) === touched) {
        return currentTouched;
      }
      return { ...currentTouched, [path]: touched };
    });
  }, []);
  const setFieldDirty = (0, import_react4.useCallback)((path, dirty, forceUpdate) => {
    setDirty((currentDirty) => {
      if (getStatus(currentDirty, path) === dirty) {
        return currentDirty;
      }
      return { ...currentDirty, [path]: dirty };
    }, forceUpdate);
  }, []);
  const setCalculatedFieldDirty = (0, import_react4.useCallback)((path, value) => {
    const currentDirty = getStatus(dirtyRef.current, path);
    const dirty = !(0, import_fast_deep_equal.default)(getPath(path, $values.getValuesSnapshot()), value);
    const clearedState = clearListState(path, dirtyRef.current);
    clearedState[path] = dirty;
    setDirty(clearedState, currentDirty !== dirty);
  }, []);
  const isTouched = (0, import_react4.useCallback)(
    (path) => getStatus(touchedRef.current, path),
    []
  );
  const clearFieldDirty = (0, import_react4.useCallback)(
    (path) => setDirty((current) => {
      if (typeof path !== "string") {
        return current;
      }
      const result = clearListState(path, current);
      delete result[path];
      if ((0, import_fast_deep_equal.default)(result, current)) {
        return current;
      }
      return result;
    }),
    []
  );
  const isDirty = (0, import_react4.useCallback)((path) => {
    if (path) {
      const overriddenValue = getPath(path, dirtyRef.current);
      if (typeof overriddenValue === "boolean") {
        return overriddenValue;
      }
      const sliceOfValues = getPath(path, $values.refValues.current);
      const sliceOfInitialValues = getPath(path, $values.valuesSnapshot.current);
      return !(0, import_fast_deep_equal.default)(sliceOfValues, sliceOfInitialValues);
    }
    const isOverridden = Object.keys(dirtyRef.current).length > 0;
    if (isOverridden) {
      return getStatus(dirtyRef.current);
    }
    return !(0, import_fast_deep_equal.default)($values.refValues.current, $values.valuesSnapshot.current);
  }, []);
  const getDirty = (0, import_react4.useCallback)(() => dirtyRef.current, []);
  const getTouched = (0, import_react4.useCallback)(() => touchedRef.current, []);
  return {
    touchedState,
    dirtyState,
    touchedRef,
    dirtyRef,
    setTouched,
    setDirty,
    resetDirty,
    resetTouched,
    isTouched,
    setFieldTouched,
    setFieldDirty,
    setTouchedState,
    setDirtyState,
    clearFieldDirty,
    isDirty,
    getDirty,
    getTouched,
    setCalculatedFieldDirty
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/hooks/use-form-values/use-form-values.mjs
var import_react5 = __toESM(require_react(), 1);
function useFormValues({
  initialValues,
  onValuesChange,
  mode
}) {
  const initialized = (0, import_react5.useRef)(false);
  const [stateValues, setStateValues] = (0, import_react5.useState)(initialValues || {});
  const refValues = (0, import_react5.useRef)(stateValues);
  const valuesSnapshot = (0, import_react5.useRef)(stateValues);
  const setValues = (0, import_react5.useCallback)(
    ({
      values,
      subscribers,
      updateState = true,
      mergeWithPreviousValues = true
    }) => {
      const previousValues = refValues.current;
      const resolvedValues = values instanceof Function ? values(refValues.current) : values;
      const updatedValues = mergeWithPreviousValues ? { ...previousValues, ...resolvedValues } : resolvedValues;
      refValues.current = updatedValues;
      updateState && setStateValues(updatedValues);
      onValuesChange == null ? void 0 : onValuesChange(updatedValues, previousValues);
      subscribers == null ? void 0 : subscribers.filter(Boolean).forEach((subscriber) => subscriber({ updatedValues, previousValues }));
    },
    [onValuesChange]
  );
  const setFieldValue = (0, import_react5.useCallback)(
    (payload) => {
      var _a;
      const currentValue = getPath(payload.path, refValues.current);
      const updatedValue = payload.value instanceof Function ? payload.value(currentValue) : payload.value;
      if (currentValue !== updatedValue) {
        const previousValues = refValues.current;
        const updatedValues = setPath(payload.path, updatedValue, refValues.current);
        setValues({ values: updatedValues, updateState: payload.updateState });
        (_a = payload.subscribers) == null ? void 0 : _a.filter(Boolean).forEach(
          (subscriber) => subscriber({ path: payload.path, updatedValues, previousValues })
        );
      }
    },
    [setValues]
  );
  const setValuesSnapshot = (0, import_react5.useCallback)((payload) => {
    valuesSnapshot.current = payload;
  }, []);
  const initialize = (0, import_react5.useCallback)(
    (values, onInitialize) => {
      if (!initialized.current) {
        initialized.current = true;
        setValues({ values, updateState: mode === "controlled" });
        setValuesSnapshot(values);
        onInitialize();
      }
    },
    [setValues]
  );
  const resetValues = (0, import_react5.useCallback)(() => {
    setValues({
      values: valuesSnapshot.current,
      updateState: true,
      mergeWithPreviousValues: false
    });
  }, [setValues]);
  const getValues = (0, import_react5.useCallback)(() => refValues.current, []);
  const getValuesSnapshot = (0, import_react5.useCallback)(() => valuesSnapshot.current, []);
  return {
    initialized,
    stateValues,
    refValues,
    valuesSnapshot,
    setValues,
    setFieldValue,
    resetValues,
    setValuesSnapshot,
    initialize,
    getValues,
    getValuesSnapshot
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/hooks/use-form-watch/use-form-watch.mjs
var import_react6 = __toESM(require_react(), 1);
function useFormWatch({
  $status
}) {
  const subscribers = (0, import_react6.useRef)(
    {}
  );
  const watch = (0, import_react6.useCallback)((path, callback) => {
    (0, import_react6.useEffect)(() => {
      subscribers.current[path] = subscribers.current[path] || [];
      subscribers.current[path].push(callback);
      return () => {
        subscribers.current[path] = subscribers.current[path].filter((cb) => cb !== callback);
      };
    }, [callback]);
  }, []);
  const getFieldSubscribers = (0, import_react6.useCallback)((path) => {
    if (!subscribers.current[path]) {
      return [];
    }
    return subscribers.current[path].map(
      (callback) => (input) => callback({
        previousValue: getPath(path, input.previousValues),
        value: getPath(path, input.updatedValues),
        touched: $status.isTouched(path),
        dirty: $status.isDirty(path)
      })
    );
  }, []);
  return {
    subscribers,
    watch,
    getFieldSubscribers
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/paths/get-data-path.mjs
function getDataPath(formName, fieldPath) {
  return formName ? `${formName}-${fieldPath.toString()}` : fieldPath.toString();
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/validate/validate-values.mjs
var formRootRule = Symbol("root-rule");
function getValidationResults(errors) {
  const filteredErrors = filterErrors(errors);
  return { hasErrors: Object.keys(filteredErrors).length > 0, errors: filteredErrors };
}
function validateRulesRecord(rules, values, path = "", errors = {}) {
  if (typeof rules !== "object" || rules === null) {
    return errors;
  }
  return Object.keys(rules).reduce((acc, ruleKey) => {
    const rule = rules[ruleKey];
    const rulePath = `${path === "" ? "" : `${path}.`}${ruleKey}`;
    const value = getPath(rulePath, values);
    let arrayValidation = false;
    if (typeof rule === "function") {
      acc[rulePath] = rule(value, values, rulePath);
    }
    if (typeof rule === "object" && Array.isArray(value)) {
      arrayValidation = true;
      value.forEach(
        (_item, index) => validateRulesRecord(rule, values, `${rulePath}.${index}`, acc)
      );
      if (formRootRule in rule) {
        acc[rulePath] = rule[formRootRule](value, values, rulePath);
      }
    }
    if (typeof rule === "object" && typeof value === "object" && value !== null) {
      if (!arrayValidation) {
        validateRulesRecord(rule, values, rulePath, acc);
      }
      if (formRootRule in rule) {
        acc[rulePath] = rule[formRootRule](value, values, rulePath);
      }
    }
    return acc;
  }, errors);
}
function validateValues(validate, values) {
  if (typeof validate === "function") {
    return getValidationResults(validate(values));
  }
  return getValidationResults(validateRulesRecord(validate, values));
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/validate/validate-field-value.mjs
function validateFieldValue(path, rules, values) {
  if (typeof path !== "string") {
    return { hasError: false, error: null };
  }
  const results = validateValues(rules, values);
  const pathInError = Object.keys(results.errors).find(
    (errorKey) => path.split(".").every((pathPart, i) => pathPart === errorKey.split(".")[i])
  );
  return { hasError: !!pathInError, error: pathInError ? results.errors[pathInError] : null };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/form-index.mjs
var FORM_INDEX = "__MANTINE_FORM_INDEX__";

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/validate/should-validate-on-change.mjs
function shouldValidateOnChange(path, validateInputOnChange) {
  if (!validateInputOnChange) {
    return false;
  }
  if (typeof validateInputOnChange === "boolean") {
    return validateInputOnChange;
  }
  if (Array.isArray(validateInputOnChange)) {
    return validateInputOnChange.includes(path.replace(/[.][0-9]+/g, `.${FORM_INDEX}`));
  }
  return false;
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/use-form.mjs
function useForm({
  name,
  mode = "controlled",
  initialValues,
  initialErrors = {},
  initialDirty = {},
  initialTouched = {},
  clearInputErrorOnChange = true,
  validateInputOnChange = false,
  validateInputOnBlur = false,
  onValuesChange,
  transformValues = (values) => values,
  enhanceGetInputProps,
  validate: rules,
  onSubmitPreventDefault = "always",
  touchTrigger = "change"
} = {}) {
  const $errors = useFormErrors(initialErrors);
  const $values = useFormValues({ initialValues, onValuesChange, mode });
  const $status = useFormStatus({ initialDirty, initialTouched, $values, mode });
  const $list = useFormList({ $values, $errors, $status });
  const $watch = useFormWatch({ $status });
  const [formKey, setFormKey] = (0, import_react7.useState)(0);
  const [fieldKeys, setFieldKeys] = (0, import_react7.useState)({});
  const [submitting, setSubmitting] = (0, import_react7.useState)(false);
  const reset = (0, import_react7.useCallback)(() => {
    $values.resetValues();
    $errors.clearErrors();
    $status.resetDirty();
    $status.resetTouched();
    mode === "uncontrolled" && setFormKey((key2) => key2 + 1);
  }, []);
  const handleValuesChanges = (0, import_react7.useCallback)(
    (previousValues) => {
      clearInputErrorOnChange && $errors.clearErrors();
      mode === "uncontrolled" && setFormKey((key2) => key2 + 1);
      Object.keys($watch.subscribers.current).forEach((path) => {
        const value = getPath(path, $values.refValues.current);
        const previousValue = getPath(path, previousValues);
        if (value !== previousValue) {
          $watch.getFieldSubscribers(path).forEach((cb) => cb({ previousValues, updatedValues: $values.refValues.current }));
        }
      });
    },
    [clearInputErrorOnChange]
  );
  const initialize = (0, import_react7.useCallback)(
    (values) => {
      const previousValues = $values.refValues.current;
      $values.initialize(values, () => mode === "uncontrolled" && setFormKey((key2) => key2 + 1));
      handleValuesChanges(previousValues);
    },
    [handleValuesChanges]
  );
  const setFieldValue = (0, import_react7.useCallback)(
    (path, value, options) => {
      const shouldValidate = shouldValidateOnChange(path, validateInputOnChange);
      const resolvedValue = value instanceof Function ? value(getPath(path, $values.refValues.current)) : value;
      $status.setCalculatedFieldDirty(path, resolvedValue);
      touchTrigger === "change" && $status.setFieldTouched(path, true);
      !shouldValidate && clearInputErrorOnChange && $errors.clearFieldError(path);
      $values.setFieldValue({
        path,
        value,
        updateState: mode === "controlled",
        subscribers: [
          ...$watch.getFieldSubscribers(path),
          shouldValidate ? (payload) => {
            const validationResults = validateFieldValue(path, rules, payload.updatedValues);
            validationResults.hasError ? $errors.setFieldError(path, validationResults.error) : $errors.clearFieldError(path);
          } : null,
          (options == null ? void 0 : options.forceUpdate) !== false && mode !== "controlled" ? () => setFieldKeys((keys) => ({
            ...keys,
            [path]: (keys[path] || 0) + 1
          })) : null
        ]
      });
    },
    [onValuesChange, rules]
  );
  const setValues = (0, import_react7.useCallback)(
    (values) => {
      const previousValues = $values.refValues.current;
      $values.setValues({ values, updateState: mode === "controlled" });
      handleValuesChanges(previousValues);
    },
    [onValuesChange, handleValuesChanges]
  );
  const validate = (0, import_react7.useCallback)(() => {
    const results = validateValues(rules, $values.refValues.current);
    $errors.setErrors(results.errors);
    return results;
  }, [rules]);
  const validateField = (0, import_react7.useCallback)(
    (path) => {
      const results = validateFieldValue(path, rules, $values.refValues.current);
      results.hasError ? $errors.setFieldError(path, results.error) : $errors.clearFieldError(path);
      return results;
    },
    [rules]
  );
  const getInputProps = (path, { type = "input", withError = true, withFocus = true, ...otherOptions } = {}) => {
    const onChange = getInputOnChange(
      (value) => setFieldValue(path, value, { forceUpdate: false })
    );
    const payload = { onChange, "data-path": getDataPath(name, path) };
    if (withError) {
      payload.error = $errors.errorsState[path];
    }
    if (type === "checkbox") {
      payload[mode === "controlled" ? "checked" : "defaultChecked"] = getPath(
        path,
        $values.refValues.current
      );
    } else {
      payload[mode === "controlled" ? "value" : "defaultValue"] = getPath(
        path,
        $values.refValues.current
      );
    }
    if (withFocus) {
      payload.onFocus = () => $status.setFieldTouched(path, true);
      payload.onBlur = () => {
        if (shouldValidateOnChange(path, validateInputOnBlur)) {
          const validationResults = validateFieldValue(path, rules, $values.refValues.current);
          validationResults.hasError ? $errors.setFieldError(path, validationResults.error) : $errors.clearFieldError(path);
        }
      };
    }
    return Object.assign(
      payload,
      enhanceGetInputProps == null ? void 0 : enhanceGetInputProps({
        inputProps: payload,
        field: path,
        options: { type, withError, withFocus, ...otherOptions },
        form
      })
    );
  };
  const onSubmit = (handleSubmit, handleValidationFailure) => (event) => {
    if (onSubmitPreventDefault === "always") {
      event == null ? void 0 : event.preventDefault();
    }
    const results = validate();
    if (results.hasErrors) {
      if (onSubmitPreventDefault === "validation-failed") {
        event == null ? void 0 : event.preventDefault();
      }
      handleValidationFailure == null ? void 0 : handleValidationFailure(results.errors, $values.refValues.current, event);
    } else {
      const submitResult = handleSubmit == null ? void 0 : handleSubmit(
        transformValues($values.refValues.current),
        event
      );
      if (submitResult instanceof Promise) {
        setSubmitting(true);
        submitResult.finally(() => setSubmitting(false));
      }
    }
  };
  const getTransformedValues = (input) => transformValues(input || $values.refValues.current);
  const onReset = (0, import_react7.useCallback)((event) => {
    event.preventDefault();
    reset();
  }, []);
  const isValid = (0, import_react7.useCallback)(
    (path) => path ? !validateFieldValue(path, rules, $values.refValues.current).hasError : !validateValues(rules, $values.refValues.current).hasErrors,
    [rules]
  );
  const key = (path) => `${formKey}-${path}-${fieldKeys[path] || 0}`;
  const getInputNode = (0, import_react7.useCallback)(
    (path) => document.querySelector(`[data-path="${getDataPath(name, path)}"]`),
    []
  );
  const form = {
    watch: $watch.watch,
    initialized: $values.initialized.current,
    values: $values.stateValues,
    getValues: $values.getValues,
    getInitialValues: $values.getValuesSnapshot,
    setInitialValues: $values.setValuesSnapshot,
    initialize,
    setValues,
    setFieldValue,
    submitting,
    setSubmitting,
    errors: $errors.errorsState,
    setErrors: $errors.setErrors,
    setFieldError: $errors.setFieldError,
    clearFieldError: $errors.clearFieldError,
    clearErrors: $errors.clearErrors,
    resetDirty: $status.resetDirty,
    setTouched: $status.setTouched,
    setDirty: $status.setDirty,
    isTouched: $status.isTouched,
    resetTouched: $status.resetTouched,
    isDirty: $status.isDirty,
    getTouched: $status.getTouched,
    getDirty: $status.getDirty,
    reorderListItem: $list.reorderListItem,
    insertListItem: $list.insertListItem,
    removeListItem: $list.removeListItem,
    replaceListItem: $list.replaceListItem,
    reset,
    validate,
    validateField,
    getInputProps,
    onSubmit,
    onReset,
    isValid,
    getTransformedValues,
    key,
    getInputNode
  };
  useFormActions(name, form);
  return form;
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/FormProvider/FormProvider.mjs
var import_jsx_runtime = __toESM(require_jsx_runtime(), 1);
var import_react8 = __toESM(require_react(), 1);
function createFormContext() {
  const FormContext = (0, import_react8.createContext)(null);
  function FormProvider({ form, children }) {
    return (0, import_jsx_runtime.jsx)(FormContext.Provider, { value: form, children });
  }
  function useFormContext() {
    const ctx = (0, import_react8.useContext)(FormContext);
    if (!ctx) {
      throw new Error("useFormContext was called outside of FormProvider context");
    }
    return ctx;
  }
  return [FormProvider, useFormContext, useForm];
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/Form/Form.mjs
var import_jsx_runtime2 = __toESM(require_jsx_runtime(), 1);
var import_react9 = __toESM(require_react(), 1);
var Form = (0, import_react9.forwardRef)(
  ({ form, onSubmit, onReset, ...others }, ref) => (0, import_jsx_runtime2.jsx)(
    "form",
    {
      ...others,
      onSubmit: form.onSubmit(typeof onSubmit === "function" ? onSubmit : () => {
      }),
      onReset: (event) => {
        onReset == null ? void 0 : onReset(event);
        form.onReset(event);
      },
      ref
    }
  )
);
Form.displayName = "@mantine/use-form/Form";

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/validators/is-not-empty/is-not-empty.mjs
function isNotEmpty(error) {
  const _error = error || true;
  return (value) => {
    if (typeof value === "string") {
      return value.trim().length > 0 ? null : _error;
    }
    if (Array.isArray(value)) {
      return value.length > 0 ? null : _error;
    }
    if (value === null || value === void 0) {
      return _error;
    }
    if (value === false) {
      return _error;
    }
    return null;
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/validators/matches/matches.mjs
function matches(regexp, error) {
  const _error = error || true;
  return (value) => {
    if (typeof value !== "string") {
      return _error;
    }
    return regexp.test(value) ? null : _error;
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/validators/is-email/is-email.mjs
function isEmail(error) {
  return matches(/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/, error);
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/validators/has-length/has-length.mjs
function isLengthValid(payload, value) {
  if (typeof payload === "number") {
    return value.length === payload;
  }
  const { max, min } = payload;
  let valid = true;
  if (typeof max === "number" && value.length > max) {
    valid = false;
  }
  if (typeof min === "number" && value.length < min) {
    valid = false;
  }
  return valid;
}
function hasLength(payload, error) {
  const _error = error || true;
  return (value) => {
    if (typeof value === "string") {
      return isLengthValid(payload, value.trim()) ? null : _error;
    }
    if (typeof value === "object" && value !== null && "length" in value) {
      return isLengthValid(payload, value) ? null : _error;
    }
    return _error;
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/validators/is-in-range/is-in-range.mjs
function isInRange({ min, max }, error) {
  const _error = error || true;
  return (value) => {
    if (typeof value !== "number") {
      return _error;
    }
    let valid = true;
    if (typeof min === "number" && value < min) {
      valid = false;
    }
    if (typeof max === "number" && value > max) {
      valid = false;
    }
    return valid ? null : _error;
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/validators/matches-field/matches-field.mjs
function matchesField(field, error) {
  const _error = error || true;
  return (value, values) => {
    if (!values || !(field in values)) {
      return _error;
    }
    return value === values[field] ? null : _error;
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/validators/is-not-empty-html/is-not-empty-html.mjs
function removeHtmlTags(input) {
  return input.replace(/<\/?[^>]+(>|$)/g, "");
}
function isNotEmptyHTML(error) {
  const _error = error || true;
  return (value) => {
    if (typeof value === "string") {
      return removeHtmlTags(value).trim().length > 0 ? null : _error;
    }
    return _error;
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/validators/is-json-string/is-json-string.mjs
function isJSONString(error) {
  const _error = error || true;
  return (value) => {
    if (typeof value === "string") {
      try {
        JSON.parse(value);
        return null;
      } catch (e) {
        return _error;
      }
    }
    return _error;
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/use-field.mjs
var import_react10 = __toESM(require_react(), 1);
function useField({
  mode = "controlled",
  clearErrorOnChange = true,
  initialValue,
  initialError = null,
  initialTouched = false,
  onValueChange,
  validateOnChange = false,
  validateOnBlur = false,
  validate,
  resolveValidationError,
  type = "input"
}) {
  const [valueState, setValueState] = (0, import_react10.useState)(initialValue);
  const valueRef = (0, import_react10.useRef)(valueState);
  const [key, setKey] = (0, import_react10.useState)(0);
  const [error, setError] = (0, import_react10.useState)(initialError || null);
  const touchedRef = (0, import_react10.useRef)(initialTouched || false);
  const [, setTouchedState] = (0, import_react10.useState)(touchedRef.current);
  const [isValidating, setIsValidating] = (0, import_react10.useState)(false);
  const errorResolver = (0, import_react10.useMemo)(
    () => resolveValidationError || ((err) => err),
    [resolveValidationError]
  );
  const setTouched = (0, import_react10.useCallback)((val, { updateState = mode === "controlled" } = {}) => {
    touchedRef.current = val;
    updateState && setTouchedState(val);
  }, []);
  const setValue = (0, import_react10.useCallback)(
    (value, {
      updateKey = mode === "uncontrolled",
      updateState = mode === "controlled"
    } = {}) => {
      if (valueRef.current === value) {
        return;
      }
      valueRef.current = value;
      onValueChange == null ? void 0 : onValueChange(value);
      if (clearErrorOnChange && error !== null) {
        setError(null);
      }
      if (updateState) {
        setValueState(value);
      }
      if (updateKey) {
        setKey((currentKey) => currentKey + 1);
      }
      if (validateOnChange) {
        _validate();
      }
    },
    [error, clearErrorOnChange, onValueChange]
  );
  const reset = (0, import_react10.useCallback)(() => {
    setValue(initialValue);
    setError(null);
    setTouched(false);
  }, [initialValue]);
  const getValue = (0, import_react10.useCallback)(() => valueRef.current, []);
  const isTouched = (0, import_react10.useCallback)(() => touchedRef.current, []);
  const isDirty = (0, import_react10.useCallback)(() => valueRef.current !== initialValue, [initialValue]);
  const _validate = (0, import_react10.useCallback)(async () => {
    const validationResult = validate == null ? void 0 : validate(valueRef.current);
    if (validationResult instanceof Promise) {
      setIsValidating(true);
      try {
        const result = await validationResult;
        setIsValidating(false);
        setError(result);
      } catch (err) {
        setIsValidating(false);
        const resolvedError = errorResolver(err);
        setError(resolvedError);
        return resolvedError;
      }
    } else {
      setError(validationResult);
      return validationResult;
    }
  }, []);
  const getInputProps = ({ withError = true, withFocus = true } = {}) => {
    const onChange = getInputOnChange((val) => setValue(val, { updateKey: false }));
    const payload = { onChange };
    if (withError) {
      payload.error = error;
    }
    if (type === "checkbox") {
      payload[mode === "controlled" ? "checked" : "defaultChecked"] = valueRef.current;
    } else {
      payload[mode === "controlled" ? "value" : "defaultValue"] = valueRef.current;
    }
    if (withFocus) {
      payload.onFocus = () => {
        setTouched(true);
      };
      payload.onBlur = () => {
        if (shouldValidateOnChange("", !!validateOnBlur)) {
          _validate();
        }
      };
    }
    return payload;
  };
  const resetTouched = (0, import_react10.useCallback)(() => setTouched(false), []);
  return {
    key,
    getValue,
    setValue,
    reset,
    getInputProps,
    isValidating,
    validate: _validate,
    error,
    setError,
    isTouched,
    isDirty,
    resetTouched
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/resolvers/zod-resolver/zod-resolver.mjs
function zodResolver(schema) {
  return (values) => {
    const parsed = schema.safeParse(values);
    if (parsed.success) {
      return {};
    }
    const results = {};
    parsed.error.errors.forEach((error) => {
      results[error.path.join(".")] = error.message;
    });
    return results;
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/resolvers/superstruct-resolver/superstruct-resolver.mjs
function superstructResolver(schema) {
  function structValidation(values) {
    const formErrors = {};
    const [err] = schema.validate(values);
    if (!err) {
      return formErrors;
    }
    err.failures().forEach((fieldFailure) => {
      const fieldName = fieldFailure.path.join(" ");
      formErrors[fieldFailure.path.join(".")] = `${fieldName}: ${fieldFailure.message}`;
    });
    return formErrors;
  }
  return structValidation;
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/resolvers/yup-resolver/yup-resolver.mjs
function yupResolver(schema) {
  const _schema = schema;
  return (values) => {
    try {
      _schema.validateSync(values, { abortEarly: false });
      return {};
    } catch (_yupError) {
      const yupError = _yupError;
      const results = {};
      yupError.inner.forEach((error) => {
        results[error.path.replaceAll("[", ".").replaceAll("]", "")] = error.message;
      });
      return results;
    }
  };
}

// node_modules/.pnpm/@mantine+form@7.17.8_react@18.3.1/node_modules/@mantine/form/esm/resolvers/joi-resolver/joi-resolver.mjs
function joiResolver(schema, options) {
  const _schema = schema;
  return (values) => {
    const parsed = _schema.validate(values, { abortEarly: false, ...options });
    if (!parsed.error) {
      return {};
    }
    const results = {};
    parsed.error.details.forEach((error) => {
      results[error.path.join(".")] = error.message;
    });
    return results;
  };
}
export {
  FORM_INDEX,
  Form,
  createFormActions,
  createFormContext,
  formRootRule,
  hasLength,
  isEmail,
  isInRange,
  isJSONString,
  isNotEmpty,
  isNotEmptyHTML,
  joiResolver,
  matches,
  matchesField,
  superstructResolver,
  useField,
  useForm,
  yupResolver,
  zodResolver
};
//# sourceMappingURL=@mantine_form.js.map
