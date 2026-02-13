import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-tw';
import { Tooltip } from '@mantine/core';

// Enable plugins
dayjs.extend(relativeTime);
dayjs.locale('zh-tw');

export interface TimeDisplayProps {
  time: string | Date;
  format?: 'relative' | 'full' | 'short' | 'date';
  showTooltip?: boolean;
}

/**
 * 統一的時間顯示組件
 * 
 * @param time - ISO 時間字串或 Date 物件
 * @param format - 顯示格式
 *   - 'relative': 相對時間（如 "2 小時前"）
 *   - 'full': 完整日期時間（如 "2026-02-09 15:30:45"）
 *   - 'short': 簡短格式（如 "02/09 15:30"）
 *   - 'date': 只顯示日期（如 "2026-02-09"）
 * @param showTooltip - 是否顯示完整時間的 tooltip（預設 true）
 */
export function TimeDisplay({ 
  time, 
  format = 'relative',
  showTooltip = true 
}: TimeDisplayProps) {
  const dayjsTime = dayjs(time);
  
  if (!dayjsTime.isValid()) {
    return <span>-</span>;
  }

  let displayText: string;
  
  switch (format) {
    case 'relative':
      displayText = dayjsTime.fromNow(); // "2 小時前"
      break;
    case 'full':
      displayText = dayjsTime.format('YYYY-MM-DD HH:mm:ss');
      break;
    case 'short':
      displayText = dayjsTime.format('MM/DD HH:mm');
      break;
    case 'date':
      displayText = dayjsTime.format('YYYY-MM-DD');
      break;
    default:
      displayText = dayjsTime.fromNow();
  }

  // If showTooltip is true and format is not 'full', show full time in tooltip
  if (showTooltip && format !== 'full') {
    return (
      <Tooltip label={dayjsTime.format('YYYY-MM-DD HH:mm:ss')}>
        <span style={{ cursor: 'help', borderBottom: '1px dotted currentColor' }}>
          {displayText}
        </span>
      </Tooltip>
    );
  }

  return <span>{displayText}</span>;
}

/**
 * 格式化時間（純函數，不含 UI）
 */
export function formatTime(
  time: string | Date, 
  format: 'relative' | 'full' | 'short' | 'date' = 'relative'
): string {
  const dayjsTime = dayjs(time);
  
  if (!dayjsTime.isValid()) {
    return '-';
  }

  switch (format) {
    case 'relative':
      return dayjsTime.fromNow();
    case 'full':
      return dayjsTime.format('YYYY-MM-DD HH:mm:ss');
    case 'short':
      return dayjsTime.format('MM/DD HH:mm');
    case 'date':
      return dayjsTime.format('YYYY-MM-DD');
    default:
      return dayjsTime.fromNow();
  }
}
