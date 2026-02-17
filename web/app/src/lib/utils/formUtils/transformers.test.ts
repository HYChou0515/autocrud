import { describe, expect, it } from 'vitest';
import {
  isCollapsedChild,
  processInitialValues,
  formValuesToApiObject,
  applyJsonToForm,
} from './transformers';
import type { BinaryFormValue } from './types';

describe('isCollapsedChild', () => {
  it('should return true for child field', () => {
    const collapsedGroups = [{ path: 'user', label: 'User' }];
    expect(isCollapsedChild('user.name', collapsedGroups)).toBe(true);
    expect(isCollapsedChild('user.profile.bio', collapsedGroups)).toBe(true);
  });

  it('should return false for non-child field', () => {
    const collapsedGroups = [{ path: 'user', label: 'User' }];
    expect(isCollapsedChild('name', collapsedGroups)).toBe(false);
    expect(isCollapsedChild('admin.name', collapsedGroups)).toBe(false);
  });

  it('should return false for parent field itself', () => {
    const collapsedGroups = [{ path: 'user.profile', label: 'Profile' }];
    expect(isCollapsedChild('user', collapsedGroups)).toBe(false);
  });

  it('should handle multiple collapsed groups', () => {
    const collapsedGroups = [
      { path: 'user', label: 'User' },
      { path: 'admin', label: 'Admin' },
    ];
    expect(isCollapsedChild('user.name', collapsedGroups)).toBe(true);
    expect(isCollapsedChild('admin.role', collapsedGroups)).toBe(true);
    expect(isCollapsedChild('other.field', collapsedGroups)).toBe(false);
  });

  it('should handle empty collapsed groups', () => {
    expect(isCollapsedChild('any.field', [])).toBe(false);
  });
});

describe('processInitialValues', () => {
  it('should convert date strings to Date objects', () => {
    const fields = [{ name: 'created_at', type: 'date' as const }];
    const dateFieldNames = ['created_at'];
    
    const result = processInitialValues(
      { created_at: '2024-01-01T00:00:00Z' },
      fields,
      [],
      dateFieldNames,
    );
    
    expect(result.created_at).toBeInstanceOf(Date);
    expect(result.created_at.toISOString()).toMatch(/^2024-01-01T00:00:00/);
  });

  it('should handle null date fields', () => {
    const fields = [{ name: 'updated_at', type: 'date' as const }];
    const dateFieldNames = ['updated_at'];
    
    const result = processInitialValues(
      { updated_at: null },
      fields,
      [],
      dateFieldNames,
    );
    
    expect(result.updated_at).toBeNull();
  });

  it('should convert binary data to BinaryFormValue', () => {
    const fields = [{ name: 'avatar', type: 'binary' as const }];
    
    const result = processInitialValues(
      { avatar: { file_id: 'abc123', content_type: 'image/png', size: 1024 } },
      fields,
      [],
      [],
    );
    
    expect(result.avatar).toEqual({
      _mode: 'existing',
      file_id: 'abc123',
      content_type: 'image/png',
      size: 1024,
    });
  });

  it('should set binary to empty mode when null', () => {
    const fields = [{ name: 'avatar', type: 'binary' as const }];
    
    const result = processInitialValues({ avatar: null }, fields, [], []);
    
    expect(result.avatar).toEqual({ _mode: 'empty' });
  });

  it('should keep array ref fields as arrays', () => {
    const fields = [
      { name: 'tags', isArray: true, ref: { resource: 'tag', type: 'resource_id' as const } },
    ];
    
    const result = processInitialValues({ tags: ['a', 'b', 'c'] }, fields, [], []);
    
    expect(result.tags).toEqual(['a', 'b', 'c']);
  });

  it('should default array ref to empty array', () => {
    const fields = [
      { name: 'tags', isArray: true, ref: { resource: 'tag', type: 'resource_id' as const } },
    ];
    
    const result = processInitialValues({ tags: null }, fields, [], []);
    
    expect(result.tags).toEqual([]);
  });

  it('should convert null to empty string for string fields', () => {
    const fields = [{ name: 'name', type: 'string' as const }];
    
    const result = processInitialValues({ name: null }, fields, [], []);
    
    expect(result.name).toBe('');
  });

  it('should convert null to empty string for number fields', () => {
    const fields = [{ name: 'age', type: 'number' as const }];
    
    const result = processInitialValues({ age: null }, fields, [], []);
    
    expect(result.age).toBe('');
  });

  it('should convert null to false for boolean fields', () => {
    const fields = [{ name: 'active', type: 'boolean' as const }];
    
    const result = processInitialValues({ active: null }, fields, [], []);
    
    expect(result.active).toBe(false);
  });

  it('should keep null for nullable enum fields', () => {
    const fields = [{ name: 'status', enumValues: ['a', 'b'], isNullable: true }];
    
    const result = processInitialValues({ status: null }, fields, [], []);
    
    expect(result.status).toBeNull();
  });

  it('should convert object to JSON string', () => {
    const fields = [{ name: 'metadata', type: 'object' as const }];
    
    const result = processInitialValues({ metadata: { key: 'value' } }, fields, [], []);
    
    expect(result.metadata).toBe('{\n  "key": "value"\n}');
  });

  it('should handle itemFields with binary sub-fields', () => {
    const fields = [
      {
        name: 'items',
        itemFields: [
          { name: 'id', type: 'number' as const },
          { name: 'image', type: 'binary' as const },
        ],
      },
    ];
    
    const result = processInitialValues(
      {
        items: [
          { id: 1, image: { file_id: 'img1', content_type: 'image/png', size: 100 } },
          { id: 2, image: null },
        ],
      },
      fields,
      [],
      [],
    );
    
    expect(result.items[0].image).toEqual({
      _mode: 'existing',
      file_id: 'img1',
      content_type: 'image/png',
      size: 100,
    });
    expect(result.items[1].image).toEqual({ _mode: 'empty' });
  });

  it('should convert array string sub-fields to comma-separated', () => {
    const fields = [
      {
        name: 'items',
        itemFields: [{ name: 'tags', isArray: true, type: 'string' as const }],
      },
    ];
    
    const result = processInitialValues(
      { items: [{ tags: ['a', 'b', 'c'] }] },
      fields,
      [],
      [],
    );
    
    expect(result.items[0].tags).toBe('a, b, c');
  });

  it('should handle collapsed groups', () => {
    const fields = [
      { name: 'user.name' },
      { name: 'user.email' },
    ];
    const collapsedGroups = [{ path: 'user', label: 'User' }];
    
    const result = processInitialValues(
      { user: { name: 'Alice', email: 'alice@example.com' } },
      fields,
      collapsedGroups,
      [],
    );
    
    expect(result.user).toBe('{\n  "name": "Alice",\n  "email": "alice@example.com"\n}');
  });

  it('should set collapsed group to JSON string with default fields when null', () => {
    const fields = [{ name: 'user.name' }];
    const collapsedGroups = [{ path: 'user', label: 'User' }];
    
    const result = processInitialValues({ user: null }, fields, collapsedGroups, []);
    
    // When collapsed group is null, setByPath for "user.name" creates { user: { name: '' } }
    // Then it gets stringified
    expect(result.user).toContain('"name"');
    expect(() => JSON.parse(result.user)).not.toThrow();
  });

  it('should deep clone nested objects', () => {
    const fields = [{ name: 'nested.value' }];
    const original = { nested: { value: 'test' } };
    
    const result = processInitialValues(original, fields, [], []);
    
    // Mutate result
    result.nested.value = 'changed';
    
    // Original should not be affected
    expect(original.nested.value).toBe('test');
  });
});

describe('formValuesToApiObject', () => {
  it('should convert Date objects to ISO strings', () => {
    const fields = [{ name: 'created_at', type: 'date' as const }];
    const dateFieldNames = ['created_at'];
    const date = new Date('2024-01-01T00:00:00Z');
    
    const result = formValuesToApiObject({ created_at: date }, fields, [], dateFieldNames);
    
    expect(result.created_at).toBe('2024-01-01T00:00:00.000Z');
  });

  it('should convert date strings to ISO strings', () => {
    const fields = [{ name: 'created_at', type: 'date' as const }];
    const dateFieldNames = ['created_at'];
    
    const result = formValuesToApiObject(
      { created_at: '2024-01-01' },
      fields,
      [],
      dateFieldNames,
    );
    
    expect(typeof result.created_at).toBe('string');
    expect(result.created_at).toContain('2024-01-01');
  });

  it('should preserve existing binary file_id', () => {
    const fields = [{ name: 'avatar', type: 'binary' as const }];
    const binaryVal: BinaryFormValue = {
      _mode: 'existing',
      file_id: 'abc123',
      content_type: 'image/png',
      size: 1024,
    };
    
    const result = formValuesToApiObject({ avatar: binaryVal }, fields, [], []);
    
    expect(result.avatar).toEqual({
      file_id: 'abc123',
      content_type: 'image/png',
      size: 1024,
    });
  });

  it('should show pending marker for file mode binary', () => {
    const fields = [{ name: 'avatar', type: 'binary' as const }];
    const file = new File(['test'], 'test.txt', { type: 'text/plain' });
    const binaryVal: BinaryFormValue = { _mode: 'file', file };
    
    const result = formValuesToApiObject({ avatar: binaryVal }, fields, [], []);
    
    expect(result.avatar).toEqual({
      _pending_file: 'test.txt',
      content_type: 'text/plain',
    });
  });

  it('should show pending marker for url mode binary', () => {
    const fields = [{ name: 'avatar', type: 'binary' as const }];
    const binaryVal: BinaryFormValue = { _mode: 'url', url: 'https://example.com/image.png' };
    
    const result = formValuesToApiObject({ avatar: binaryVal }, fields, [], []);
    
    expect(result.avatar).toEqual({ _pending_url: 'https://example.com/image.png' });
  });

  it('should parse JSON string to object', () => {
    const fields = [{ name: 'metadata', type: 'object' as const }];
    
    const result = formValuesToApiObject(
      { metadata: '{"key": "value"}' },
      fields,
      [],
      [],
    );
    
    expect(result.metadata).toEqual({ key: 'value' });
  });

  it('should handle itemFields with all sub-field types', () => {
    const fields = [
      {
        name: 'items',
        itemFields: [
          { name: 'name', type: 'string' as const },
          { name: 'tags', isArray: true, type: 'string' as const },
          { name: 'count', type: 'number' as const },
        ],
      },
    ];
    
    const result = formValuesToApiObject(
      {
        items: [
          { name: 'Item 1', tags: 'a, b, c', count: '' },
        ],
      },
      fields,
      [],
      [],
    );
    
    expect(result.items[0]).toEqual({
      name: 'Item 1',
      tags: ['a', 'b', 'c'],
      count: undefined, // Empty string for number becomes undefined
    });
  });

  it('should convert nullable string empty to null', () => {
    const fields = [{ name: 'description', type: 'string' as const, isNullable: true }];
    
    const result = formValuesToApiObject({ description: '' }, fields, [], []);
    
    expect(result.description).toBeNull();
  });

  it('should parse collapsed group JSON strings', () => {
    const fields = [{ name: 'user.name' }, { name: 'user.email' }];
    const collapsedGroups = [{ path: 'user', label: 'User' }];
    
    const result = formValuesToApiObject(
      { user: '{"name": "Alice", "email": "alice@example.com"}' },
      fields,
      collapsedGroups,
      [],
    );
    
    expect(result.user).toEqual({ name: 'Alice', email: 'alice@example.com' });
  });

  it('should skip collapsed child fields', () => {
    const fields = [{ name: 'user.name' }, { name: 'user.email' }];
    const collapsedGroups = [{ path: 'user', label: 'User' }];
    
    const result = formValuesToApiObject(
      { user: '{"name": "Alice"}', 'user.name': 'Bob' },
      fields,
      collapsedGroups, // 3rd param: collapsedGroups
      [], // 4th param: dateFieldNames
    );
    
    // Top-level keys should only contain 'user', not 'user.name' string literal
    expect(Object.keys(result)).toEqual(['user']); // Only has 'user' key
    expect('user.name' in result).toBe(false); // No string literal key 'user.name' 
    expect(result.user).toEqual({ name: 'Alice' }); // Collapsed group parsed from JSON
  });
});

describe('applyJsonToForm', () => {
  it('should convert date strings to Date objects', () => {
    const fields = [{ name: 'created_at', type: 'date' as const }];
    const dateFieldNames = ['created_at'];
    
    const result = applyJsonToForm(
      { created_at: '2024-01-01T00:00:00Z' },
      fields,
      [],
      dateFieldNames,
    );
    
    expect(result.created_at).toBeInstanceOf(Date);
  });

  it('should handle invalid date strings', () => {
    const fields = [{ name: 'created_at', type: 'date' as const }];
    const dateFieldNames = ['created_at'];
    
    const result = applyJsonToForm(
      { created_at: 'invalid date' },
      fields,
      [],
      dateFieldNames,
    );
    
    expect(result.created_at).toBeNull();
  });

  it('should convert binary object to BinaryFormValue', () => {
    const fields = [{ name: 'avatar', type: 'binary' as const }];
    
    const result = applyJsonToForm(
      { avatar: { file_id: 'abc123', content_type: 'image/png', size: 1024 } },
      fields,
      [],
      [],
    );
    
    expect(result.avatar).toEqual({
      _mode: 'existing',
      file_id: 'abc123',
      content_type: 'image/png',
      size: 1024,
    });
  });

  it('should set binary to empty mode when null', () => {
    const fields = [{ name: 'avatar', type: 'binary' as const }];
    
    const result = applyJsonToForm({ avatar: null }, fields, [], []);
    
    expect(result.avatar).toEqual({ _mode: 'empty' });
  });

  it('should convert object to JSON string', () => {
    const fields = [{ name: 'metadata', type: 'object' as const }];
    
    const result = applyJsonToForm({ metadata: { key: 'value' } }, fields, [], []);
    
    expect(result.metadata).toBe('{\n  "key": "value"\n}');
  });

  it('should convert number to empty string when null', () => {
    const fields = [{ name: 'age', type: 'number' as const }];
    
    const result = applyJsonToForm({ age: null }, fields, [], []);
    
    expect(result.age).toBe('');
  });

  it('should convert boolean to false when null', () => {
    const fields = [{ name: 'active', type: 'boolean' as const }];
    
    const result = applyJsonToForm({ active: null }, fields, [], []);
    
    expect(result.active).toBe(false);
  });

  it('should handle itemFields with array string conversion', () => {
    const fields = [
      {
        name: 'items',
        itemFields: [{ name: 'tags', isArray: true, type: 'string' as const }],
      },
    ];
    
    const result = applyJsonToForm(
      { items: [{ tags: ['a', 'b', 'c'] }] },
      fields,
      [],
      [],
    );
    
    expect(result.items[0].tags).toBe('a, b, c');
  });

  it('should handle collapsed groups', () => {
    const fields = [{ name: 'user.name' }, { name: 'user.email' }];
    const collapsedGroups = [{ path: 'user', label: 'User' }];
    
    const result = applyJsonToForm(
      { user: { name: 'Alice', email: 'alice@example.com' } },
      fields,
      collapsedGroups,
      [],
    );
    
    expect(result.user).toBe('{\n  "name": "Alice",\n  "email": "alice@example.com"\n}');
  });

  it('should set collapsed group to empty object string when null', () => {
    const fields = [{ name: 'user.name' }];
    const collapsedGroups = [{ path: 'user', label: 'User' }];
    
    const result = applyJsonToForm({ user: null }, fields, collapsedGroups, []);
    
    expect(result.user).toBe('{}');
  });

  it('should convert empty itemFields array to empty array', () => {
    const fields = [
      {
        name: 'items',
        itemFields: [{ name: 'id' }],
      },
    ];
    
    const result = applyJsonToForm({ items: null }, fields, [], []);
    
    expect(result.items).toEqual([]);
  });
});
