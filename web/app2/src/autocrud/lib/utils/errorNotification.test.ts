/**
 * errorNotification — unit tests for all three exported functions.
 *
 * Covers:
 * - extractErrorMessage: all code paths (no data, string detail, array detail, status fallback, generic fallback)
 * - extractUniqueConflict: 409 with field, non-409, string detail, missing field
 * - showErrorNotification: calls notifications.show with correct params
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock @mantine/notifications
const mockShow = vi.hoisted(() => vi.fn());
vi.mock('@mantine/notifications', () => ({
  notifications: { show: mockShow },
}));

import {
  extractErrorMessage,
  extractUniqueConflict,
  showErrorNotification,
} from './errorNotification';

beforeEach(() => {
  mockShow.mockClear();
});

// ---------------------------------------------------------------------------
// extractErrorMessage
// ---------------------------------------------------------------------------

describe('extractErrorMessage', () => {
  it('returns generic message for unknown error', () => {
    expect(extractErrorMessage({})).toBe('An unexpected error occurred');
  });

  it('returns axios message when no response data', () => {
    const error = { message: 'Network Error' };
    expect(extractErrorMessage(error)).toBe('Network Error');
  });

  it('returns status-based message when response has no detail', () => {
    const error = { response: { status: 500, data: {} } };
    expect(extractErrorMessage(error)).toBe('Request failed with status 500');
  });

  it('returns string detail from HTTPException', () => {
    const error = { response: { status: 400, data: { detail: 'Bad request' } } };
    expect(extractErrorMessage(error)).toBe('Bad request');
  });

  it('formats array detail from ValidationError', () => {
    const error = {
      response: {
        status: 422,
        data: {
          detail: [
            { loc: ['body', 'name'], msg: 'field required', type: 'missing' },
            { loc: ['body', 'age'], msg: 'must be positive', type: 'value_error' },
          ],
        },
      },
    };
    const msg = extractErrorMessage(error);
    expect(msg).toContain('name: field required');
    expect(msg).toContain('age: must be positive');
  });

  it('handles validation error with only "body" in loc', () => {
    const error = {
      response: {
        status: 422,
        data: {
          detail: [{ loc: ['body'], msg: 'invalid', type: 'value_error' }],
        },
      },
    };
    expect(extractErrorMessage(error)).toContain('(root): invalid');
  });

  it('handles non-array non-string detail', () => {
    const error = {
      response: { status: 400, data: { detail: 12345 } },
    };
    expect(extractErrorMessage(error)).toBe('An unexpected error occurred');
  });

  it('returns generic message for null error', () => {
    expect(extractErrorMessage(null)).toBe('An unexpected error occurred');
  });
});

// ---------------------------------------------------------------------------
// extractUniqueConflict
// ---------------------------------------------------------------------------

describe('extractUniqueConflict', () => {
  it('returns conflict info for 409 with field', () => {
    const error = {
      response: {
        status: 409,
        data: {
          detail: {
            message: 'Username taken',
            field: 'username',
            conflicting_resource_id: 'abc-123',
          },
        },
      },
    };
    const result = extractUniqueConflict(error);
    expect(result).toEqual({
      field: 'username',
      message: 'Username taken',
      conflictingResourceId: 'abc-123',
    });
  });

  it('returns null for non-409 status', () => {
    const error = { response: { status: 400, data: { detail: { field: 'name' } } } };
    expect(extractUniqueConflict(error)).toBeNull();
  });

  it('returns null when detail is string', () => {
    const error = { response: { status: 409, data: { detail: 'conflict' } } };
    expect(extractUniqueConflict(error)).toBeNull();
  });

  it('returns null when detail has no field', () => {
    const error = { response: { status: 409, data: { detail: { message: 'conflict' } } } };
    expect(extractUniqueConflict(error)).toBeNull();
  });

  it('uses default message when message is missing', () => {
    const error = {
      response: { status: 409, data: { detail: { field: 'email' } } },
    };
    const result = extractUniqueConflict(error);
    expect(result?.message).toBe('Value already exists for field "email"');
  });

  it('returns null when detail is null', () => {
    const error = { response: { status: 409, data: { detail: null } } };
    expect(extractUniqueConflict(error)).toBeNull();
  });

  it('returns null for non-object error', () => {
    expect(extractUniqueConflict(null)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// showErrorNotification
// ---------------------------------------------------------------------------

describe('showErrorNotification', () => {
  it('calls notifications.show with extracted message', () => {
    const error = { response: { status: 400, data: { detail: 'Bad request' } } };
    showErrorNotification(error);
    expect(mockShow).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Operation Failed',
        message: 'Bad request',
        color: 'red',
      }),
    );
  });

  it('uses custom title', () => {
    showErrorNotification({}, 'Custom Title');
    expect(mockShow).toHaveBeenCalledWith(expect.objectContaining({ title: 'Custom Title' }));
  });
});
