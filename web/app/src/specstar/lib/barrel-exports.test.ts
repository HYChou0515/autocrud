/**
 * Barrel export coverage — ensures all index.ts re-export modules load correctly.
 */
import { describe, it, expect } from 'vitest';

describe('barrel exports', () => {
  it('hooks/index.ts re-exports', async () => {
    const mod = await import('@/specstar/lib/hooks/index');
    expect(mod.resourceKeys).toBeDefined();
    expect(mod.useResourceList).toBeDefined();
  });

  it('components/table/index.ts re-exports', async () => {
    const mod = await import('@/specstar/lib/components/table/index');
    expect(mod.ResourceTable).toBeDefined();
    expect(mod.SearchForm).toBeDefined();
    expect(mod.AdvancedSearchPanel).toBeDefined();
  });

  it('utils/formUtils/index.ts re-exports', async () => {
    const mod = await import('@/specstar/lib/utils/formUtils/index');
    expect(mod.getHandler).toBeDefined();
    expect(mod.computeMaxAvailableDepth).toBeDefined();
    expect(mod.processInitialValues).toBeDefined();
  });
});
