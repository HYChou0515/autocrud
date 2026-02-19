/**
 * Tests for Job section components' shared logic.
 *
 * Since JobStatusSection and JobFieldsSection are React components,
 * these tests focus on the exported constants and filtering logic.
 */

import { describe, it, expect } from 'vitest';
import { JOB_STATUS_FIELDS } from '../../job/JobStatusSection';

describe('JOB_STATUS_FIELDS', () => {
  it('contains all expected job status field names', () => {
    const expected = [
      'status',
      'retries',
      'errmsg',
      'periodic_interval_seconds',
      'periodic_max_runs',
      'periodic_runs',
      'periodic_initial_delay_seconds',
    ];
    for (const name of expected) {
      expect(JOB_STATUS_FIELDS.has(name), `Missing field: ${name}`).toBe(true);
    }
    expect(JOB_STATUS_FIELDS.size).toBe(expected.length);
  });

  it('does not contain non-status fields', () => {
    expect(JOB_STATUS_FIELDS.has('payload')).toBe(false);
    expect(JOB_STATUS_FIELDS.has('name')).toBe(false);
    expect(JOB_STATUS_FIELDS.has('id')).toBe(false);
  });

  it('correctly filters job data fields from visible fields', () => {
    // Simulate the filtering logic used in ResourceDetail
    const allFields = [
      { name: 'status' },
      { name: 'retries' },
      { name: 'name' },
      { name: 'description' },
      { name: 'periodic_interval_seconds' },
    ];

    const dataFields = allFields.filter((f) => !JOB_STATUS_FIELDS.has(f.name));
    expect(dataFields).toEqual([{ name: 'name' }, { name: 'description' }]);
  });
});
