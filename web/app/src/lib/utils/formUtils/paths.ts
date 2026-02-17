/**
 * Path utility functions for nested object access and manipulation
 */

/**
 * Get a value from an object using dot-notation path
 * @param obj - The object to get the value from
 * @param path - Dot-notation path (e.g., "user.profile.name")
 * @returns The value at the path, or undefined if not found
 * 
 * @example
 * getByPath({ user: { name: 'Alice' } }, 'user.name') // 'Alice'
 * getByPath({ items: [{ id: 1 }] }, 'items.0.id') // 1
 * getByPath({}, 'nonexistent.path') // undefined
 */
export function getByPath(obj: Record<string, any>, path: string): any {
  if (!path) return obj;
  return path.split('.').reduce((o, k) => o?.[k], obj);
}

/**
 * Set a value in an object using dot-notation path
 * **Warning**: This function mutates the original object
 * 
 * @param obj - The object to set the value in (will be mutated)
 * @param path - Dot-notation path (e.g., "user.profile.name")
 * @param value - The value to set
 * 
 * @example
 * const obj = {};
 * setByPath(obj, 'user.name', 'Alice');
 * // obj is now { user: { name: 'Alice' } }
 * 
 * setByPath(obj, 'user.age', 30);
 * // obj is now { user: { name: 'Alice', age: 30 } }
 */
export function setByPath(obj: Record<string, any>, path: string, value: any): void {
  const keys = path.split('.');
  let current = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    if (current[keys[i]] == null || typeof current[keys[i]] !== 'object') {
      current[keys[i]] = {};
    }
    current = current[keys[i]];
  }
  current[keys[keys.length - 1]] = value;
}
