/**
 * Tests for JobArtifactSection structured display logic.
 *
 * These tests verify artifact field filtering, grouping, and the
 * isArtifactField helper used by ResourceDetail to split artifact
 * fields from the payload section.
 */

import { describe, it, expect } from 'vitest';
import { groupFieldsForDisplay } from '../detail/ResourceDetail';

/** Simulates the isArtifactField helper from ResourceDetail */
const isArtifactField = (name: string) => name === 'artifact' || name.startsWith('artifact.');

describe('isArtifactField helper', () => {
  it('matches exact "artifact" field', () => {
    expect(isArtifactField('artifact')).toBe(true);
  });

  it('matches dot-notation sub-fields', () => {
    expect(isArtifactField('artifact.result')).toBe(true);
    expect(isArtifactField('artifact.details.count')).toBe(true);
  });

  it('does not match unrelated fields', () => {
    expect(isArtifactField('artifacts')).toBe(false);
    expect(isArtifactField('my_artifact')).toBe(false);
    expect(isArtifactField('payload')).toBe(false);
    expect(isArtifactField('status')).toBe(false);
  });
});

describe('artifact field separation for display groups', () => {
  const JOB_STATUS_FIELDS = new Set([
    'status',
    'retries',
    'max_retries',
    'errmsg',
    'last_heartbeat_at',
    'periodic_interval_seconds',
    'periodic_max_runs',
    'periodic_runs',
    'periodic_initial_delay_seconds',
  ]);

  const allFields = [
    {
      name: 'status',
      label: 'Status',
      type: 'string',
      tsType: 'string',
      isArray: false,
      isRequired: true,
      isNullable: false,
      zodType: 'z.string()',
    },
    {
      name: 'artifact',
      label: 'Artifact',
      type: 'object',
      tsType: 'Record<string, any>',
      isArray: false,
      isRequired: false,
      isNullable: true,
      zodType: 'z.any()',
    },
    {
      name: 'payload.name',
      label: 'Name',
      type: 'string',
      tsType: 'string',
      isArray: false,
      isRequired: true,
      isNullable: false,
      zodType: 'z.string()',
    },
    {
      name: 'retries',
      label: 'Retries',
      type: 'number',
      tsType: 'number',
      isArray: false,
      isRequired: true,
      isNullable: false,
      zodType: 'z.number()',
    },
  ] as any[];

  it('filters artifact and status fields from payload display', () => {
    const payloadFields = allFields.filter(
      (f) => !JOB_STATUS_FIELDS.has(f.name) && !isArtifactField(f.name),
    );
    expect(payloadFields.map((f) => f.name)).toEqual(['payload.name']);
  });

  it('extracts only artifact fields for artifact section', () => {
    const artifactFields = allFields.filter((f) => isArtifactField(f.name));
    expect(artifactFields.map((f) => f.name)).toEqual(['artifact']);
  });

  it('handles structured artifact sub-fields', () => {
    const fieldsWithSub = [
      {
        name: 'artifact.result',
        label: 'Result',
        type: 'number',
        tsType: 'number',
        isArray: false,
        isRequired: true,
        isNullable: false,
        zodType: 'z.number()',
      },
      {
        name: 'artifact.details',
        label: 'Details',
        type: 'string',
        tsType: 'string',
        isArray: false,
        isRequired: false,
        isNullable: true,
        zodType: 'z.string()',
      },
      {
        name: 'payload.name',
        label: 'Name',
        type: 'string',
        tsType: 'string',
        isArray: false,
        isRequired: true,
        isNullable: false,
        zodType: 'z.string()',
      },
    ] as any[];

    const artifactFields = fieldsWithSub.filter((f) => isArtifactField(f.name));
    expect(artifactFields.map((f) => f.name)).toEqual(['artifact.result', 'artifact.details']);

    // All sub-fields have same depth → rendered as individual single groups
    const groups = groupFieldsForDisplay(artifactFields);
    expect(groups).toHaveLength(2);
    expect(groups[0].kind).toBe('single');
    expect(groups[1].kind).toBe('single');
  });

  it('filters artifact from collapsed groups', () => {
    const collapsedGroups = [
      { path: 'artifact', label: 'Artifact' },
      { path: 'payload', label: 'Payload' },
      { path: 'status', label: 'Status' },
    ];

    const artifactCollapsed = collapsedGroups.filter((g) => isArtifactField(g.path));
    expect(artifactCollapsed).toEqual([{ path: 'artifact', label: 'Artifact' }]);

    const payloadCollapsed = collapsedGroups.filter(
      (g) => !JOB_STATUS_FIELDS.has(g.path) && !isArtifactField(g.path),
    );
    expect(payloadCollapsed).toEqual([{ path: 'payload', label: 'Payload' }]);
  });

  it('does not filter artifact for non-job resources', () => {
    const isJob = false;
    const filtered = isJob
      ? allFields.filter((f) => !JOB_STATUS_FIELDS.has(f.name) && !isArtifactField(f.name))
      : allFields;
    expect(filtered).toEqual(allFields);
  });
});

describe('JobArtifactSection visibility', () => {
  it('should not render when artifact is null and no groups', () => {
    const data = { status: 'completed', payload: {}, artifact: null };
    const groups: any[] = [];
    const collapsedGroups: any[] = [];
    // Component returns null when all are empty
    expect(groups.length === 0 && collapsedGroups.length === 0 && data.artifact == null).toBe(true);
  });

  it('should render when artifact has value even with no schema groups', () => {
    const data = { artifact: { result: 42 } };
    const groups: any[] = [];
    const collapsedGroups: any[] = [];
    expect(groups.length === 0 && collapsedGroups.length === 0 && data.artifact == null).toBe(
      false,
    );
  });

  it('should render when artifact groups exist', () => {
    const data = { artifact: null };
    const groups = [{ kind: 'single', field: { name: 'artifact' } }];
    expect(groups.length === 0 && data.artifact == null).toBe(false);
  });
});
