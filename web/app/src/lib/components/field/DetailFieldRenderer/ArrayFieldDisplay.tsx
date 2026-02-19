/**
 * ArrayFieldDisplay — Read-only display for array-of-typed-object fields.
 *
 * Each array item is rendered as a bordered card with a numbered header
 * and a sub-table of the item's fields.
 */

import { Paper, Stack, Table, Text } from '@mantine/core';
import type { ResourceField } from '../../../resources';
import type { DetailRenderContext } from './index';

export interface ArrayFieldDisplayProps {
  value: unknown[];
  itemFields: ResourceField[];
  /** Render function for individual sub-field values */
  renderValue: (ctx: DetailRenderContext) => React.ReactNode;
}

export function ArrayFieldDisplay({ value, itemFields, renderValue }: ArrayFieldDisplayProps) {
  if (value.length === 0) {
    return (
      <Text c="dimmed" size="sm">
        []
      </Text>
    );
  }

  return (
    <Stack gap="xs">
      {value.map((item: any, idx: number) => (
        <Paper key={idx} withBorder p="xs" radius="sm">
          <Text size="xs" c="dimmed" mb={4}>
            #{idx + 1}
          </Text>
          <Table fz="sm">
            <Table.Tbody>
              {itemFields.map((sf) => (
                <Table.Tr key={sf.name}>
                  <Table.Td style={{ fontWeight: 500, width: '35%' }}>{sf.label}</Table.Td>
                  <Table.Td>
                    {renderValue({
                      field: sf,
                      value: item?.[sf.name],
                      data: item ?? {},
                    })}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      ))}
    </Stack>
  );
}
