/**
 * Backup & Restore page component.
 *
 * Provides:
 * - Global export / import for all models
 * - Per-model export / import
 * - Selectable on_duplicate strategy
 */

import { useState, useCallback } from 'react';
import {
  Container,
  Stack,
  Title,
  Text,
  Card,
  Group,
  Button,
  Select,
  FileInput,
  SimpleGrid,
  Alert,
  Table,
  Badge,
  Divider,
  Loader,
} from '@mantine/core';
import {
  IconDownload,
  IconUpload,
  IconCheck,
  IconAlertCircle,
  IconDatabaseExport,
  IconDatabaseImport,
} from '@tabler/icons-react';
import { backupApi, type OnDuplicate, type ImportResult, type GlobalImportResult } from '../../generated/api/backupApi';

interface BackupRestoreProps {
  resourceNames: string[];
}

/** Trigger browser download for a Blob response. */
function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export function BackupRestore({ resourceNames }: BackupRestoreProps) {
  // ── Global state ────────────────────────────────────────────────
  const [globalExporting, setGlobalExporting] = useState(false);
  const [globalImporting, setGlobalImporting] = useState(false);
  const [globalFile, setGlobalFile] = useState<File | null>(null);
  const [globalDuplicateStrategy, setGlobalDuplicateStrategy] = useState<OnDuplicate>('overwrite');
  const [globalResult, setGlobalResult] = useState<GlobalImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // ── Per-model state ─────────────────────────────────────────────
  const [perModelFile, setPerModelFile] = useState<File | null>(null);
  const [perModelTarget, setPerModelTarget] = useState<string | null>(null);
  const [perModelDuplicateStrategy, setPerModelDuplicateStrategy] = useState<OnDuplicate>('overwrite');
  const [perModelExporting, setPerModelExporting] = useState<string | null>(null);
  const [perModelImporting, setPerModelImporting] = useState(false);
  const [perModelResult, setPerModelResult] = useState<ImportResult | null>(null);

  const clearMessages = useCallback(() => {
    setError(null);
    setSuccessMessage(null);
    setGlobalResult(null);
    setPerModelResult(null);
  }, []);

  // ── Global export ───────────────────────────────────────────────
  const handleGlobalExport = async () => {
    clearMessages();
    setGlobalExporting(true);
    try {
      const resp = await backupApi.exportAll();
      downloadBlob(resp.data, 'backup.acbak');
      setSuccessMessage('Global backup downloaded successfully.');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Export failed');
    } finally {
      setGlobalExporting(false);
    }
  };

  // ── Global import ───────────────────────────────────────────────
  const handleGlobalImport = async () => {
    if (!globalFile) return;
    clearMessages();
    setGlobalImporting(true);
    try {
      const resp = await backupApi.importAll(globalFile, globalDuplicateStrategy);
      setGlobalResult(resp.data);
      setGlobalFile(null);
      setSuccessMessage('Global import completed.');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Import failed');
    } finally {
      setGlobalImporting(false);
    }
  };

  // ── Per-model export ────────────────────────────────────────────
  const handlePerModelExport = async (modelName: string) => {
    clearMessages();
    setPerModelExporting(modelName);
    try {
      const method = (backupApi as any)[`export${toPascal(modelName)}`];
      if (!method) {
        // Fallback: use global export with model filter
        const resp = await backupApi.exportAll([modelName]);
        downloadBlob(resp.data, `${modelName}.acbak`);
      } else {
        const resp = await method();
        downloadBlob(resp.data, `${modelName}.acbak`);
      }
      setSuccessMessage(`${modelName} exported successfully.`);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Export failed');
    } finally {
      setPerModelExporting(null);
    }
  };

  // ── Per-model import ────────────────────────────────────────────
  const handlePerModelImport = async () => {
    if (!perModelFile || !perModelTarget) return;
    clearMessages();
    setPerModelImporting(true);
    try {
      const method = (backupApi as any)[`import${toPascal(perModelTarget)}`];
      if (!method) {
        setError(`No import method found for ${perModelTarget}`);
        return;
      }
      const resp = await method(perModelFile, perModelDuplicateStrategy);
      setPerModelResult(resp.data);
      setPerModelFile(null);
      setSuccessMessage(`${perModelTarget} import completed.`);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Import failed');
    } finally {
      setPerModelImporting(false);
    }
  };

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        <div>
          <Title order={2}>Backup & Restore</Title>
          <Text c="dimmed" mt={4}>
            Export and import your data as .acbak archives.
          </Text>
        </div>

        {/* Alerts */}
        {error && (
          <Alert icon={<IconAlertCircle size={18} />} color="red" onClose={() => setError(null)} withCloseButton>
            {error}
          </Alert>
        )}
        {successMessage && (
          <Alert icon={<IconCheck size={18} />} color="green" onClose={() => setSuccessMessage(null)} withCloseButton>
            {successMessage}
          </Alert>
        )}

        {/* ── Global backup ─────────────────────────────────────── */}
        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Group>
              <IconDatabaseExport size={24} />
              <Title order={4}>Global Backup</Title>
            </Group>
            <Text size="sm" c="dimmed">
              Export all models into a single .acbak archive, or import a previously exported archive.
            </Text>

            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
              {/* Export */}
              <Card withBorder padding="md">
                <Stack gap="sm">
                  <Text fw={500}>Export</Text>
                  <Button
                    leftSection={<IconDownload size={16} />}
                    onClick={handleGlobalExport}
                    loading={globalExporting}
                    fullWidth
                  >
                    Download Full Backup
                  </Button>
                </Stack>
              </Card>

              {/* Import */}
              <Card withBorder padding="md">
                <Stack gap="sm">
                  <Text fw={500}>Import</Text>
                  <FileInput
                    placeholder="Choose .acbak file"
                    accept=".acbak,application/octet-stream"
                    value={globalFile}
                    onChange={setGlobalFile}
                  />
                  <Select
                    label="On duplicate"
                    data={[
                      { value: 'overwrite', label: 'Overwrite existing' },
                      { value: 'skip', label: 'Skip duplicates' },
                      { value: 'raise_error', label: 'Raise error' },
                    ]}
                    value={globalDuplicateStrategy}
                    onChange={(v) => setGlobalDuplicateStrategy((v as OnDuplicate) || 'overwrite')}
                  />
                  <Button
                    leftSection={<IconUpload size={16} />}
                    onClick={handleGlobalImport}
                    loading={globalImporting}
                    disabled={!globalFile}
                    fullWidth
                  >
                    Upload & Import
                  </Button>
                </Stack>
              </Card>
            </SimpleGrid>

            {/* Global import results */}
            {globalResult && (
              <>
                <Divider />
                <Text fw={500}>Import Results</Text>
                <Table striped withTableBorder>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Model</Table.Th>
                      <Table.Th>Loaded</Table.Th>
                      <Table.Th>Skipped</Table.Th>
                      <Table.Th>Total</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {Object.entries(globalResult).map(([model, stats]) => (
                      <Table.Tr key={model}>
                        <Table.Td>
                          <Badge variant="light">{model}</Badge>
                        </Table.Td>
                        <Table.Td>{stats.loaded}</Table.Td>
                        <Table.Td>{stats.skipped}</Table.Td>
                        <Table.Td>{stats.total}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </>
            )}
          </Stack>
        </Card>

        {/* ── Per-model backup ──────────────────────────────────── */}
        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Group>
              <IconDatabaseImport size={24} />
              <Title order={4}>Per-Model Operations</Title>
            </Group>
            <Text size="sm" c="dimmed">
              Export or import individual models.
            </Text>

            {/* Per-model export */}
            <Text fw={500}>Export Single Model</Text>
            <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }} spacing="sm">
              {resourceNames.map((name) => (
                <Button
                  key={name}
                  variant="outline"
                  leftSection={<IconDownload size={14} />}
                  onClick={() => handlePerModelExport(name)}
                  loading={perModelExporting === name}
                  size="sm"
                >
                  {name}
                </Button>
              ))}
            </SimpleGrid>

            <Divider />

            {/* Per-model import */}
            <Text fw={500}>Import Single Model</Text>
            <Group grow>
              <Select
                label="Target model"
                placeholder="Select model"
                data={resourceNames.map((n) => ({ value: n, label: n }))}
                value={perModelTarget}
                onChange={setPerModelTarget}
              />
              <Select
                label="On duplicate"
                data={[
                  { value: 'overwrite', label: 'Overwrite existing' },
                  { value: 'skip', label: 'Skip duplicates' },
                  { value: 'raise_error', label: 'Raise error' },
                ]}
                value={perModelDuplicateStrategy}
                onChange={(v) => setPerModelDuplicateStrategy((v as OnDuplicate) || 'overwrite')}
              />
            </Group>
            <FileInput
              placeholder="Choose .acbak file"
              accept=".acbak,application/octet-stream"
              value={perModelFile}
              onChange={setPerModelFile}
            />
            <Button
              leftSection={<IconUpload size={16} />}
              onClick={handlePerModelImport}
              loading={perModelImporting}
              disabled={!perModelFile || !perModelTarget}
            >
              Upload & Import to {perModelTarget || '...'}
            </Button>

            {/* Per-model import results */}
            {perModelResult && (
              <>
                <Divider />
                <Group>
                  <Text fw={500}>Import Result:</Text>
                  <Badge color="green">{perModelResult.loaded} loaded</Badge>
                  <Badge color="yellow">{perModelResult.skipped} skipped</Badge>
                  <Badge color="gray">{perModelResult.total} total</Badge>
                </Group>
              </>
            )}
          </Stack>
        </Card>
      </Stack>
    </Container>
  );
}

/** Convert kebab-case or snake_case to PascalCase. */
function toPascal(s: string): string {
  return s
    .split(/[-_]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join('');
}
