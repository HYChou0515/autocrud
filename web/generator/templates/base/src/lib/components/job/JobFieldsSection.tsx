/**
 * JobFieldsSection — Displays non-status, non-payload Job fields.
 *
 * Renders a simple key→value table for any fields that are not part of
 * the Job status section and not the payload object.
 */

import { Paper, Table, Title } from '@mantine/core';
import { renderSimpleValue } from '../../utils/displayHelpers';
import { JOB_STATUS_FIELDS } from './JobStatusSection';

export interface JobFieldsSectionProps {
  data: Record<string, any>;
}

export function JobFieldsSection({ data }: JobFieldsSectionProps) {
  const otherFields = Object.entries(data).filter(
    ([key]) => !JOB_STATUS_FIELDS.has(key) && key !== 'payload',
  );

  if (otherFields.length === 0) return null;

  return (
    <Paper withBorder p="md">
      <Title order={4} mb="md">
        Job Fields
      </Title>
      <Table>
        <Table.Tbody>
          {otherFields.map(([key, value]) => (
            <Table.Tr key={key}>
              <Table.Td style={{ fontWeight: 500, width: '30%' }}>{key}</Table.Td>
              <Table.Td>{renderSimpleValue(value)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Paper>
  );
}
