/**
 * CollapsibleJson — A collapsible JSON viewer for detail display.
 *
 * Shows a compact summary (e.g. `{3 keys}` or `[5 items]`) by default.
 * Click the summary to expand into a full pretty-printed JSON code block.
 */

import { useState } from 'react';
import { Code, UnstyledButton, Group, Text } from '@mantine/core';
import { IconChevronRight, IconChevronDown } from '@tabler/icons-react';

export interface CollapsibleJsonProps {
  value: unknown;
  defaultExpanded?: boolean;
}

/** Build a one-line summary string for the collapsed state. */
function summarise(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.length} item${value.length === 1 ? '' : 's'}]`;
  }
  if (typeof value === 'object' && value !== null) {
    const keys = Object.keys(value);
    return `{${keys.length} key${keys.length === 1 ? '' : 's'}}`;
  }
  return String(value);
}

export function CollapsibleJson({ value, defaultExpanded = false }: CollapsibleJsonProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  if (value == null) {
    return (
      <Text c="dimmed" size="sm">
        N/A
      </Text>
    );
  }

  // Primitive values — no need for collapse
  if (typeof value !== 'object') {
    return <Code>{String(value)}</Code>;
  }

  const jsonStr = JSON.stringify(value, null, 2);

  // Small enough to show inline (≤ 120 chars) — just show it
  if (jsonStr.length <= 120) {
    return <Code block>{jsonStr}</Code>;
  }

  return (
    <div>
      <UnstyledButton onClick={() => setExpanded((e) => !e)}>
        <Group gap={4}>
          {expanded ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
          <Text size="sm" c="dimmed" ff="monospace">
            {summarise(value)}
          </Text>
        </Group>
      </UnstyledButton>
      {expanded && (
        <Code block mt={4}>
          {jsonStr}
        </Code>
      )}
    </div>
  );
}
