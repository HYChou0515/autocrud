/**
 * revisionList — unit tests for all exported pure functions.
 *
 * Covers:
 * - getRevisionId: returns revision_id or uid
 * - hasRevisionId: checks if revision exists in list
 * - mergeRevisionsUnique: merges without duplicates
 * - ensureRevisionInList: adds revision if not present
 * - toRevisionFromInfo: converts RevisionInfo to Revision
 */

import { describe, it, expect } from 'vitest';
import {
  getRevisionId,
  hasRevisionId,
  mergeRevisionsUnique,
  ensureRevisionInList,
  toRevisionFromInfo,
} from './revisionList';
import type { Revision } from '../types/revision';

// ---------------------------------------------------------------------------
// getRevisionId
// ---------------------------------------------------------------------------

describe('getRevisionId', () => {
  it('returns revision_id when present', () => {
    expect(getRevisionId({ revision_id: 'rev-1' })).toBe('rev-1');
  });

  it('returns uid when revision_id is undefined', () => {
    expect(getRevisionId({ uid: 'uid-1' })).toBe('uid-1');
  });

  it('returns undefined when neither is present', () => {
    expect(getRevisionId({})).toBeUndefined();
  });

  it('prefers revision_id over uid', () => {
    expect(getRevisionId({ revision_id: 'rev-1', uid: 'uid-1' })).toBe('rev-1');
  });
});

// ---------------------------------------------------------------------------
// hasRevisionId
// ---------------------------------------------------------------------------

describe('hasRevisionId', () => {
  const revisions: Revision[] = [{ revision_id: 'rev-1' }, { uid: 'uid-2' }];

  it('returns true when revision is in list', () => {
    expect(hasRevisionId(revisions, 'rev-1')).toBe(true);
    expect(hasRevisionId(revisions, 'uid-2')).toBe(true);
  });

  it('returns false when revision is not in list', () => {
    expect(hasRevisionId(revisions, 'rev-99')).toBe(false);
  });

  it('returns false for empty list', () => {
    expect(hasRevisionId([], 'rev-1')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// mergeRevisionsUnique
// ---------------------------------------------------------------------------

describe('mergeRevisionsUnique', () => {
  it('merges without duplicates', () => {
    const base: Revision[] = [{ revision_id: 'rev-1' }, { revision_id: 'rev-2' }];
    const extra: Revision[] = [{ revision_id: 'rev-2' }, { revision_id: 'rev-3' }];
    const result = mergeRevisionsUnique(base, extra);
    expect(result).toHaveLength(3);
    expect(result.map((r) => r.revision_id)).toEqual(['rev-1', 'rev-2', 'rev-3']);
  });

  it('handles empty base', () => {
    const extra: Revision[] = [{ revision_id: 'rev-1' }];
    expect(mergeRevisionsUnique([], extra)).toHaveLength(1);
  });

  it('handles empty extra', () => {
    const base: Revision[] = [{ revision_id: 'rev-1' }];
    expect(mergeRevisionsUnique(base, [])).toHaveLength(1);
  });

  it('skips revisions without id', () => {
    const base: Revision[] = [{ revision_id: 'rev-1' }];
    const extra: Revision[] = [{}];
    expect(mergeRevisionsUnique(base, extra)).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// ensureRevisionInList
// ---------------------------------------------------------------------------

describe('ensureRevisionInList', () => {
  const existing: Revision[] = [{ revision_id: 'rev-1' }];

  it('returns list unchanged if revision is undefined', () => {
    expect(ensureRevisionInList(existing)).toBe(existing);
  });

  it('returns list unchanged if revision has no id', () => {
    expect(ensureRevisionInList(existing, {})).toBe(existing);
  });

  it('returns list unchanged if revision already exists', () => {
    expect(ensureRevisionInList(existing, { revision_id: 'rev-1' })).toBe(existing);
  });

  it('appends revision when not in list', () => {
    const result = ensureRevisionInList(existing, { revision_id: 'rev-2' });
    expect(result).toHaveLength(2);
    expect(result[1].revision_id).toBe('rev-2');
  });
});

// ---------------------------------------------------------------------------
// toRevisionFromInfo
// ---------------------------------------------------------------------------

describe('toRevisionFromInfo', () => {
  it('converts RevisionInfo fields correctly', () => {
    const info = {
      revision_id: 'rev-1',
      uid: 'uid-1',
      status: 'stable',
      created_time: '2024-01-01T00:00:00',
      updated_time: '2024-01-02T00:00:00',
      created_by: 'user1',
      updated_by: 'user2',
      parent_revision_id: 'rev-0',
    };
    const result = toRevisionFromInfo(info as any);
    expect(result).toEqual({
      revision_id: 'rev-1',
      uid: 'uid-1',
      status: 'stable',
      created_time: '2024-01-01T00:00:00',
      updated_time: '2024-01-02T00:00:00',
      created_by: 'user1',
      updated_by: 'user2',
      parent_revision_id: 'rev-0',
    });
  });

  it('handles missing optional fields', () => {
    const info = {
      revision_id: 'rev-1',
      uid: 'uid-1',
      status: 'draft',
      created_time: '2024-01-01T00:00:00',
      updated_time: '2024-01-01T00:00:00',
      created_by: 'system',
      updated_by: 'system',
      parent_revision_id: null,
    };
    const result = toRevisionFromInfo(info as any);
    expect(result.parent_revision_id).toBeNull();
  });
});
