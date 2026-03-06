/**
 * Migration Status page component.
 *
 * Provides:
 * - Per-model migration test (dry run) with streaming progress
 * - Per-model migration execution with streaming progress
 * - Single resource migration
 * - Real-time progress display via JSONL streaming
 */

import { useState, useCallback, useRef } from 'react';
import {
  Container,
  Stack,
  Title,
  Text,
  Card,
  Group,
  Button,
  Table,
  Badge,
  Alert,
  Divider,
  Progress,
  Accordion,
  Tooltip,
  ActionIcon,
  Code,
  Loader,
} from '@mantine/core';
import {
  IconCheck,
  IconAlertCircle,
  IconArrowsTransferUp,
  IconTestPipe,
  IconPlayerPlay,
  IconRefresh,
  IconX,
} from '@tabler/icons-react';
import {
  migrateApi,
  type MigrateProgress,
  type MigrateResult,
} from '../../autocrud/generated/api/migrateApi';

interface MigrationStatusProps {
  resourceNames: string[];
}

interface ModelMigrationState {
  /** Whether a test/execute is currently running */
  running: boolean;
  /** 'test' or 'execute' */
  mode: 'test' | 'execute' | null;
  /** Streaming progress items */
  progressItems: MigrateProgress[];
  /** Final result summary */
  result: MigrateResult | null;
  /** Error message */
  error: string | null;
}

function getInitialState(): ModelMigrationState {
  return {
    running: false,
    mode: null,
    progressItems: [],
    result: null,
    error: null,
  };
}

function statusColor(status: string): string {
  switch (status) {
    case 'success':
      return 'green';
    case 'failed':
      return 'red';
    case 'skipped':
      return 'gray';
    case 'migrating':
      return 'blue';
    default:
      return 'gray';
  }
}

export function MigrationStatus({ resourceNames }: MigrationStatusProps) {
  const [states, setStates] = useState<Record<string, ModelMigrationState>>(() =>
    Object.fromEntries(resourceNames.map((name) => [name, getInitialState()])),
  );
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [globalSuccess, setGlobalSuccess] = useState<string | null>(null);
  const abortControllers = useRef<Record<string, AbortController>>({});

  const clearMessages = useCallback(() => {
    setGlobalError(null);
    setGlobalSuccess(null);
  }, []);

  const updateModelState = useCallback(
    (modelName: string, update: Partial<ModelMigrationState>) => {
      setStates((prev) => ({
        ...prev,
        [modelName]: { ...prev[modelName], ...update },
      }));
    },
    [],
  );

  const handleMigrate = useCallback(
    async (modelName: string, mode: 'test' | 'execute') => {
      clearMessages();

      // Abort any existing operation for this model
      if (abortControllers.current[modelName]) {
        abortControllers.current[modelName].abort();
      }

      const controller = new AbortController();
      abortControllers.current[modelName] = controller;

      updateModelState(modelName, {
        running: true,
        mode,
        progressItems: [],
        result: null,
        error: null,
      });

      try {
        const apiFn = mode === 'test' ? migrateApi.test : migrateApi.execute;
        const result = await apiFn(
          modelName,
          (progress) => {
            setStates((prev) => ({
              ...prev,
              [modelName]: {
                ...prev[modelName],
                progressItems: [...prev[modelName].progressItems, progress],
              },
            }));
          },
          controller.signal,
        );

        updateModelState(modelName, {
          running: false,
          result,
        });

        if (mode === 'execute' && result.failed === 0) {
          setGlobalSuccess(
            `${modelName}: Migration completed — ${result.success} succeeded, ${result.skipped} skipped.`,
          );
        }
      } catch (e: any) {
        if (e.name === 'AbortError') {
          updateModelState(modelName, { running: false, error: 'Operation cancelled.' });
        } else {
          const message = e.response?.data?.detail || e.message || 'Migration failed';
          updateModelState(modelName, { running: false, error: message });
        }
      } finally {
        delete abortControllers.current[modelName];
      }
    },
    [clearMessages, updateModelState],
  );

  const handleCancel = useCallback((modelName: string) => {
    if (abortControllers.current[modelName]) {
      abortControllers.current[modelName].abort();
      delete abortControllers.current[modelName];
    }
  }, []);

  const handleMigrateAll = useCallback(
    async (mode: 'test' | 'execute') => {
      clearMessages();
      for (const name of resourceNames) {
        await handleMigrate(name, mode);
      }
      setGlobalSuccess(
        mode === 'test'
          ? 'All models tested successfully.'
          : 'All models migrated successfully.',
      );
    },
    [clearMessages, resourceNames, handleMigrate],
  );

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        <div>
          <Title order={2}>Schema Migration</Title>
          <Text c="dimmed" mt={4}>
            Test and execute schema migrations for your resources. Use &quot;Test&quot; for a dry
            run before executing.
          </Text>
        </div>

        {/* Global alerts */}
        {globalError && (
          <Alert
            icon={<IconAlertCircle size={18} />}
            color="red"
            onClose={() => setGlobalError(null)}
            withCloseButton
          >
            {globalError}
          </Alert>
        )}
        {globalSuccess && (
          <Alert
            icon={<IconCheck size={18} />}
            color="green"
            onClose={() => setGlobalSuccess(null)}
            withCloseButton
          >
            {globalSuccess}
          </Alert>
        )}

        {/* Global actions */}
        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Group>
              <IconArrowsTransferUp size={24} />
              <Title order={4}>Batch Operations</Title>
            </Group>
            <Text size="sm" c="dimmed">
              Run test or execute migration for all models at once.
            </Text>
            <Group>
              <Button
                variant="light"
                leftSection={<IconTestPipe size={16} />}
                onClick={() => handleMigrateAll('test')}
                disabled={resourceNames.some((n) => states[n]?.running)}
              >
                Test All Models
              </Button>
              <Button
                leftSection={<IconPlayerPlay size={16} />}
                onClick={() => handleMigrateAll('execute')}
                disabled={resourceNames.some((n) => states[n]?.running)}
              >
                Migrate All Models
              </Button>
            </Group>
          </Stack>
        </Card>

        {/* Per-model cards */}
        {resourceNames.map((modelName) => {
          const state = states[modelName] || getInitialState();
          return (
            <ModelMigrationCard
              key={modelName}
              modelName={modelName}
              state={state}
              onTest={() => handleMigrate(modelName, 'test')}
              onExecute={() => handleMigrate(modelName, 'execute')}
              onCancel={() => handleCancel(modelName)}
            />
          );
        })}
      </Stack>
    </Container>
  );
}

// ── Per-model card ──────────────────────────────────────────────

interface ModelMigrationCardProps {
  modelName: string;
  state: ModelMigrationState;
  onTest: () => void;
  onExecute: () => void;
  onCancel: () => void;
}

function ModelMigrationCard({
  modelName,
  state,
  onTest,
  onExecute,
  onCancel,
}: ModelMigrationCardProps) {
  const { running, mode, progressItems, result, error } = state;
  const total = progressItems.length;
  const successCount = progressItems.filter((p) => p.status === 'success').length;
  const failedCount = progressItems.filter((p) => p.status === 'failed').length;
  const skippedCount = progressItems.filter((p) => p.status === 'skipped').length;

  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder>
      <Stack gap="md">
        {/* Header */}
        <Group justify="space-between">
          <Group>
            <Badge variant="filled" size="lg">
              {modelName}
            </Badge>
            {running && (
              <Group gap="xs">
                <Loader size="xs" />
                <Text size="sm" c="dimmed">
                  {mode === 'test' ? 'Testing…' : 'Migrating…'}
                </Text>
              </Group>
            )}
          </Group>

          <Group gap="xs">
            {running && (
              <Tooltip label="Cancel">
                <ActionIcon variant="subtle" color="red" onClick={onCancel}>
                  <IconX size={16} />
                </ActionIcon>
              </Tooltip>
            )}
            <Button
              variant="light"
              size="xs"
              leftSection={<IconTestPipe size={14} />}
              onClick={onTest}
              disabled={running}
            >
              Test
            </Button>
            <Button
              size="xs"
              leftSection={<IconPlayerPlay size={14} />}
              onClick={onExecute}
              disabled={running}
            >
              Migrate
            </Button>
          </Group>
        </Group>

        {/* Error */}
        {error && (
          <Alert icon={<IconAlertCircle size={16} />} color="red" variant="light">
            {error}
          </Alert>
        )}

        {/* Progress bar (while running) */}
        {running && total > 0 && (
          <Stack gap="xs">
            <Progress.Root size="lg">
              <Progress.Section value={(successCount / Math.max(total, 1)) * 100} color="green">
                <Progress.Label>{successCount}</Progress.Label>
              </Progress.Section>
              <Progress.Section value={(skippedCount / Math.max(total, 1)) * 100} color="gray">
                <Progress.Label>{skippedCount}</Progress.Label>
              </Progress.Section>
              <Progress.Section value={(failedCount / Math.max(total, 1)) * 100} color="red">
                <Progress.Label>{failedCount}</Progress.Label>
              </Progress.Section>
            </Progress.Root>
            <Text size="xs" c="dimmed">
              Processed {total} resources — {successCount} success, {skippedCount} skipped,{' '}
              {failedCount} failed
            </Text>
          </Stack>
        )}

        {/* Final result summary */}
        {result && (
          <>
            <Divider />
            <Group>
              <IconRefresh size={18} />
              <Text fw={500}>
                {mode === 'test' ? 'Test' : 'Migration'} Result
              </Text>
            </Group>
            <Group>
              <Badge color="blue" variant="light" size="lg">
                {result.total} total
              </Badge>
              <Badge color="green" variant="light" size="lg">
                {result.success} success
              </Badge>
              <Badge color="gray" variant="light" size="lg">
                {result.skipped} skipped
              </Badge>
              <Badge color="red" variant="light" size="lg">
                {result.failed} failed
              </Badge>
            </Group>

            {/* Error details */}
            {result.errors.length > 0 && (
              <Accordion variant="contained">
                <Accordion.Item value="errors">
                  <Accordion.Control icon={<IconAlertCircle size={16} color="red" />}>
                    {result.errors.length} Error(s)
                  </Accordion.Control>
                  <Accordion.Panel>
                    <Table striped withTableBorder>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Resource ID</Table.Th>
                          <Table.Th>Error</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {result.errors.map((err, idx) => (
                          <Table.Tr key={idx}>
                            <Table.Td>
                              <Code>{err.resource_id}</Code>
                            </Table.Td>
                            <Table.Td>
                              <Text size="sm" c="red">
                                {err.error}
                              </Text>
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
            )}
          </>
        )}

        {/* Progress detail (expandable) */}
        {!running && progressItems.length > 0 && (
          <Accordion variant="contained">
            <Accordion.Item value="details">
              <Accordion.Control>
                Details ({progressItems.length} resources)
              </Accordion.Control>
              <Accordion.Panel>
                <Table striped withTableBorder>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Resource ID</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th>Message</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {progressItems.map((p, idx) => (
                      <Table.Tr key={idx}>
                        <Table.Td>
                          <Code>{p.resource_id}</Code>
                        </Table.Td>
                        <Table.Td>
                          <Badge color={statusColor(p.status)} variant="light" size="sm">
                            {p.status}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{p.error || p.message || '—'}</Text>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
        )}
      </Stack>
    </Card>
  );
}
