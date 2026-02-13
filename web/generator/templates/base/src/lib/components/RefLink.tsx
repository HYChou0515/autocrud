/**
 * RefLink — renders a resource ID as a clickable link to the referenced resource's detail page.
 *
 * When a field has `ref` metadata (from Annotated[str, Ref(...)]), this component
 * replaces the plain text display with a navigable link.
 */
import { Anchor, Group, Text, Tooltip } from '@mantine/core';
import { IconExternalLink } from '@tabler/icons-react';
import { Link } from '@tanstack/react-router';
import type { FieldRef } from '../resources';

interface RefLinkProps {
  /** The resource ID value (or null) */
  value: string | null | undefined;
  /** Ref metadata from the field definition */
  fieldRef: FieldRef;
}

export function RefLink({ value, fieldRef }: RefLinkProps) {
  if (value == null) {
    return <Text c="dimmed" size="sm">N/A</Text>;
  }

  const detailPath = `/autocrud-admin/${fieldRef.resource}/${value}`;
  const label = fieldRef.type === 'revision_id'
    ? `${fieldRef.resource} revision`
    : fieldRef.resource;

  return (
    <Tooltip label={`Go to ${label}: ${value}`} withArrow>
      <Anchor component={Link} to={detailPath} size="sm">
        <Group gap={4} wrap="nowrap">
          <Text size="sm" truncate style={{ maxWidth: 280 }}>{value}</Text>
          <IconExternalLink size={14} />
        </Group>
      </Anchor>
    </Tooltip>
  );
}
