/**
 * UnionFieldDisplay — Read-only display for discriminated union fields.
 *
 * Shows the discriminator tag as a badge, then renders variant-specific
 * sub-fields in a nested table.
 */

import { Badge, Stack, Table } from '@mantine/core';
import type { UnionMeta, ResourceField } from '../../../resources';
import type { DetailRenderContext } from './index';

export interface UnionFieldDisplayProps {
  value: Record<string, any>;
  unionMeta: UnionMeta;
  /** Render function for individual sub-field values */
  renderValue: (ctx: DetailRenderContext) => React.ReactNode;
}

export function UnionFieldDisplay({ value, unionMeta, renderValue }: UnionFieldDisplayProps) {
  const discField = unionMeta.discriminatorField;
  const tag = value[discField];
  const variant = unionMeta.variants.find((v) => v.tag === tag);

  return (
    <Stack gap="xs">
      <Badge variant="light" size="sm">
        {variant?.label || tag || 'unknown'}
      </Badge>
      {variant?.fields && variant.fields.length > 0 && (
        <Table fz="sm">
          <Table.Tbody>
            {variant.fields.map((sf: ResourceField) => (
              <Table.Tr key={sf.name}>
                <Table.Td style={{ fontWeight: 500, width: '35%' }}>{sf.label}</Table.Td>
                <Table.Td>
                  {renderValue({
                    field: sf,
                    value: value?.[sf.name],
                    data: value,
                  })}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
