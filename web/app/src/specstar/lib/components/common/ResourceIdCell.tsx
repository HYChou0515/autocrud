/**
 * Resource ID 顯示元件 - 顯示簡短版本，可複製完整 ID
 */

import { useState } from 'react';
import { Group, Tooltip, ActionIcon, Code } from '@mantine/core';
import { IconCopy, IconCheck } from '@tabler/icons-react';

interface ResourceIdCellProps {
  rid: string;
}

export function ResourceIdCell({ rid }: ResourceIdCellProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(rid);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const shortId = rid.length > 12 ? `${rid.slice(0, 4)}...${rid.slice(-4)}` : rid;

  return (
    <Group gap="xs" wrap="nowrap">
      <Tooltip label={rid} position="top">
        <Code style={{ cursor: 'help' }}>{shortId}</Code>
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
