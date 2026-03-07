import { useState, useEffect, useRef, useMemo } from 'react';
import { Link, useNavigate } from '@tanstack/react-router';
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
  NumberInput,
  Tooltip,
} from '@mantine/core';
import {
  IconEdit,
  IconTrash,
  IconTrashX,
  IconRestore,
  IconArrowLeft,
  IconAlertCircle,
  IconLayersSubtract,
  IconHistory,
  IconRefresh,
} from '@tabler/icons-react';
import type { ResourceConfig, ResourceField } from '../../resources';
import { useResourceDetail } from '../../hooks/useResourceDetail';
import { useFieldDepth } from '../../hooks/useFieldDepth';
import { ResourceForm, type ResourceFormHandle } from '../form/ResourceForm';
import { MetadataSection } from './MetadataSection';
import { RevisionHistorySection } from './RevisionHistorySection';
import { ResourceIdCell } from '../common/ResourceIdCell';
import { RevisionIdCell } from '../common/RevisionIdCell';
import { DetailFieldRenderer } from '../field/DetailFieldRenderer';
import { CollapsibleJson } from '../field/DetailFieldRenderer/CollapsibleJson';
import { JobStatusSection, JOB_STATUS_FIELDS, JOB_STATUS_COLORS } from '../job/JobStatusSection';
import { JobArtifactSection } from '../job/JobArtifactSection';
import { JobFieldsSection } from '../job/JobFieldsSection';
import { JobLogsPanel } from '../job/JobLogsPanel';
import type { ResourceListRoute } from '../../../generated/resources';
import { showErrorNotification, extractUniqueConflict } from '../../utils/errorNotification';
import { getByPath } from '@/autocrud/lib/utils/formUtils';

// ---------------------------------------------------------------------------
// Field grouping — groups dot-notation sub-fields under their parent
// ---------------------------------------------------------------------------

export type DisplayGroup =
  | { kind: 'single'; field: ResourceField }
  | { kind: 'nested'; parentPath: string; parentLabel: string; children: ResourceField[] };

/**
 * Group flat dot-notation fields by their parent path for hierarchical display.
 *
 * Fields at the shallowest depth become standalone rows.
 * Deeper fields that share the same parent path are grouped into a single
 * nested row labelled with the parent's name.
 */
export function groupFieldsForDisplay(fields: ResourceField[]): DisplayGroup[] {
  if (fields.length === 0) return [];

  const minDepth = Math.min(...fields.map((f) => f.name.split('.').length));

  function parentOf(name: string): string {
    const lastDot = name.lastIndexOf('.');
    return lastDot >= 0 ? name.substring(0, lastDot) : '';
  }

  function toGroupLabel(parentPath: string): string {
    const lastSeg = parentPath.split('.').pop() || parentPath;
    return lastSeg.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }

  const groups: DisplayGroup[] = [];
  let i = 0;

  while (i < fields.length) {
    const field = fields[i];
    const depth = field.name.split('.').length;

    if (depth <= minDepth) {
      groups.push({ kind: 'single', field });
      i++;
      continue;
    }

    // Deeper field — collect consecutive siblings with same parent
    const parent = parentOf(field.name);
    const children: ResourceField[] = [field];
    let j = i + 1;
    while (j < fields.length && parentOf(fields[j].name) === parent) {
      children.push(fields[j]);
      j++;
    }

    groups.push({
      kind: 'nested',
      parentPath: parent,
      parentLabel: toGroupLabel(parent),
      children,
    });
    i = j;
  }

  return groups;
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
  const navigate = useNavigate();
  const [editOpen, setEditOpen] = useState(false);
  const [selectedRevision, setSelectedRevision] = useState<string | null>(initialRevision ?? null);
  const editFormRef = useRef<ResourceFormHandle | null>(null);

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
    permanentlyDelete,
    restore,
    switchRevision,
    rerun,
    error,
    logs,
    logsLoading,
    fetchLogs,
  } = useResourceDetail(config, resourceId, selectedRevision);

  // Depth control — shared hook (detail mode strips itemFields instead of collapsing)
  const {
    maxAvailableDepth,
    depth: detailDepth,
    setDepth: setDetailDepth,
    visibleFields,
    collapsedGroups,
  } = useFieldDepth({
    fields: config.fields,
    maxFormDepth: config.maxFormDepth,
    stripItemFields: true,
  });

  // Group dot-notation fields by parent for hierarchical display
  const isArtifactField = (name: string) => name === 'artifact' || name.startsWith('artifact.');

  const displayGroups = useMemo(() => {
    const filtered = isJob
      ? visibleFields.filter((f) => !JOB_STATUS_FIELDS.has(f.name) && !isArtifactField(f.name))
      : visibleFields;
    return groupFieldsForDisplay(filtered);
  }, [visibleFields, isJob]);

  // Artifact-specific groups (same structured rendering as Payload)
  const artifactGroups = useMemo(() => {
    if (!isJob) return [];
    const artifactFields = visibleFields.filter((f) => isArtifactField(f.name));
    return groupFieldsForDisplay(artifactFields);
  }, [visibleFields, isJob]);

  const artifactCollapsedGroups = useMemo(() => {
    if (!isJob) return [];
    return collapsedGroups.filter((g) => isArtifactField(g.path));
  }, [collapsedGroups, isJob]);

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

  // Job-specific: status for header badge, display data source
  const jobStatus = isJob ? (data.status as string) || 'unknown' : null;
  const displayData = isJob ? data.payload || {} : data;

  const displayNameValue = config.displayNameField
    ? getByPath(displayData, config.displayNameField)
    : undefined;
  const displayNameText =
    typeof displayNameValue === 'string' && displayNameValue.trim().length > 0
      ? displayNameValue
      : undefined;

  const handleEdit = async (values: T) => {
    try {
      // Union resource: form wraps in { data: ... }, API expects the unwrapped union object
      const submitValues = config.isUnion ? ((values as any).data as T) : values;
      await update(submitValues);
      setEditOpen(false);
      // Navigate to latest (no revision param) after successful edit
      handleRevisionSelect(null);
    } catch (error) {
      const conflict = extractUniqueConflict(error);
      if (conflict && editFormRef.current) {
        editFormRef.current.setFieldError(conflict.field, `此值已被使用 (unique constraint)`);
      }
      showErrorNotification(error, 'Update Failed');
    }
  };

  const handleDelete = async () => {
    if (confirm('Are you sure you want to delete this resource?')) {
      try {
        await deleteResource();
      } catch (error) {
        showErrorNotification(error, 'Delete Failed');
      }
    }
  };

  const handlePermanentlyDelete = async () => {
    if (
      confirm(
        '⚠️ PERMANENTLY DELETE this resource?\n\nThis action is IRREVERSIBLE. All data and revision history will be lost forever.',
      )
    ) {
      try {
        await permanentlyDelete();
        navigate({ to: basePath });
      } catch (error) {
        showErrorNotification(error, 'Permanently Delete Failed');
      }
    }
  };

  const handleRestore = async () => {
    try {
      await restore();
    } catch (error) {
      showErrorNotification(error, 'Restore Failed');
    }
  };

  const handleRevert = async () => {
    if (!selectedRevision) return;
    if (confirm('Are you sure you want to revert to this revision?')) {
      try {
        await switchRevision(selectedRevision);
        handleRevisionSelect(null);
      } catch (error) {
        showErrorNotification(error, 'Revert Failed');
      }
    }
  };

  const handleRerun = async () => {
    try {
      await rerun();
    } catch (error) {
      showErrorNotification(error, 'Rerun Failed');
    }
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
                {isJob && jobStatus && (
                  <Badge color={JOB_STATUS_COLORS[jobStatus] || 'gray'} variant="filled">
                    {jobStatus.toUpperCase()}
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
                {isJob &&
                  (jobStatus === 'completed' || jobStatus === 'failed') &&
                  config.apiClient.rerun && (
                    <Button
                      variant="light"
                      color="blue"
                      leftSection={<IconRefresh size={16} />}
                      onClick={handleRerun}
                    >
                      Rerun
                    </Button>
                  )}
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
              <>
                <Button
                  color="green"
                  leftSection={<IconRestore size={16} />}
                  onClick={handleRestore}
                >
                  Restore
                </Button>
                <Button
                  color="red"
                  variant="filled"
                  leftSection={<IconTrashX size={16} />}
                  onClick={handlePermanentlyDelete}
                >
                  Permanently Delete
                </Button>
              </>
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
            <Button
              variant="light"
              color="blue"
              size="xs"
              leftSection={<IconHistory size={14} />}
              onClick={handleRevert}
              mt="xs"
            >
              Revert to this revision
            </Button>
          </Alert>
        )}

        {/* Job Status Section (delegated to JobStatusSection component) */}
        {isJob && <JobStatusSection data={data} />}

        {/* Artifact Section (structured display, same pattern as Payload) */}
        {isJob && (
          <JobArtifactSection
            data={data}
            groups={artifactGroups}
            collapsedGroups={artifactCollapsedGroups}
          />
        )}

        {/* Other Job Fields Section (delegated to JobFieldsSection component) */}
        {isJob && <JobFieldsSection data={data} />}

        {/* Job Execution Logs */}
        {isJob && (
          <JobLogsPanel
            logs={logs}
            loading={logsLoading}
            onFetch={fetchLogs}
            available={!!config.apiClient.getLogs}
          />
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
              {displayGroups.map((group) => {
                if (group.kind === 'single') {
                  const field = group.field;
                  const value =
                    config.isUnion && field.type === 'union' && field.name === 'data'
                      ? data
                      : getByPath(data, field.name);
                  return (
                    <Table.Tr key={field.name}>
                      <Table.Td style={{ fontWeight: 500, width: '30%', verticalAlign: 'top' }}>
                        {field.label}
                      </Table.Td>
                      <Table.Td>
                        <DetailFieldRenderer field={field} value={value} data={data} />
                      </Table.Td>
                    </Table.Tr>
                  );
                }

                // Nested group — render children in a sub-table
                const parentValue = getByPath(data, group.parentPath);
                return (
                  <Table.Tr key={group.parentPath}>
                    <Table.Td style={{ fontWeight: 500, width: '30%', verticalAlign: 'top' }}>
                      {group.parentLabel}
                    </Table.Td>
                    <Table.Td>
                      {parentValue == null ? (
                        <Text c="dimmed" size="sm">
                          N/A
                        </Text>
                      ) : (
                        <Table fz="sm">
                          <Table.Tbody>
                            {group.children.map((child) => (
                              <Table.Tr key={child.name}>
                                <Table.Td style={{ fontWeight: 500, width: '35%' }}>
                                  {child.label}
                                </Table.Td>
                                <Table.Td>
                                  <DetailFieldRenderer
                                    field={child}
                                    value={getByPath(data, child.name)}
                                    data={data}
                                  />
                                </Table.Td>
                              </Table.Tr>
                            ))}
                          </Table.Tbody>
                        </Table>
                      )}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
              {(isJob
                ? collapsedGroups.filter(
                    (g) => !JOB_STATUS_FIELDS.has(g.path) && !isArtifactField(g.path),
                  )
                : collapsedGroups
              ).map((group) => {
                const value = getByPath(data, group.path);
                return (
                  <Table.Tr key={group.path}>
                    <Table.Td style={{ fontWeight: 500, width: '30%' }}>{group.label}</Table.Td>
                    <Table.Td>
                      {value != null ? (
                        <CollapsibleJson value={value} />
                      ) : (
                        <Text c="dimmed" size="sm">
                          N/A
                        </Text>
                      )}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
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
            initialValues={config.isUnion ? ({ data } as unknown as Partial<T>) : data}
            onSubmit={handleEdit}
            onCancel={() => setEditOpen(false)}
            submitLabel="Update"
            formRef={editFormRef}
          />
        )}
      </Modal>
    </Container>
  );
}
