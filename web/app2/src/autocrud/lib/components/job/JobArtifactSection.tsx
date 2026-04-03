/**
 * JobArtifactSection — Displays the Job artifact in a dedicated bordered Paper.
 *
 * Uses the same structured Table + DetailFieldRenderer pattern as the
 * Payload section so that artifact sub-fields are rendered with proper
 * type-aware formatting rather than raw JSON.
 *
 * Renders nothing when there are no artifact groups AND the raw artifact
 * value is null/undefined.
 */

import { Paper, Table, Text, Title } from '@mantine/core';
import type { DisplayGroup } from '../detail/ResourceDetail';
import { DetailFieldRenderer } from '../field/DetailFieldRenderer';
import { CollapsibleJson } from '../field/DetailFieldRenderer/CollapsibleJson';
import { getByPath } from '@/autocrud/lib/utils/formUtils';

export interface JobArtifactSectionProps {
  /** Full job data object */
  data: Record<string, any>;
  /** Artifact display groups built from schema fields (artifact.*) */
  groups: DisplayGroup[];
  /** Collapsed artifact groups (depth-based) */
  collapsedGroups: { path: string; label: string }[];
}

export function JobArtifactSection({ data, groups, collapsedGroups }: JobArtifactSectionProps) {
  const artifact = data.artifact;

  // Nothing to show
  if (groups.length === 0 && collapsedGroups.length === 0 && artifact == null) return null;

  return (
    <Paper withBorder p="md">
      <Title order={4} mb="md">
        Artifact
      </Title>
      <Table>
        <Table.Tbody>
          {groups.map((group) => {
            if (group.kind === 'single') {
              const field = group.field;
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
          {collapsedGroups.map((group) => {
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
  );
}
