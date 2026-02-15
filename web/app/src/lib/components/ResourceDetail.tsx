import { useState, useEffect, useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import {
  Container,
  Title,
  Stack,
  Group,
  Button,
  Badge,
  Alert,
  Loader,
  Paper,
  Text,
  Modal,
  Table,
  Select,
  Code,
  Progress,
  Image,
  Anchor,
  NumberInput,
  Tooltip,
} from '@mantine/core';
import {
  IconEdit,
  IconTrash,
  IconRestore,
  IconArrowLeft,
  IconAlertCircle,
  IconDownload,
  IconLayersSubtract,
} from '@tabler/icons-react';
import type { ResourceConfig, ResourceField } from '../resources';
import { useResourceDetail } from '../hooks/useResourceDetail';
import { ResourceForm } from './ResourceForm';
import { MetadataSection } from './MetadataSection';
import { RevisionHistorySection } from './RevisionHistorySection';
import { ResourceIdCell } from './resource-table/ResourceIdCell';
import { RefLink, RefLinkList, RefRevisionLink, RefRevisionLinkList } from './RefLink';
import { RevisionIdCell } from './resource-table/RevisionIdCell';
import { TimeDisplay } from './TimeDisplay';
import type { ResourceListRoute } from '../../generated/resources';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/** Get a nested value from an object by dot-notation path */
function getByPath(obj: Record<string, any>, path: string): any {
  return path.split('.').reduce((o, k) => o?.[k], obj);
}

/** Convert snake_case / kebab-case to Title Case */
function toLabel(s: string): string {
  return s
    .split(/[-_]+/)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}

/** Build a URL to fetch a blob by file_id */
function getBlobUrl(fileId: string): string {
  return `${API_BASE_URL}/blobs/${fileId}`;
}

/** Check if a string looks like an ISO datetime */
function isISODateString(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value);
}

/** Check if content_type is an image type */
function isImageContentType(contentType: string | undefined): boolean {
  return !!contentType && contentType.startsWith('image/');
}

/** Format byte size to human-readable string */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Render a detail value as React node, with date auto-detection */
function renderDetailValue(value: unknown, fieldType?: string): React.ReactNode {
  if (value == null) {
    return (
      <Text c="dimmed" size="sm">
        N/A
      </Text>
    );
  }
  // Date fields by type or ISO string detection
  if (fieldType === 'date' || isISODateString(value)) {
    return <TimeDisplay time={String(value)} format="full" />;
  }
  if (typeof value === 'boolean') {
    return value ? '✅ Yes' : '❌ No';
  }
  if (Array.isArray(value)) {
    if (value.length === 0)
      return (
        <Text c="dimmed" size="sm">
          []
        </Text>
      );
    // If elements are objects, show as formatted JSON
    if (typeof value[0] === 'object' && value[0] !== null) {
      return <Code block>{JSON.stringify(value, null, 2)}</Code>;
    }
    return value.join(', ');
  }
  if (typeof value === 'object' && value !== null) {
    const obj = value as Record<string, unknown>;
    if ('file_id' in obj && 'size' in obj) {
      const fileId = String(obj.file_id);
      const contentType = obj.content_type as string | undefined;
      const size = obj.size as number;
      const blobUrl = getBlobUrl(fileId);

      if (isImageContentType(contentType)) {
        return (
          <Stack gap="xs">
            <Image
              src={blobUrl}
              alt={fileId}
              maw={400}
              mah={300}
              fit="contain"
              radius="sm"
              style={{ border: '1px solid var(--mantine-color-gray-3)' }}
            />
            <Group gap="xs">
              <Text size="xs" c="dimmed">
                {contentType} · {formatSize(size)}
              </Text>
              <Anchor href={blobUrl} target="_blank" size="xs">
                <Group gap={4}>
                  <IconDownload size={12} />
                  Download
                </Group>
              </Anchor>
            </Group>
          </Stack>
        );
      }

      return (
        <Group gap="xs">
          <Text size="sm">
            📎 {contentType || 'File'} ({formatSize(size)})
          </Text>
          <Anchor href={blobUrl} target="_blank" size="sm">
            <Group gap={4}>
              <IconDownload size={14} />
              Download
            </Group>
          </Anchor>
        </Group>
      );
    }
    return <Code block>{JSON.stringify(value, null, 2)}</Code>;
  }
  return String(value);
}

export interface ResourceDetailProps<T> {
  config: ResourceConfig<T>;
  resourceId: string;
  basePath: ResourceListRoute;
  isJob?: boolean;
  /** Current revision from URL search params (passed by route component) */
  initialRevision?: string;
  /** Callback to update revision in URL (handled by route component with proper typing) */
  onRevisionChange?: (revision: string | null) => void;
}

const statusColors: Record<string, string> = {
  pending: 'gray',
  processing: 'blue',
  completed: 'green',
  failed: 'red',
};

/**
 * Extract revision number from revision_id
 * e.g., "game-event:uuid:3" -> "Rev #3"
 */
function formatRevisionLabel(revisionId: string, resourceId: string, isCurrent: boolean): string {
  const prefix = resourceId + ':';
  if (revisionId.startsWith(prefix)) {
    const parts = revisionId.split(':');
    const revNum = parts[parts.length - 1];
    return isCurrent ? `Current (Rev #${revNum})` : `Rev #${revNum}`;
  }
  // Fallback: try to extract number from end
  const match = revisionId.match(/:(\d+)$/);
  if (match) {
    return isCurrent ? `Current (Rev #${match[1]})` : `Rev #${match[1]}`;
  }
  // Last resort: show truncated ID
  const shortId =
    revisionId.length > 12 ? `${revisionId.slice(0, 6)}...${revisionId.slice(-4)}` : revisionId;
  return isCurrent ? `Current (${shortId})` : shortId;
}

/**
 * Generic resource detail page with edit, delete, restore, and revision history
 * Supports both regular resources and Job resources
 */
export function ResourceDetail<T extends Record<string, any>>({
  config,
  resourceId,
  basePath,
  isJob = false,
  initialRevision,
  onRevisionChange,
}: ResourceDetailProps<T>) {
  const [editOpen, setEditOpen] = useState(false);
  const [selectedRevision, setSelectedRevision] = useState<string | null>(initialRevision ?? null);

  // Sync with external revision changes (e.g., browser back/forward)
  useEffect(() => {
    setSelectedRevision(initialRevision ?? null);
  }, [initialRevision]);

  // Wrapper to update both local state and notify parent for URL sync
  const handleRevisionSelect = (revision: string | null) => {
    setSelectedRevision(revision);
    onRevisionChange?.(revision);
  };

  const {
    resource,
    loading,
    refresh: _refresh,
    update,
    deleteResource,
    restore,
    error,
  } = useResourceDetail(config, resourceId, selectedRevision);

  // Depth control (same logic as ResourceForm)
  const maxAvailableDepth = useMemo(() => {
    let max = 1;
    for (const f of config.fields) {
      const d = f.name.split('.').length;
      if (d > max) max = d;
      // Fields with itemFields (array of typed objects) represent an extra depth level
      if (f.itemFields && f.itemFields.length > 0 && d + 1 > max) max = d + 1;
    }
    return max;
  }, [config.fields]);

  const [detailDepth, setDetailDepth] = useState<number>(config.maxFormDepth ?? maxAvailableDepth);

  const { visibleFields, collapsedGroups } = useMemo(() => {
    const visible: ResourceField[] = [];
    const groupedChildren = new Map<string, ResourceField[]>();

    for (const field of config.fields) {
      const depth = field.name.split('.').length;
      if (depth <= detailDepth) {
        // If field has itemFields but depth isn't enough to expand them, strip itemFields
        if (field.itemFields && field.itemFields.length > 0 && depth + 1 > detailDepth) {
          visible.push({ ...field, itemFields: undefined });
        } else {
          visible.push(field);
        }
      } else {
        const parts = field.name.split('.');
        const ancestorPath = parts.slice(0, detailDepth).join('.');
        if (!groupedChildren.has(ancestorPath)) {
          groupedChildren.set(ancestorPath, []);
        }
        groupedChildren.get(ancestorPath)!.push(field);
      }
    }

    const groups: { path: string; label: string }[] = [];
    for (const parentPath of groupedChildren.keys()) {
      const alreadyVisible = visible.some((f) => f.name === parentPath);
      if (!alreadyVisible) {
        const labelParts = parentPath.split('.');
        const label = toLabel(labelParts[labelParts.length - 1]);
        groups.push({ path: parentPath, label });
      }
    }

    return { visibleFields: visible, collapsedGroups: groups };
  }, [config.fields, detailDepth]);

  if (loading) {
    return (
      <Container size="lg" py="xl">
        <Loader />
      </Container>
    );
  }

  if (error || !resource) {
    return (
      <Container size="lg" py="xl">
        <Alert icon={<IconAlertCircle size={16} />} title="Error" color="red">
          {error?.message || 'Resource not found'}
        </Alert>
      </Container>
    );
  }

  const { data, meta, revision_info } = resource;

  // Whether the user is viewing a historical (non-current) revision
  const isViewingHistorical =
    selectedRevision != null && selectedRevision !== meta.current_revision_id;

  // Job-specific extractions
  const jobStatusFields = new Set([
    'status',
    'retries',
    'errmsg',
    'periodic_interval_seconds',
    'periodic_max_runs',
    'periodic_runs',
    'periodic_initial_delay_seconds',
  ]);

  const status = isJob ? data.status || 'unknown' : null;
  const retries = isJob ? data.retries || 0 : null;
  const errmsg = isJob ? data.errmsg || null : null;
  const isPeriodic = isJob && data.periodic_interval_seconds != null;
  const periodicRuns = isJob ? data.periodic_runs || 0 : null;
  const periodicMaxRuns = isJob ? data.periodic_max_runs || 0 : null;

  // For Job resources:
  // - Use data.payload directly for payload data
  // - Extract other fields (not status fields, not payload)
  const payloadData = isJob ? data.payload || {} : data;
  const otherJobFields = isJob
    ? Object.fromEntries(
        Object.entries(data).filter(([key]) => !jobStatusFields.has(key) && key !== 'payload'),
      )
    : {};
  const _displayData = isJob ? payloadData : data;

  const displayNameValue = config.displayNameField
    ? getByPath(_displayData, config.displayNameField)
    : undefined;
  const displayNameText =
    typeof displayNameValue === 'string' && displayNameValue.trim().length > 0
      ? displayNameValue
      : undefined;

  const handleEdit = async (values: T) => {
    await update(values);
    setEditOpen(false);
    // Navigate to latest (no revision param) after successful edit
    handleRevisionSelect(null);
  };

  const handleDelete = async () => {
    if (confirm('Are you sure you want to delete this resource?')) {
      await deleteResource();
    }
  };

  const handleRestore = async () => {
    await restore();
  };

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        <Group justify="space-between">
          <Group>
            <Button
              component={Link}
              to={basePath}
              variant="subtle"
              leftSection={<IconArrowLeft size={16} />}
            >
              Back
            </Button>
            <div>
              <Group gap="xs" mb="xs">
                <Title order={2}>{isJob ? 'Job Detail' : `${config.label} Detail`}</Title>
                {isJob && status && (
                  <Badge color={statusColors[status] || 'gray'} variant="filled">
                    {status.toUpperCase()}
                  </Badge>
                )}
              </Group>
              {displayNameText && (
                <Text size="sm" c="dimmed" mb={4}>
                  {displayNameText}
                </Text>
              )}
              <ResourceIdCell rid={meta.resource_id} />
            </div>
          </Group>
          <Group>
            {!isViewingHistorical && !meta.is_deleted && (
              <>
                <Button
                  variant="light"
                  leftSection={<IconEdit size={16} />}
                  onClick={() => setEditOpen(true)}
                >
                  Edit
                </Button>
                <Button
                  color="red"
                  variant="light"
                  leftSection={<IconTrash size={16} />}
                  onClick={handleDelete}
                >
                  Delete
                </Button>
              </>
            )}
            {!isViewingHistorical && meta.is_deleted && (
              <Button color="green" leftSection={<IconRestore size={16} />} onClick={handleRestore}>
                Restore
              </Button>
            )}
          </Group>
        </Group>

        {meta.is_deleted && (
          <Alert color="red" title="Deleted">
            This resource has been deleted.
          </Alert>
        )}

        {isViewingHistorical && (
          <Alert color="blue" title="Viewing Historical Revision">
            You are viewing{' '}
            <RevisionIdCell
              revisionId={selectedRevision!}
              resourceId={meta.resource_id}
              showCopy={false}
            />
            . This is a read-only view.
          </Alert>
        )}

        {/* Job Status Section (only for Job resources) */}
        {isJob && (
          <Paper p="md" withBorder>
            <Stack gap="md">
              <Group justify="space-between">
                <Text fw={600} size="lg">
                  Job Status
                </Text>
                <Badge color={statusColors[status!] || 'gray'} variant="filled" size="lg">
                  {status!.toUpperCase()}
                </Badge>
              </Group>

              <Table>
                <Table.Tbody>
                  <Table.Tr>
                    <Table.Td style={{ fontWeight: 500, width: '30%' }}>Status</Table.Td>
                    <Table.Td>
                      <Badge color={statusColors[status!] || 'gray'} variant="light">
                        {status!.toUpperCase()}
                      </Badge>
                    </Table.Td>
                  </Table.Tr>
                  <Table.Tr>
                    <Table.Td style={{ fontWeight: 500, width: '30%' }}>Retries</Table.Td>
                    <Table.Td>{retries}</Table.Td>
                  </Table.Tr>
                  <Table.Tr>
                    <Table.Td style={{ fontWeight: 500, width: '30%' }}>Error Message</Table.Td>
                    <Table.Td>
                      {errmsg ? (
                        <Code block color="red">
                          {errmsg}
                        </Code>
                      ) : (
                        <Text c="dimmed" size="sm">
                          N/A
                        </Text>
                      )}
                    </Table.Td>
                  </Table.Tr>
                  <Table.Tr>
                    <Table.Td style={{ fontWeight: 500, width: '30%' }}>
                      Periodic Interval (seconds)
                    </Table.Td>
                    <Table.Td>
                      {data.periodic_interval_seconds != null ? (
                        `${data.periodic_interval_seconds}s`
                      ) : (
                        <Text c="dimmed" size="sm">
                          N/A
                        </Text>
                      )}
                    </Table.Td>
                  </Table.Tr>
                  <Table.Tr>
                    <Table.Td style={{ fontWeight: 500, width: '30%' }}>Periodic Max Runs</Table.Td>
                    <Table.Td>
                      {data.periodic_max_runs != null ? (
                        data.periodic_max_runs === 0 ? (
                          'Unlimited'
                        ) : (
                          data.periodic_max_runs
                        )
                      ) : (
                        <Text c="dimmed" size="sm">
                          N/A
                        </Text>
                      )}
                    </Table.Td>
                  </Table.Tr>
                  <Table.Tr>
                    <Table.Td style={{ fontWeight: 500, width: '30%' }}>Periodic Runs</Table.Td>
                    <Table.Td>
                      {periodicRuns}
                      {isPeriodic && periodicMaxRuns! > 0 && (
                        <>
                          {' / '}
                          {periodicMaxRuns}
                          <Progress
                            value={(periodicRuns! / periodicMaxRuns!) * 100}
                            size="sm"
                            mt="xs"
                          />
                        </>
                      )}
                    </Table.Td>
                  </Table.Tr>
                  <Table.Tr>
                    <Table.Td style={{ fontWeight: 500, width: '30%' }}>
                      Periodic Initial Delay (seconds)
                    </Table.Td>
                    <Table.Td>
                      {data.periodic_initial_delay_seconds != null ? (
                        `${data.periodic_initial_delay_seconds}s`
                      ) : (
                        <Text c="dimmed" size="sm">
                          N/A
                        </Text>
                      )}
                    </Table.Td>
                  </Table.Tr>
                </Table.Tbody>
              </Table>
            </Stack>
          </Paper>
        )}

        {/* Other Job Fields Section (fields other than status and payload) */}
        {isJob && Object.keys(otherJobFields).length > 0 && (
          <Paper withBorder p="md">
            <Title order={4} mb="md">
              Job Fields
            </Title>
            <Table>
              <Table.Tbody>
                {Object.entries(otherJobFields).map(([key, value]) => (
                  <Table.Tr key={key}>
                    <Table.Td style={{ fontWeight: 500, width: '30%' }}>{key}</Table.Td>
                    <Table.Td>{renderDetailValue(value)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
        )}

        {/* Data/Payload Section */}
        <Paper withBorder p="md">
          <Group justify="space-between" mb="md">
            <Title order={4}>{isJob ? 'Payload' : 'Data'}</Title>
            {maxAvailableDepth > 1 && (
              <Tooltip
                label="Field expansion depth: lower values collapse nested objects into JSON"
                withArrow
              >
                <Group gap={4}>
                  <IconLayersSubtract size={16} />
                  <Text size="xs" c="dimmed">
                    Depth
                  </Text>
                  <NumberInput
                    size="xs"
                    value={detailDepth}
                    onChange={(val) => setDetailDepth(typeof val === 'number' ? val : 1)}
                    min={1}
                    max={maxAvailableDepth}
                    step={1}
                    w={60}
                    styles={{ input: { textAlign: 'center' } }}
                  />
                </Group>
              </Tooltip>
            )}
          </Group>
          <Table>
            <Table.Tbody>
              {(() => {
                // For Job: filter out status fields (shown in Job Status section)
                const dataFields = isJob
                  ? visibleFields.filter((f) => !jobStatusFields.has(f.name))
                  : visibleFields;
                const dataGroups = isJob
                  ? collapsedGroups.filter((g) => !jobStatusFields.has(g.path))
                  : collapsedGroups;
                return (
                  <>
                    {dataFields.map((field) => {
                      const value = getByPath(data, field.name);
                      // Array of typed objects with itemFields — render as sub-table
                      if (field.itemFields && field.itemFields.length > 0 && Array.isArray(value)) {
                        return (
                          <Table.Tr key={field.name}>
                            <Table.Td
                              style={{ fontWeight: 500, width: '30%', verticalAlign: 'top' }}
                            >
                              {field.label}
                            </Table.Td>
                            <Table.Td>
                              {value.length === 0 ? (
                                <Text c="dimmed" size="sm">
                                  []
                                </Text>
                              ) : (
                                <Stack gap="xs">
                                  {value.map((item: any, idx: number) => (
                                    <Paper key={idx} withBorder p="xs" radius="sm">
                                      <Text size="xs" c="dimmed" mb={4}>
                                        #{idx + 1}
                                      </Text>
                                      <Table fz="sm">
                                        <Table.Tbody>
                                          {field.itemFields!.map((sf) => (
                                            <Table.Tr key={sf.name}>
                                              <Table.Td style={{ fontWeight: 500, width: '35%' }}>
                                                {sf.label}
                                              </Table.Td>
                                              <Table.Td>
                                                {renderDetailValue(item?.[sf.name], sf.type)}
                                              </Table.Td>
                                            </Table.Tr>
                                          ))}
                                        </Table.Tbody>
                                      </Table>
                                    </Paper>
                                  ))}
                                </Stack>
                              )}
                            </Table.Td>
                          </Table.Tr>
                        );
                      }
                      return (
                        <Table.Tr key={field.name}>
                          <Table.Td style={{ fontWeight: 500, width: '30%' }}>
                            {field.label}
                          </Table.Td>
                          <Table.Td>
                            {field.ref && field.ref.type === 'resource_id' && field.isArray ? (
                              <RefLinkList values={value as string[] | null} fieldRef={field.ref} />
                            ) : field.ref && field.ref.type === 'resource_id' ? (
                              <RefLink value={value as string | null} fieldRef={field.ref} />
                            ) : field.ref && field.ref.type === 'revision_id' && field.isArray ? (
                              <RefRevisionLinkList
                                values={value as string[] | null}
                                fieldRef={field.ref}
                              />
                            ) : field.ref && field.ref.type === 'revision_id' ? (
                              <RefRevisionLink
                                value={value as string | null}
                                fieldRef={field.ref}
                              />
                            ) : (
                              renderDetailValue(value, field.type)
                            )}
                          </Table.Td>
                        </Table.Tr>
                      );
                    })}
                    {dataGroups.map((group) => {
                      const value = getByPath(data, group.path);
                      return (
                        <Table.Tr key={group.path}>
                          <Table.Td style={{ fontWeight: 500, width: '30%' }}>
                            {group.label}
                          </Table.Td>
                          <Table.Td>{renderDetailValue(value)}</Table.Td>
                        </Table.Tr>
                      );
                    })}
                  </>
                );
              })()}
            </Table.Tbody>
          </Table>
        </Paper>

        <MetadataSection meta={meta} revisionInfo={revision_info} variant="full" />

        <RevisionHistorySection
          config={config}
          resourceId={meta.resource_id}
          currentRevisionId={meta.current_revision_id}
          onRevisionSelect={(revisionId) => {
            handleRevisionSelect(revisionId === meta.current_revision_id ? null : revisionId);
          }}
          selectedRevisionId={selectedRevision || undefined}
        />
      </Stack>

      <Modal
        opened={editOpen}
        onClose={() => setEditOpen(false)}
        title={`Edit ${config.label}`}
        size="lg"
      >
        {editOpen && (
          <ResourceForm
            config={config}
            initialValues={data}
            onSubmit={handleEdit}
            onCancel={() => setEditOpen(false)}
            submitLabel="Update"
          />
        )}
      </Modal>
    </Container>
  );
}
