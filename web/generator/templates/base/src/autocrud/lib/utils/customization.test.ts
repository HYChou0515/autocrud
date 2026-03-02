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

  it('returns default when window is undefined', () => {
    vi.stubGlobal('window', undefined);
    const customization = getCustomization();
    expect(customization.revisionViewMode).toBe('timeline');
  });

  it('returns default when localStorage is undefined', () => {
    vi.stubGlobal('window', {});
    const customization = getCustomization();
    expect(customization.revisionViewMode).toBe('timeline');
  });

  it('handles JSON parse errors gracefully', () => {
    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    window.localStorage.setItem('autocrud:customization:v1', 'invalid json');

    const customization = getCustomization();
    expect(customization.revisionViewMode).toBe('timeline');
    expect(consoleWarnSpy).toHaveBeenCalledWith(
      'Failed to read customization from storage:',
      expect.any(Error),
    );

    consoleWarnSpy.mockRestore();
  });

  it('returns merged state when storage is unavailable during update', () => {
    vi.stubGlobal('window', undefined);

    const result = updateCustomization({ revisionViewMode: 'tree' });
    expect(result.revisionViewMode).toBe('tree');
  });

  it('handles localStorage.setItem errors gracefully', () => {
    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const storage = createStorage();
    storage.setItem = () => {
      throw new Error('Storage full');
    };
    vi.stubGlobal('window', { localStorage: storage });

    const result = updateCustomization({ revisionViewMode: 'tree' });
    expect(result.revisionViewMode).toBe('tree');
    expect(consoleWarnSpy).toHaveBeenCalledWith(
      'Failed to write customization to storage:',
      expect.any(Error),
    );

    consoleWarnSpy.mockRestore();
  });
});
