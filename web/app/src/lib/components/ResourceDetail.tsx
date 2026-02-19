import { useState, useEffect } from 'react';
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
  Code,
  NumberInput,
  Tooltip,
} from '@mantine/core';
import {
  IconEdit,
  IconTrash,
  IconRestore,
  IconArrowLeft,
  IconAlertCircle,
  IconLayersSubtract,
} from '@tabler/icons-react';
import type { ResourceConfig } from '../resources';
import { useResourceDetail } from '../hooks/useResourceDetail';
import { useFieldDepth } from '../hooks/useFieldDepth';
import { ResourceForm } from './ResourceForm';
import { MetadataSection } from './MetadataSection';
import { RevisionHistorySection } from './RevisionHistorySection';
import { ResourceIdCell } from './resource-table/ResourceIdCell';
import { RevisionIdCell } from './resource-table/RevisionIdCell';
import { DetailFieldRenderer } from './Field/DetailFieldRenderer';
import { JobStatusSection, JOB_STATUS_FIELDS, JOB_STATUS_COLORS } from './JobStatusSection';
import { JobFieldsSection } from './JobFieldsSection';
import type { ResourceListRoute } from '../../generated/resources';
import { showErrorNotification } from '../utils/errorNotification';
import { getByPath } from '@/lib/utils/formUtils';

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
      await update(values);
      setEditOpen(false);
      // Navigate to latest (no revision param) after successful edit
      handleRevisionSelect(null);
    } catch (error) {
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

  const handleRestore = async () => {
    try {
      await restore();
    } catch (error) {
      showErrorNotification(error, 'Restore Failed');
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

        {/* Job Status Section (delegated to JobStatusSection component) */}
        {isJob && <JobStatusSection data={data} />}

        {/* Other Job Fields Section (delegated to JobFieldsSection component) */}
        {isJob && <JobFieldsSection data={data} />}

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
              {(isJob
                ? visibleFields.filter((f) => !JOB_STATUS_FIELDS.has(f.name))
                : visibleFields
              ).map((field) => {
                const value = getByPath(data, field.name);
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
              })}
              {(isJob
                ? collapsedGroups.filter((g) => !JOB_STATUS_FIELDS.has(g.path))
                : collapsedGroups
              ).map((group) => {
                const value = getByPath(data, group.path);
                return (
                  <Table.Tr key={group.path}>
                    <Table.Td style={{ fontWeight: 500, width: '30%' }}>{group.label}</Table.Td>
                    <Table.Td>
                      {value != null ? (
                        <Code block>{JSON.stringify(value, null, 2)}</Code>
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
