/**
 * JobEnqueue - Job creation form
 *
 * Creates new jobs with payload validation
 */

import { Container, Title, Stack, Group, Button, Alert, Text } from '@mantine/core';
import { IconArrowLeft, IconInfoCircle } from '@tabler/icons-react';
import { useNavigate } from '@tanstack/react-router';
import type { ResourceConfig } from '../resources';
import { ResourceForm } from './ResourceForm';
import { showErrorNotification } from '../utils/errorNotification';

export interface JobEnqueueProps<T> {
  config: ResourceConfig<T>;
  basePath: string;
}

export function JobEnqueue<T extends Record<string, any>>({
  config,
  basePath,
}: JobEnqueueProps<T>) {
  const navigate = useNavigate();

  // Filter out job-specific fields to create payload schema
  const jobSpecificFields = new Set([
    'status',
    'retries',
    'errmsg',
    'periodic_interval_seconds',
    'periodic_max_runs',
    'periodic_runs',
    'periodic_initial_delay_seconds',
  ]);

  const payloadFields = config.fields.filter((field) => !jobSpecificFields.has(field.name));

  // Extract payload Zod schema (if available)
  const payloadZodSchema = config.zodSchema
    ? config.zodSchema.pick(Object.fromEntries(payloadFields.map((f) => [f.name, true])))
    : undefined;

  const payloadConfig = {
    ...config,
    fields: payloadFields,
    zodSchema: payloadZodSchema,
  };

  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        {/* Header */}
        <Group justify="space-between">
          <div>
            <Title order={2}>Enqueue Job</Title>
            <Text c="dimmed" size="sm">
              Create a new {config.label.toLowerCase()} job
            </Text>
          </div>
          <Button
            variant="subtle"
            leftSection={<IconArrowLeft size={16} />}
            onClick={() => navigate({ to: basePath })}
          >
            Back to List
          </Button>
        </Group>

        {/* Info Alert */}
        <Alert icon={<IconInfoCircle size={16} />} title="Job Submission" color="blue">
          Fill in the payload data below. Job status, retries, and error handling are managed
          automatically by the system.
        </Alert>

        {/* Form */}
        <ResourceForm
          config={payloadConfig as ResourceConfig<Record<string, any>>}
          onSubmit={async (values) => {
            try {
              const result = await config.apiClient.create(values as T);
              navigate({ to: `${basePath}/${result.data.resource_id}` });
            } catch (error) {
              showErrorNotification(error, 'Enqueue Failed');
            }
          }}
          onCancel={() => navigate({ to: basePath })}
          submitLabel="Enqueue Job"
        />
      </Stack>
    </Container>
  );
}
