import { describe, expect, it, beforeEach, vi } from 'vitest';
import {
  getCustomization,
  getRevisionViewMode,
  setRevisionViewMode,
  updateCustomization,
} from './customization';

type Store = Record<string, string>;

function createStorage() {
  let store: Store = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
}

describe('customization storage', () => {
  beforeEach(() => {
    const storage = createStorage();
    // Mock window object with localStorage
    vi.stubGlobal('window', {
      localStorage: storage,
    });
    window.localStorage.clear();
  });

  it('returns default customization when empty', () => {
    const customization = getCustomization();
    expect(customization.revisionViewMode).toBe('timeline');
  });

  it('persists revision view mode changes', () => {
    setRevisionViewMode('tree');
    expect(getRevisionViewMode()).toBe('tree');
  });

  it('merges partial updates with defaults', () => {
    updateCustomization({ revisionViewMode: 'tree' });
    const customization = getCustomization();
    expect(customization.revisionViewMode).toBe('tree');
  });
});
