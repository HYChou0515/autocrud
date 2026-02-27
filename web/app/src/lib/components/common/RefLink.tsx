/**
 * RefLink — renders a resource ID as a clickable link to the referenced resource's detail page.
 *
 * Displays the ID in a truncated "first4...last4" format (same style as ResourceIdCell),
 * but as a clickable link that navigates to the referenced resource's detail page.
 *
 * RefLinkList — renders an array of resource IDs as a list of RefLinks.
 * Used for list[Annotated[str, Ref(...)]] fields (N:N relationships).
 *
 * RefRevisionLink — renders a revision ID with a truncated format and copy button.
 * RefRevisionLinkList — renders an array of revision IDs.
 */
import { useState } from 'react';
import { ActionIcon, Code, Group, Stack, Text, Tooltip } from '@mantine/core';
import { IconCheck, IconCopy, IconExternalLink } from '@tabler/icons-react';
import { Link } from '@tanstack/react-router';
import type { FieldRef } from '../../resources';
import { getResourceDetailRoute, type ResourceName } from '../../../generated/resources';

interface RefLinkProps {
  /** The resource ID value (or null) */
  value: string | null | undefined;
  /** Ref metadata from the field definition */
  fieldRef: FieldRef;
}

function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 4)}...${id.slice(-4)}` : id;
}

export function RefLink({ value, fieldRef }: RefLinkProps) {
  const [copied, setCopied] = useState(false);

  if (value == null) {
    return <Code c="dimmed">N/A</Code>;
  }

  const detailRoute = getResourceDetailRoute(fieldRef.resource as ResourceName);

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
        <Link
          to={detailRoute}
          params={{ resourceId: value }}
          onClick={(e) => e.stopPropagation()}
          onPointerDownCapture={(e) => e.stopPropagation()}
          onClickCapture={(e) => e.stopPropagation()}
          style={{ textDecoration: 'none' }}
        >
          <Group gap={4} wrap="nowrap">
            <Code style={{ cursor: 'pointer' }}>{shortId(value)}</Code>
            <IconExternalLink size={14} />
          </Group>
        </Link>
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

interface RefLinkListProps {
  /** Array of resource IDs */
  values: string[] | null | undefined;
  /** Ref metadata from the field definition */
  fieldRef: FieldRef;
  /** Max items to show before collapsing (default: 5) */
  maxVisible?: number;
}

/**
 * Renders an array of resource IDs as a vertical list of RefLinks.
 * Used for list[Annotated[str, Ref(...)]] fields.
 */
export function RefLinkList({ values, fieldRef, maxVisible = 5 }: RefLinkListProps) {
  const [expanded, setExpanded] = useState(false);

  if (!values || values.length === 0) {
    return (
      <Text c="dimmed" size="sm">
        （空）
      </Text>
    );
  }

  const visible = expanded ? values : values.slice(0, maxVisible);
  const remaining = values.length - maxVisible;

  return (
    <Stack gap={4}>
      {visible.map((id) => (
        <RefLink key={id} value={id} fieldRef={fieldRef} />
      ))}
      {!expanded && remaining > 0 && (
        <Text size="xs" c="blue" style={{ cursor: 'pointer' }} onClick={() => setExpanded(true)}>
          +{remaining} more...
        </Text>
      )}
      {expanded && values.length > maxVisible && (
        <Text size="xs" c="blue" style={{ cursor: 'pointer' }} onClick={() => setExpanded(false)}>
          收起
        </Text>
      )}
    </Stack>
  );
}

// ============= RefRevision Support =============

interface RefRevisionLinkProps {
  /** The revision ID value (or null) */
  value: string | null | undefined;
  /** Ref metadata from the field definition */
  fieldRef: FieldRef;
}

/**
 * Extract resource_id from a revision_id.
 * revision_id format: "prefix:uuid:revision_number" → resource_id: "prefix:uuid"
 */
function revisionIdToResourceId(revisionId: string): string {
  const lastColon = revisionId.lastIndexOf(':');
  if (lastColon > 0) {
    return revisionId.substring(0, lastColon);
  }
  return revisionId;
}

/**
 * Renders a revision ID as a clickable link to the referenced resource's detail page
 * at the specific revision. Navigates to /autocrud-admin/{resource}/{resourceId}?revision={revisionId}.
 */
export function RefRevisionLink({ value, fieldRef }: RefRevisionLinkProps) {
  const [copied, setCopied] = useState(false);

  if (value == null) {
    return <Code c="dimmed">N/A</Code>;
  }

  const resourceId = revisionIdToResourceId(value);
  const detailRoute = getResourceDetailRoute(fieldRef.resource as ResourceName);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Group gap="xs" wrap="nowrap">
      <Tooltip label={`${fieldRef.resource} revision: ${value}`} position="top" withArrow>
        <Link
          to={detailRoute}
          params={{ resourceId }}
          search={{ revision: value }}
          onClick={(e) => e.stopPropagation()}
          onPointerDownCapture={(e) => e.stopPropagation()}
          onClickCapture={(e) => e.stopPropagation()}
          style={{ textDecoration: 'none' }}
        >
          <Group gap={4} wrap="nowrap">
            <Code style={{ cursor: 'pointer' }}>{shortId(value)}</Code>
            <IconExternalLink size={14} />
          </Group>
        </Link>
      </Tooltip>
      <Tooltip label={copied ? '已複製!' : '複製完整 Revision ID'} position="right">
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

interface RefRevisionLinkListProps {
  /** Array of revision IDs */
  values: string[] | null | undefined;
  /** Ref metadata from the field definition */
  fieldRef: FieldRef;
  /** Max items to show before collapsing (default: 5) */
  maxVisible?: number;
}

/**
 * Renders an array of revision IDs as a vertical list.
 * Used for list[Annotated[str, RefRevision(...)]] fields.
 */
export function RefRevisionLinkList({
  values,
  fieldRef,
  maxVisible = 5,
}: RefRevisionLinkListProps) {
  const [expanded, setExpanded] = useState(false);

  if (!values || values.length === 0) {
    return (
      <Text c="dimmed" size="sm">
        （空）
      </Text>
    );
  }

  const visible = expanded ? values : values.slice(0, maxVisible);
  const remaining = values.length - maxVisible;

  return (
    <Stack gap={4}>
      {visible.map((id) => (
        <RefRevisionLink key={id} value={id} fieldRef={fieldRef} />
      ))}
      {!expanded && remaining > 0 && (
        <Text size="xs" c="blue" style={{ cursor: 'pointer' }} onClick={() => setExpanded(true)}>
          +{remaining} more...
        </Text>
      )}
      {expanded && values.length > maxVisible && (
        <Text size="xs" c="blue" style={{ cursor: 'pointer' }} onClick={() => setExpanded(false)}>
          收起
        </Text>
      )}
    </Stack>
  );
}
