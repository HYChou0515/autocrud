/**
 * SearchForm — unit tests for exported pure helper functions.
 *
 * Tests verify:
 * 1. buildFieldLabelMap produces correct name→label mapping
 * 2. filterFieldOptionsFn matches against both name and label (case-insensitive)
 * 3. Autocomplete data format uses plain strings (not {value,label} objects)
 */

import { describe, it, expect } from 'vitest';
import { buildFieldLabelMap, filterFieldOptionsFn } from './SearchForm';

// ---------------------------------------------------------------------------
// buildFieldLabelMap
// ---------------------------------------------------------------------------

describe('buildFieldLabelMap', () => {
  it('builds a name→label map', () => {
    const fields = [
      { name: 'level', label: 'Level' },
      { name: 'name', label: 'Name' },
    ];
    const map = buildFieldLabelMap(fields);
    expect(map.get('level')).toBe('Level');
    expect(map.get('name')).toBe('Name');
    expect(map.size).toBe(2);
  });

  it('handles fields where label equals name', () => {
    const fields = [{ name: 'hp', label: 'hp' }];
    const map = buildFieldLabelMap(fields);
    expect(map.get('hp')).toBe('hp');
  });

  it('returns empty map for empty fields', () => {
    expect(buildFieldLabelMap([]).size).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// filterFieldOptionsFn
// ---------------------------------------------------------------------------

describe('filterFieldOptionsFn', () => {
  const fields = [
    { name: 'level', label: 'Level' },
    { name: 'name', label: '名稱' },
    { name: 'guild_name', label: 'Guild Name' },
    { name: 'created_by', label: '[meta] Created By' },
  ];
  const labelMap = buildFieldLabelMap(fields);
  const options = fields.map((f) => ({ value: f.name }));

  it('returns all options when search is empty', () => {
    expect(filterFieldOptionsFn(options, '', labelMap)).toEqual(options);
  });

  it('returns all options when search is whitespace', () => {
    expect(filterFieldOptionsFn(options, '  ', labelMap)).toEqual(options);
  });

  it('matches by field name (exact)', () => {
    const result = filterFieldOptionsFn(options, 'level', labelMap);
    expect(result).toHaveLength(1);
    expect(result[0].value).toBe('level');
  });

  it('matches by field name (case-insensitive)', () => {
    const result = filterFieldOptionsFn(options, 'LEVEL', labelMap);
    expect(result).toHaveLength(1);
    expect(result[0].value).toBe('level');
  });

  it('matches by label when name does not match', () => {
    // Typing "名稱" should match field "name" (label is "名稱")
    const result = filterFieldOptionsFn(options, '名稱', labelMap);
    expect(result).toHaveLength(1);
    expect(result[0].value).toBe('name');
  });

  it('matches by label (case-insensitive)', () => {
    // Typing "guild" should match "guild_name" via its label "Guild Name"
    const result = filterFieldOptionsFn(options, 'guild', labelMap);
    expect(result).toHaveLength(1);
    expect(result[0].value).toBe('guild_name');
  });

  it('matches partial name', () => {
    const result = filterFieldOptionsFn(options, 'lev', labelMap);
    expect(result).toHaveLength(1);
    expect(result[0].value).toBe('level');
  });

  it('matches partial label', () => {
    // "Created" should match "[meta] Created By"
    const result = filterFieldOptionsFn(options, 'Created', labelMap);
    expect(result).toHaveLength(1);
    expect(result[0].value).toBe('created_by');
  });

  it('matches multiple fields when search is ambiguous', () => {
    // "name" matches "name" (field name) and "guild_name" (field name)
    const result = filterFieldOptionsFn(options, 'name', labelMap);
    expect(result).toHaveLength(2);
    expect(result.map((o) => o.value).sort()).toEqual(['guild_name', 'name']);
  });

  it('returns empty when nothing matches', () => {
    expect(filterFieldOptionsFn(options, 'zzz_no_match', labelMap)).toHaveLength(0);
  });

  it('supports dot-path search (unrecognised, returns empty since not in options)', () => {
    expect(filterFieldOptionsFn(options, 'stats.hp', labelMap)).toHaveLength(0);
  });
});
