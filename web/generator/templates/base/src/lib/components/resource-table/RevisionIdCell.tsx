/**
 * Revision ID 顯示元件 - 智能顯示 revision ID
 * 
 * 對於格式 "resource_id:revision_number" 的 ID，只顯示版本號
 * 否則使用類似 ResourceIdCell 的簡短格式
 */

import { useState } from 'react';
import { Group, Tooltip, ActionIcon, Code, Text } from '@mantine/core';
import { IconCopy, IconCheck } from '@tabler/icons-react';

interface RevisionIdCellProps {
  revisionId: string;
  resourceId?: string;
  showCopy?: boolean;
}

/**
 * 從 revision_id 提取版本號
 * 例如：game-event:3322bb31-587b-460a-a0a1-8134fcc354eb:3 -> "3"
 */
function extractRevisionNumber(revisionId: string, resourceId?: string): string | null {
  if (resourceId && revisionId.startsWith(resourceId + ':')) {
    // revision_id 格式為 resource_id:revision_number
    const parts = revisionId.split(':');
    return parts[parts.length - 1];
  }
  
  // 嘗試從 revision_id 末尾提取數字
  const match = revisionId.match(/:(\d+)$/);
  if (match) {
    return match[1];
  }
  
  return null;
}

export function RevisionIdCell({ revisionId, resourceId, showCopy = true }: RevisionIdCellProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(revisionId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const revisionNumber = extractRevisionNumber(revisionId, resourceId);
  
  // 如果能提取版本號，顯示 "Rev #3"
  // 否則使用簡短格式
  const displayText = revisionNumber 
    ? `Rev #${revisionNumber}`
    : revisionId.length > 12 
      ? `${revisionId.slice(0, 4)}...${revisionId.slice(-4)}` 
      : revisionId;

  return (
    <Group gap="xs" wrap="nowrap">
      <Tooltip label={revisionId} position="top">
        <Code style={{ cursor: 'help' }}>{displayText}</Code>
      </Tooltip>
      {showCopy && (
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
      )}
    </Group>
  );
}
