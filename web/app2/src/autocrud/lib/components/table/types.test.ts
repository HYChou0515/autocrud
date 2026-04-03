/**
 * Tests for table/types.ts — operatorLabels and getDefaultOperators.
 */

import { describe, it, expect } from 'vitest';
import { operatorLabels, getDefaultOperators } from './types';

describe('operatorLabels', () => {
  it('contains all standard operators', () => {
    expect(operatorLabels.eq).toBe('=');
    expect(operatorLabels.ne).toBe('≠');
    expect(operatorLabels.gt).toBe('>');
    expect(operatorLabels.gte).toBe('≥');
    expect(operatorLabels.lt).toBe('<');
    expect(operatorLabels.lte).toBe('≤');
    expect(operatorLabels.in).toBe('IN');
    expect(operatorLabels.not_in).toBe('NOT IN');
    expect(operatorLabels.contains).toBe('包含');
    expect(operatorLabels.starts_with).toBe('開頭');
    expect(operatorLabels.ends_with).toBe('結尾');
  });
});

describe('getDefaultOperators', () => {
  it('returns string operators for string type', () => {
    const ops = getDefaultOperators('string');
    expect(ops).toContain('eq');
    expect(ops).toContain('contains');
    expect(ops).toContain('starts_with');
    expect(ops).toContain('ends_with');
  });

  it('returns numeric operators for number type', () => {
    const ops = getDefaultOperators('number');
    expect(ops).toContain('eq');
    expect(ops).toContain('gt');
    expect(ops).toContain('gte');
    expect(ops).toContain('lt');
    expect(ops).toContain('lte');
  });

  it('returns numeric operators for date type', () => {
    const ops = getDefaultOperators('date');
    expect(ops).toContain('gt');
    expect(ops).toContain('lte');
  });

  it('returns boolean operators for boolean type', () => {
    const ops = getDefaultOperators('boolean');
    expect(ops).toEqual(['eq', 'ne']);
  });

  it('returns select operators for select type', () => {
    const ops = getDefaultOperators('select');
    expect(ops).toContain('eq');
    expect(ops).toContain('in');
  });

  it('returns default operators for unknown type', () => {
    const ops = getDefaultOperators('unknown' as any);
    expect(ops).toEqual(['eq', 'ne']);
  });
});
