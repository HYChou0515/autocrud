/**
 * queryKeys — Tests for the resource query key factory.
 *
 * Verifies:
 * - Key structure and hierarchy
 * - Key uniqueness across different inputs
 * - Referential stability (same input → same array structure)
 * - Optional parameters (revisionId) affect key shape
 */

import { describe, it, expect } from 'vitest';
import { resourceKeys } from './queryKeys';

describe('resourceKeys', () => {
  describe('all', () => {
    it('produces ["resource", name]', () => {
      expect(resourceKeys.all('character')).toEqual(['resource', 'character']);
    });

    it('different names produce different keys', () => {
      expect(resourceKeys.all('character')).not.toEqual(resourceKeys.all('weapon'));
    });
  });

  describe('lists', () => {
    it('produces ["resource", name, "list"]', () => {
      expect(resourceKeys.lists('character')).toEqual(['resource', 'character', 'list']);
    });

    it('is a prefix of list(name, params)', () => {
      const listsKey = resourceKeys.lists('character');
      const listKey = resourceKeys.list('character', { limit: 10 });
      expect(listKey.slice(0, 3)).toEqual(listsKey);
    });
  });

  describe('list', () => {
    it('produces ["resource", name, "list", params]', () => {
      const params = { limit: 10, offset: 20 };
      expect(resourceKeys.list('character', params)).toEqual([
        'resource',
        'character',
        'list',
        params,
      ]);
    });

    it('defaults to empty params', () => {
      expect(resourceKeys.list('character')).toEqual(['resource', 'character', 'list', {}]);
    });

    it('different params produce different keys', () => {
      const key1 = resourceKeys.list('character', { limit: 10 });
      const key2 = resourceKeys.list('character', { limit: 20 });
      expect(key1).not.toEqual(key2);
    });
  });

  describe('details', () => {
    it('produces ["resource", name, "detail"]', () => {
      expect(resourceKeys.details('character')).toEqual(['resource', 'character', 'detail']);
    });
  });

  describe('detail', () => {
    it('produces ["resource", name, "detail", id] without revisionId', () => {
      expect(resourceKeys.detail('character', 'abc-123')).toEqual([
        'resource',
        'character',
        'detail',
        'abc-123',
      ]);
    });

    it('produces ["resource", name, "detail", id, revisionId] with revisionId', () => {
      expect(resourceKeys.detail('character', 'abc-123', 'rev-456')).toEqual([
        'resource',
        'character',
        'detail',
        'abc-123',
        'rev-456',
      ]);
    });

    it('null revisionId omits the 5th element', () => {
      expect(resourceKeys.detail('character', 'abc-123', null)).toEqual([
        'resource',
        'character',
        'detail',
        'abc-123',
      ]);
    });

    it('undefined revisionId omits the 5th element', () => {
      expect(resourceKeys.detail('character', 'abc-123', undefined)).toEqual([
        'resource',
        'character',
        'detail',
        'abc-123',
      ]);
    });
  });

  describe('revisions', () => {
    it('produces ["resource", name, "revisions", id]', () => {
      expect(resourceKeys.revisions('character', 'abc-123')).toEqual([
        'resource',
        'character',
        'revisions',
        'abc-123',
      ]);
    });
  });

  describe('logs', () => {
    it('produces ["resource", name, "logs", id]', () => {
      expect(resourceKeys.logs('my-job', 'job-123')).toEqual([
        'resource',
        'my-job',
        'logs',
        'job-123',
      ]);
    });
  });

  describe('hierarchy', () => {
    it('all() is a prefix of lists()', () => {
      const allKey = resourceKeys.all('x');
      const listsKey = resourceKeys.lists('x');
      expect(listsKey.slice(0, allKey.length)).toEqual(allKey);
    });

    it('all() is a prefix of details()', () => {
      const allKey = resourceKeys.all('x');
      const detailsKey = resourceKeys.details('x');
      expect(detailsKey.slice(0, allKey.length)).toEqual(allKey);
    });

    it('all() is a prefix of revisions()', () => {
      const allKey = resourceKeys.all('x');
      const revsKey = resourceKeys.revisions('x', 'id1');
      expect(revsKey.slice(0, allKey.length)).toEqual(allKey);
    });

    it('all() is a prefix of logs()', () => {
      const allKey = resourceKeys.all('x');
      const logsKey = resourceKeys.logs('x', 'id1');
      expect(logsKey.slice(0, allKey.length)).toEqual(allKey);
    });
  });
});
