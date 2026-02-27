/**
 * JobEnqueue — unit tests
 *
 * Verifies that JobEnqueue correctly:
 * 1. Filters out job-specific fields from config.fields
 * 2. Passes the ORIGINAL zodSchema to ResourceForm (no .pick() extraction)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { z } from 'zod';
import type { ResourceConfig, ResourceField } from '../../resources';

// Capture the config prop passed to ResourceForm
let capturedConfig: ResourceConfig<any> | null = null;

vi.mock('../form/ResourceForm', () => ({
  ResourceForm: (props: any) => {
    capturedConfig = props.config;
    return null;
  },
}));

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}));

import { render } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { JobEnqueue } from './JobEnqueue';

function makeField(name: string, overrides?: Partial<ResourceField>): ResourceField {
  return {
    name,
    label: name,
    type: 'string',
    isArray: false,
    isRequired: false,
    isNullable: false,
    ...overrides,
  };
}

function renderJobEnqueue(config: ResourceConfig<any>) {
  return render(
    <MantineProvider>
      <JobEnqueue config={config} basePath="/test" />
    </MantineProvider>,
  );
}

describe('JobEnqueue', () => {
  beforeEach(() => {
    capturedConfig = null;
  });

  it('passes original zodSchema to ResourceForm without .pick() extraction', () => {
    const originalZodSchema = z.object({
      payload: z.object({
        event_type: z.string(),
        description: z.string(),
      }),
      status: z.enum(['pending', 'completed']).optional(),
      retries: z.number().int().optional(),
      errmsg: z.string().nullable().optional(),
    });

    const config: ResourceConfig<any> = {
      name: 'game-event',
      label: 'Game Event',
      pluralLabel: 'Game Events',
      schema: 'GameEvent',
      fields: [
        makeField('payload.event_type'),
        makeField('payload.description'),
        makeField('status'),
        makeField('retries', { type: 'number' }),
        makeField('errmsg'),
      ],
      zodSchema: originalZodSchema,
      apiClient: {
        create: vi.fn(),
        list: vi.fn(),
        count: vi.fn(),
        get: vi.fn(),
        update: vi.fn(),
        delete: vi.fn(),
        restore: vi.fn(),
        revisionList: vi.fn(),
        switchRevision: vi.fn(),
      },
    };

    renderJobEnqueue(config);

    expect(capturedConfig).not.toBeNull();
    // zodSchema should be the ORIGINAL, not a .pick()'d subset
    expect(capturedConfig!.zodSchema).toBe(originalZodSchema);
  });

  it('filters out job-specific fields from config.fields', () => {
    const config: ResourceConfig<any> = {
      name: 'test-job',
      label: 'Test Job',
      pluralLabel: 'Test Jobs',
      schema: 'TestJob',
      fields: [
        makeField('payload.name'),
        makeField('payload.value', { type: 'number' }),
        makeField('status'),
        makeField('retries', { type: 'number' }),
        makeField('errmsg'),
        makeField('periodic_interval_seconds', { type: 'number' }),
        makeField('periodic_max_runs', { type: 'number' }),
        makeField('periodic_runs', { type: 'number' }),
        makeField('periodic_initial_delay_seconds', { type: 'number' }),
      ],
      apiClient: {
        create: vi.fn(),
        list: vi.fn(),
        count: vi.fn(),
        get: vi.fn(),
        update: vi.fn(),
        delete: vi.fn(),
        restore: vi.fn(),
        revisionList: vi.fn(),
        switchRevision: vi.fn(),
      },
    };

    renderJobEnqueue(config);

    expect(capturedConfig).not.toBeNull();
    const fieldNames = capturedConfig!.fields.map((f) => f.name);
    expect(fieldNames).toEqual(['payload.name', 'payload.value']);
    // No job-specific fields
    expect(fieldNames).not.toContain('status');
    expect(fieldNames).not.toContain('retries');
    expect(fieldNames).not.toContain('errmsg');
    expect(fieldNames).not.toContain('periodic_interval_seconds');
  });
});
