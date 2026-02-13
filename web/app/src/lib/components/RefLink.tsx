/**
 * RefLink — renders a resource ID as a clickable link to the referenced resource's detail page.
 *
 * Displays the ID in a truncated "first4...last4" format (same style as ResourceIdCell),
 * but as a clickable link that navigates to the referenced resource's detail page.
 * Hover tooltip shows the full ID. A copy button is provided alongside.
 */
import { useState } from 'react';
import { ActionIcon, Anchor, Code, Group, Tooltip } from '@mantine/core';
import { IconCheck, IconCopy, IconExternalLink } from '@tabler/icons-react';
import { Link } from '@tanstack/react-router';
import type { FieldRef } from '../resources';

interface RefLinkProps {
  /** The resource ID value (or null) */
  value: string | null | undefined;
  /** Ref metadata from the field definition */
  fieldRef: FieldRef;
}

export function RefLink({ value, fieldRef }: RefLinkProps) {
  const [copied, setCopied] = useState(false);

  if (value == null) {
    return <Code c="dimmed">N/A</Code>;
  }

  const detailPath = `/autocrud-admin/${fieldRef.resource}/${value}`;
  const shortId = value.length > 12
    ? `${value.slice(0, 4)}...${value.slice(-4)}`
    : value;

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Group gap="xs" wrap="nowrap">
      <Tooltip label={`${fieldRef.resource}: ${value}`} position="top" withArrow>
        <Anchor component={Link} to={detailPath} size="sm" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
          <Group gap={4} wrap="nowrap">
            <Code style={{ cursor: 'pointer' }}>{shortId}</Code>
            <IconExternalLink size={14} />
          </Group>
        </Anchor>
      </Tooltip>
      <Tooltip label={copied ? '已複製!' : '複製完整 ID'} position="right">
        <ActionIcon
          variant="subtle"
          size="sm"
          color={copied ? 'green' : 'gray'}
          onClick={handleCopy}
        >
          {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}
