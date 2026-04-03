export type RevisionViewMode = 'timeline' | 'tree';

export interface CustomizationState {
  revisionViewMode: RevisionViewMode;
}

const customizationVersion = 1;
const storageKey = `autocrud:customization:v${customizationVersion}`;
const defaultCustomization: CustomizationState = {
  revisionViewMode: 'timeline',
};

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

export function getCustomization(): CustomizationState {
  if (!canUseStorage()) {
    return { ...defaultCustomization };
  }

  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) {
      return { ...defaultCustomization };
    }
    const parsed = JSON.parse(raw) as Partial<CustomizationState>;
    return { ...defaultCustomization, ...parsed };
  } catch (error) {
    console.warn('Failed to read customization from storage:', error);
    return { ...defaultCustomization };
  }
}

export function updateCustomization(next: Partial<CustomizationState>): CustomizationState {
  const merged = { ...getCustomization(), ...next };
  if (!canUseStorage()) {
    return merged;
  }

  try {
    window.localStorage.setItem(storageKey, JSON.stringify(merged));
  } catch (error) {
    console.warn('Failed to write customization to storage:', error);
  }
  return merged;
}

export function getRevisionViewMode(): RevisionViewMode {
  return getCustomization().revisionViewMode;
}

export function setRevisionViewMode(mode: RevisionViewMode): void {
  updateCustomization({ revisionViewMode: mode });
}
