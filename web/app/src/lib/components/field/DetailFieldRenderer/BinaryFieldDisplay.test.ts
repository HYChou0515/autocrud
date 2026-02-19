import { describe, it, expect } from 'vitest';
import { formatSize } from './BinaryFieldDisplay';

describe('formatSize', () => {
  it('returns bytes for values < 1024', () => {
    expect(formatSize(0)).toBe('0 B');
    expect(formatSize(512)).toBe('512 B');
    expect(formatSize(1023)).toBe('1023 B');
  });

  it('returns KB for values < 1MB', () => {
    expect(formatSize(1024)).toBe('1.0 KB');
    expect(formatSize(1536)).toBe('1.5 KB');
    expect(formatSize(1024 * 512)).toBe('512.0 KB');
  });

  it('returns MB for values >= 1MB', () => {
    expect(formatSize(1024 * 1024)).toBe('1.0 MB');
    expect(formatSize(1024 * 1024 * 2.5)).toBe('2.5 MB');
    expect(formatSize(1024 * 1024 * 100)).toBe('100.0 MB');
  });
});
