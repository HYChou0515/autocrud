/**
 * Payload truncation utilities — limits the size of large objects/arrays
 * before rendering to prevent the browser from freezing.
 *
 * Two main concerns:
 * 1. **Too many attributes** — an object with hundreds of keys slows down
 *    both JSON.stringify and DOM rendering.
 * 2. **Very large attribute values** — a single string of several MB
 *    (e.g. base64 blob) can freeze the UI.
 *
 * The {@link truncatePayload} function recursively walks a value and returns
 * a shallow-truncated copy suitable for display purposes.
 */

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

export interface TruncateOptions {
  /** Maximum number of keys to keep per object level. Default: 50 */
  maxKeys?: number;
  /** Maximum string length (chars) before truncation. Default: 10_000 */
  maxStringLength?: number;
  /** Maximum array items to keep. Default: 50 */
  maxArrayItems?: number;
  /** Maximum recursion depth. Default: 6 */
  maxDepth?: number;
}

/** Preset for table cells — very aggressive truncation. */
export const CELL_TRUNCATE_OPTIONS: Required<TruncateOptions> = {
  maxKeys: 10,
  maxStringLength: 200,
  maxArrayItems: 5,
  maxDepth: 3,
};

/** Preset for detail pages — moderate truncation. */
export const DETAIL_TRUNCATE_OPTIONS: Required<TruncateOptions> = {
  maxKeys: 50,
  maxStringLength: 10_000,
  maxArrayItems: 50,
  maxDepth: 8,
};

const DEFAULT_OPTIONS: Required<TruncateOptions> = DETAIL_TRUNCATE_OPTIONS;

// ---------------------------------------------------------------------------
// Sentinel value used by renderers to display "… and N more" labels
// ---------------------------------------------------------------------------

/**
 * A special marker appended when keys or array items are omitted.
 * Renderers can check for this to show a human-readable note.
 */
export const TRUNCATION_MARKER = '__truncated__';

export interface TruncationInfo {
  /** Total number of entries before truncation. */
  total: number;
  /** Number of entries that were omitted. */
  omitted: number;
}

// ---------------------------------------------------------------------------
// Core function
// ---------------------------------------------------------------------------

/**
 * Recursively truncate a value so it can be safely stringified and rendered.
 *
 * - Objects with too many keys → keeps first `maxKeys`, appends marker.
 * - Arrays that are too long → keeps first `maxArrayItems`, appends marker.
 * - Strings that are too long → slices and appends "…[truncated]".
 * - Recursion beyond `maxDepth` → returns `"[nested object]"` / `"[nested array]"`.
 *
 * The original value is **never mutated** — a new structure is returned.
 */
export function truncatePayload(
  value: unknown,
  options?: TruncateOptions,
  _depth: number = 0,
): unknown {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  // Primitives pass through
  if (value == null || typeof value === 'boolean' || typeof value === 'number') {
    return value;
  }

  // Strings — truncate if too long
  if (typeof value === 'string') {
    if (value.length > opts.maxStringLength) {
      const truncatedKB = Math.round(value.length / 1024);
      return value.slice(0, opts.maxStringLength) + `…[truncated — ${truncatedKB} KB total]`;
    }
    return value;
  }

  // Depth guard
  if (_depth >= opts.maxDepth) {
    if (Array.isArray(value)) return `[Array(${value.length})]`;
    if (typeof value === 'object') return `[Object(${Object.keys(value as object).length} keys)]`;
    return String(value);
  }

  // Arrays — truncate length, then recurse
  if (Array.isArray(value)) {
    const truncated = value.length > opts.maxArrayItems;
    const items = value
      .slice(0, opts.maxArrayItems)
      .map((item) => truncatePayload(item, opts, _depth + 1));
    if (truncated) {
      const info: TruncationInfo = {
        total: value.length,
        omitted: value.length - opts.maxArrayItems,
      };
      // Store truncation metadata as a special last element
      return [...items, { [TRUNCATION_MARKER]: info }];
    }
    return items;
  }

  // Objects — truncate keys, then recurse values
  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj);
    const truncated = keys.length > opts.maxKeys;
    const keptKeys = truncated ? keys.slice(0, opts.maxKeys) : keys;

    const result: Record<string, unknown> = {};
    for (const key of keptKeys) {
      result[key] = truncatePayload(obj[key], opts, _depth + 1);
    }

    if (truncated) {
      const info: TruncationInfo = { total: keys.length, omitted: keys.length - opts.maxKeys };
      result[TRUNCATION_MARKER] = info;
    }

    return result;
  }

  return value;
}

// ---------------------------------------------------------------------------
// Convenience wrappers
// ---------------------------------------------------------------------------

/** Truncate for table cell display (aggressive). */
export function truncateForCell(value: unknown): unknown {
  return truncatePayload(value, CELL_TRUNCATE_OPTIONS);
}

/** Truncate for detail page display (moderate). */
export function truncateForDetail(value: unknown): unknown {
  return truncatePayload(value, DETAIL_TRUNCATE_OPTIONS);
}
