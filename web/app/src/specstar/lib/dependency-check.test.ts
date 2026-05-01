/**
 * Dependency version check — regression tests for critical package versions.
 *
 * These tests verify that pinned package versions in package.json are actually
 * installed at the expected version. This catches cases where:
 * - A package is listed but not installed
 * - A package resolves to an unexpected version
 * - Someone accidentally changes the version range
 *
 * Run WITHOUT mocks — actually imports the real modules.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import path from 'path';

describe('Critical dependency versions', () => {
  it('@tanstack/react-query is installed at a 5.9x+ version', () => {
    // Read the installed package.json from node_modules
    const pkgPath = path.resolve(process.cwd(), 'node_modules/@tanstack/react-query/package.json');
    const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'));
    // Must be 5.93.0 or higher
    const [major, minor] = pkg.version.split('.').map(Number);
    expect(major).toBe(5);
    expect(minor).toBeGreaterThanOrEqual(93);
  });

  it('@tanstack/react-query version range is ^5.93 in package.json', () => {
    const rootPkg = JSON.parse(readFileSync(path.resolve(process.cwd(), 'package.json'), 'utf-8'));
    const version = rootPkg.dependencies?.['@tanstack/react-query'];
    expect(version).toBe('^5.93');
  });

  it('@tanstack/react-query exports can be imported without mocks', async () => {
    // This would fail if the package is missing from node_modules
    const rq = await import('@tanstack/react-query');
    expect(rq.QueryClient).toBeDefined();
    expect(rq.useQuery).toBeDefined();
    expect(rq.useMutation).toBeDefined();
    expect(rq.useQueryClient).toBeDefined();
    expect(rq.QueryClientProvider).toBeDefined();
  });
});
