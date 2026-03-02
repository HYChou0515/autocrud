import { describe, expect, it } from 'vitest';
import { getByPath, setByPath } from './paths';

describe('getByPath', () => {
  it('should get value from simple path', () => {
    const obj = { name: 'Alice', age: 30 };
    expect(getByPath(obj, 'name')).toBe('Alice');
    expect(getByPath(obj, 'age')).toBe(30);
  });

  it('should get value from nested path', () => {
    const obj = { user: { profile: { name: 'Bob' } } };
    expect(getByPath(obj, 'user.profile.name')).toBe('Bob');
  });

  it('should get value from array index', () => {
    const obj = { items: [{ id: 1 }, { id: 2 }] };
    expect(getByPath(obj, 'items.0.id')).toBe(1);
    expect(getByPath(obj, 'items.1.id')).toBe(2);
  });

  it('should return undefined for non-existent path', () => {
    const obj = { user: { name: 'Charlie' } };
    expect(getByPath(obj, 'user.age')).toBeUndefined();
    expect(getByPath(obj, 'nonexistent')).toBeUndefined();
    expect(getByPath(obj, 'user.profile.name')).toBeUndefined();
  });

  it('should handle null or undefined intermediate values', () => {
    const obj = { user: null };
    expect(getByPath(obj, 'user.name')).toBeUndefined();
  });

  it('should handle empty path', () => {
    const obj = { name: 'David' };
    expect(getByPath(obj, '')).toEqual(obj);
  });

  it('should handle null object', () => {
    expect(getByPath(null as any, 'name')).toBeUndefined();
    expect(getByPath(undefined as any, 'name')).toBeUndefined();
  });
});

describe('setByPath', () => {
  it('should set value for simple path', () => {
    const obj: Record<string, any> = {};
    setByPath(obj, 'name', 'Alice');
    expect(obj.name).toBe('Alice');
  });

  it('should set value for nested path', () => {
    const obj: Record<string, any> = {};
    setByPath(obj, 'user.name', 'Bob');
    expect(obj.user.name).toBe('Bob');
  });

  it('should create intermediate objects', () => {
    const obj: Record<string, any> = {};
    setByPath(obj, 'user.profile.name', 'Charlie');
    expect(obj).toEqual({ user: { profile: { name: 'Charlie' } } });
  });

  it('should overwrite existing values', () => {
    const obj = { user: { name: 'Old' } };
    setByPath(obj, 'user.name', 'New');
    expect(obj.user.name).toBe('New');
  });

  it('should overwrite non-object intermediate values', () => {
    const obj = { user: 'string' };
    setByPath(obj, 'user.name', 'Alice');
    expect(obj.user).toEqual({ name: 'Alice' });
  });

  it('should set null value', () => {
    const obj: Record<string, any> = {};
    setByPath(obj, 'user.name', null);
    expect(obj.user.name).toBeNull();
  });

  it('should set undefined value', () => {
    const obj: Record<string, any> = {};
    setByPath(obj, 'user.name', undefined);
    expect(obj.user.name).toBeUndefined();
  });

  it('should handle deeply nested paths', () => {
    const obj: Record<string, any> = {};
    setByPath(obj, 'a.b.c.d.e.f', 'deep');
    expect(obj.a.b.c.d.e.f).toBe('deep');
  });
});
