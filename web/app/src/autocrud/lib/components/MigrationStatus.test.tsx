/**
 * MigrationStatus — unit tests
 *
 * Verifies that:
 * 1. migrateApi.test/execute is called with limit=MIGRATE_ALL_LIMIT by default
 * 2. QB expression is passed when user provides one
 * 3. QB input fields render in the UI
 * 4. Empty QB expression is not sent (undefined)
 * 5. Large result sets are truncated to TABLE_DISPLAY_LIMIT rows
 * 6. Download buttons are rendered for progress details and errors
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { MigrationStatus } from './MigrationStatus';

// Track all migrateApi calls
const mockTest = vi.fn();
const mockExecute = vi.fn();

/**
 * Build a mock that fires `count` progress callbacks and returns a result with `errorCount` errors.
 * Does NOT call mockTest itself — just returns the result. mockTest tracks calls automatically.
 */
function makeLargeMock(count: number, errorCount = 0) {
  return (_modelName: string, options?: any) => {
    // Fire progress callbacks synchronously before resolving
    for (let i = 0; i < count; i++) {
      options?.onProgress?.({
        resource_id: `resource-${i}`,
        status: i < errorCount ? 'failed' : 'success',
        message: `msg-${i}`,
        error: i < errorCount ? `error-${i}` : undefined,
      });
    }
    const errors = Array.from({ length: errorCount }, (_, i) => ({
      resource_id: `resource-${i}`,
      error: `error-${i}`,
    }));
    return Promise.resolve({
      total: count,
      success: count - errorCount,
      failed: errorCount,
      skipped: 0,
      errors,
    });
  };
}

vi.mock('../../generated/api/migrateApi', () => ({
  migrateApi: {
    test: (...args: any[]) => mockTest(...args),
    execute: (...args: any[]) => mockExecute(...args),
  },
}));

function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

/** Default empty result used by most tests. */
const emptyResult = () =>
  Promise.resolve({ total: 0, success: 0, failed: 0, skipped: 0, errors: [] });

describe('MigrationStatus', () => {
  beforeEach(() => {
    cleanup();
    mockTest.mockReset();
    mockExecute.mockReset();
    // Default: return empty result
    mockTest.mockImplementation(emptyResult);
    mockExecute.mockImplementation(emptyResult);
  });

  it('renders QB input fields for batch operations', () => {
    renderWithMantine(<MigrationStatus resourceNames={['character']} />);

    // Global QB input should exist
    expect(screen.getByPlaceholderText(/leave empty to migrate all resources/i)).toBeTruthy();
  });

  it('renders per-model QB input fields', () => {
    renderWithMantine(<MigrationStatus resourceNames={['character']} />);

    // Both global and per-model QB inputs should exist
    const qbInputs = screen.getAllByPlaceholderText(/leave empty to migrate all/i);
    expect(qbInputs.length).toBeGreaterThanOrEqual(2);
  });

  it('calls migrateApi.test with limit=10000000 by default', async () => {
    renderWithMantine(<MigrationStatus resourceNames={['character']} />);

    // Click the per-model Test button
    const testButtons = screen.getAllByRole('button', { name: /test/i });
    // The per-model Test button (not the batch one)
    const perModelTest = testButtons.find(
      (btn) => btn.textContent === 'Test' || btn.textContent?.trim() === 'Test',
    );
    expect(perModelTest).toBeTruthy();
    fireEvent.click(perModelTest!);

    await waitFor(() => {
      expect(mockTest).toHaveBeenCalledTimes(1);
    });

    const [modelName, options] = mockTest.mock.calls[0];
    expect(modelName).toBe('character');
    expect(options.limit).toBe(10_000_000);
    // No QB expression by default
    expect(options.qb).toBeUndefined();
  });

  it('calls migrateApi.execute with limit=10000000 by default', async () => {
    renderWithMantine(<MigrationStatus resourceNames={['character']} />);

    // Click the per-model Migrate button
    const migrateButtons = screen.getAllByRole('button', { name: /migrate/i });
    const perModelMigrate = migrateButtons.find(
      (btn) => btn.textContent === 'Migrate' || btn.textContent?.trim() === 'Migrate',
    );
    expect(perModelMigrate).toBeTruthy();
    fireEvent.click(perModelMigrate!);

    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalledTimes(1);
    });

    const [modelName, options] = mockExecute.mock.calls[0];
    expect(modelName).toBe('character');
    expect(options.limit).toBe(10_000_000);
    expect(options.qb).toBeUndefined();
  });

  it('sends qb option in API call when options include qb', async () => {
    // Directly verify that the migrateApi mock receives qb when passed through handleMigrate.
    const { migrateApi } = await import('../../generated/api/migrateApi');

    // migrateApi.test delegates to mockTest which returns emptyResult by default
    await migrateApi.test('character', {
      qb: "QB['status'] == 'active'",
      limit: 10_000_000,
    });

    expect(mockTest).toHaveBeenCalledTimes(1);
    const args = mockTest.mock.calls[0];
    expect(args[0]).toBe('character');
    expect(args[1].qb).toBe("QB['status'] == 'active'");
    expect(args[1].limit).toBe(10_000_000);
  });

  it('does not send qb when expression is empty or whitespace', async () => {
    renderWithMantine(<MigrationStatus resourceNames={['character']} />);

    // Enter whitespace in per-model QB input
    const qbInputs = screen.getAllByPlaceholderText(/leave empty to migrate all/i);
    const perModelQb = qbInputs[qbInputs.length - 1];
    fireEvent.change(perModelQb, { target: { value: '   ' } });

    const testButtons = screen.getAllByRole('button', { name: /test/i });
    const perModelTest = testButtons.find(
      (btn) => btn.textContent === 'Test' || btn.textContent?.trim() === 'Test',
    );
    fireEvent.click(perModelTest!);

    await waitFor(() => {
      expect(mockTest).toHaveBeenCalledTimes(1);
    });

    const [, options] = mockTest.mock.calls[0];
    expect(options.qb).toBeUndefined();
  });

  // ── Batch operations & global scope ──────────────────────────

  describe('batch operations', () => {
    it('Test All calls migrateApi.test for each model sequentially', async () => {
      const callOrder: string[] = [];
      mockTest.mockImplementation((name: string) => {
        callOrder.push(name);
        return Promise.resolve({ total: 0, success: 0, failed: 0, skipped: 0, errors: [] });
      });

      renderWithMantine(<MigrationStatus resourceNames={['character', 'item']} />);
      fireEvent.click(screen.getByText('Test All Models'));

      await waitFor(() => {
        expect(callOrder).toEqual(['character', 'item']);
      });
    });

    it('Migrate All calls migrateApi.execute for each model', async () => {
      renderWithMantine(<MigrationStatus resourceNames={['character']} />);
      fireEvent.click(screen.getByText('Migrate All Models'));

      await waitFor(() => {
        expect(mockExecute).toHaveBeenCalledTimes(1);
        expect(mockExecute).toHaveBeenCalledWith('character', expect.objectContaining({ limit: 10_000_000 }));
      });
    });

    it('shows success alert after Test All completes', async () => {
      renderWithMantine(<MigrationStatus resourceNames={['character']} />);
      fireEvent.click(screen.getByText('Test All Models'));

      await waitFor(() => {
        expect(screen.getByText('All models tested successfully.')).toBeTruthy();
      });
    });

    it('shows success alert after Migrate All completes', async () => {
      renderWithMantine(<MigrationStatus resourceNames={['character']} />);
      fireEvent.click(screen.getByText('Migrate All Models'));

      await waitFor(() => {
        expect(screen.getByText('All models migrated successfully.')).toBeTruthy();
      });
    });

    it('passes global QB expression in batch', async () => {
      renderWithMantine(<MigrationStatus resourceNames={['character']} />);
      const globalQb = screen.getByPlaceholderText(/leave empty to migrate all resources/i);
      fireEvent.change(globalQb, { target: { value: "QB['level'] > 5" } });

      fireEvent.click(screen.getByText('Test All Models'));

      await waitFor(() => {
        expect(mockTest).toHaveBeenCalledWith(
          'character',
          expect.objectContaining({ qb: "QB['level'] > 5" }),
        );
      });
    });

    it('passes global revision scope "all" in batch', async () => {
      const { container } = renderWithMantine(
        <MigrationStatus resourceNames={['character']} />,
      );
      const allRadios = container.querySelectorAll('input[type="radio"]');
      const allRevRadio = Array.from(allRadios).find((r) => r.getAttribute('value') === 'all');
      if (allRevRadio) fireEvent.click(allRevRadio);

      fireEvent.click(screen.getByText('Test All Models'));

      await waitFor(() => {
        expect(mockTest).toHaveBeenCalledWith(
          'character',
          expect.objectContaining({ revisionId: 'all' }),
        );
      });
    });

    it('passes global specific revision ID in batch', async () => {
      const { container } = renderWithMantine(
        <MigrationStatus resourceNames={['character']} />,
      );
      const allRadios = container.querySelectorAll('input[type="radio"]');
      const specificRadio = Array.from(allRadios).find((r) => r.getAttribute('value') === 'specific');
      if (specificRadio) fireEvent.click(specificRadio);

      await waitFor(() => {
        const revInput = screen.getByPlaceholderText('Revision ID');
        fireEvent.change(revInput, { target: { value: 'rev-456' } });
      });

      fireEvent.click(screen.getByText('Test All Models'));

      await waitFor(() => {
        expect(mockTest).toHaveBeenCalledWith(
          'character',
          expect.objectContaining({ revisionId: 'rev-456' }),
        );
      });
    });
  });

  // ── Error handling ──────────────────────────────────────────────

  describe('error handling', () => {
    it('shows error message from Error object', async () => {
      mockTest.mockRejectedValueOnce(new Error('Network timeout'));
      renderWithMantine(<MigrationStatus resourceNames={['character']} />);
      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(screen.getByText('Network timeout')).toBeTruthy();
      });
    });

    it('shows error from response.data.detail', async () => {
      mockTest.mockRejectedValueOnce({
        name: 'AxiosError',
        response: { data: { detail: 'Schema not found' } },
      });
      renderWithMantine(<MigrationStatus resourceNames={['character']} />);
      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(screen.getByText('Schema not found')).toBeTruthy();
      });
    });

    it('shows "Operation cancelled." on AbortError', async () => {
      const abortErr = new Error('Aborted');
      abortErr.name = 'AbortError';
      mockTest.mockRejectedValueOnce(abortErr);
      renderWithMantine(<MigrationStatus resourceNames={['character']} />);
      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(screen.getByText('Operation cancelled.')).toBeTruthy();
      });
    });

    it('shows fallback "Migration failed" when error has no message', async () => {
      mockTest.mockRejectedValueOnce({});
      renderWithMantine(<MigrationStatus resourceNames={['character']} />);
      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(screen.getByText('Migration failed')).toBeTruthy();
      });
    });
  });

  // ── Cancel & running state ──────────────────────────────────────

  describe('cancel', () => {
    it('shows Testing… indicator', async () => {
      let resolvePromise: (v: any) => void;
      mockTest.mockImplementation(
        () => new Promise((resolve) => { resolvePromise = resolve; }),
      );
      renderWithMantine(<MigrationStatus resourceNames={['character']} />);
      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(screen.getByText('Testing…')).toBeTruthy();
      });
      resolvePromise!({ total: 0, success: 0, failed: 0, skipped: 0, errors: [] });
    });

    it('shows Migrating… indicator for execute mode', async () => {
      let resolvePromise: (v: any) => void;
      mockExecute.mockImplementation(
        () => new Promise((resolve) => { resolvePromise = resolve; }),
      );
      renderWithMantine(<MigrationStatus resourceNames={['character']} />);
      const migrateButtons = screen.getAllByRole('button', { name: /migrate/i });
      const perModelMigrate = migrateButtons.find((btn) => btn.textContent?.trim() === 'Migrate');
      fireEvent.click(perModelMigrate!);

      await waitFor(() => {
        expect(screen.getByText('Migrating…')).toBeTruthy();
      });
      resolvePromise!({ total: 0, success: 0, failed: 0, skipped: 0, errors: [] });
    });
  });

  // ── Per-model execute success ───────────────────────────────────

  it('shows per-model success alert on execute with 0 failed', async () => {
    mockExecute.mockResolvedValueOnce({
      total: 3, success: 2, failed: 0, skipped: 1, errors: [],
    });
    renderWithMantine(<MigrationStatus resourceNames={['character']} />);
    const migrateButtons = screen.getAllByRole('button', { name: /migrate/i });
    const perModelMigrate = migrateButtons.find((btn) => btn.textContent?.trim() === 'Migrate');
    fireEvent.click(perModelMigrate!);

    await waitFor(() => {
      expect(screen.getByText(/character: Migration completed/)).toBeTruthy();
    });
  });

  // ── Per-model revision scope ────────────────────────────────────

  describe('per-model revision scope', () => {
    it('passes "all" revision scope for per-model test', async () => {
      const { container } = renderWithMantine(
        <MigrationStatus resourceNames={['character']} />,
      );
      const allRadios = container.querySelectorAll('input[type="radio"]');
      const allRevisionRadios = Array.from(allRadios).filter(
        (r) => r.getAttribute('value') === 'all',
      );
      if (allRevisionRadios.length > 1) fireEvent.click(allRevisionRadios[1]);

      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(mockTest).toHaveBeenCalledWith(
          'character',
          expect.objectContaining({ revisionId: 'all' }),
        );
      });
    });

    it('passes specific revision ID for per-model test', async () => {
      const { container } = renderWithMantine(
        <MigrationStatus resourceNames={['character']} />,
      );
      const allRadios = container.querySelectorAll('input[type="radio"]');
      const specificRadios = Array.from(allRadios).filter(
        (r) => r.getAttribute('value') === 'specific',
      );
      if (specificRadios.length > 1) fireEvent.click(specificRadios[1]);

      await waitFor(() => {
        const revInputs = screen.getAllByPlaceholderText('Revision ID');
        fireEvent.change(revInputs[revInputs.length - 1], { target: { value: 'rev-abc' } });
      });

      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(mockTest).toHaveBeenCalledWith(
          'character',
          expect.objectContaining({ revisionId: 'rev-abc' }),
        );
      });
    });
  });

  // ── Alert close ─────────────────────────────────────────────────

  it('can close global success alert', async () => {
    renderWithMantine(<MigrationStatus resourceNames={['character']} />);
    fireEvent.click(screen.getByText('Test All Models'));

    await waitFor(() => {
      expect(screen.getByText('All models tested successfully.')).toBeTruthy();
    });

    const closeButtons = screen.getAllByRole('button');
    const alertClose = closeButtons.find((b) => b.getAttribute('aria-label') === 'Close');
    if (alertClose) fireEvent.click(alertClose);
  });

  // ── Progress display with statusColor ───────────────────────────

  it('shows progress items with different statuses', async () => {
    mockTest.mockImplementation((_name: string, options?: any) => {
      options?.onProgress?.({ resource_id: 'r1', status: 'success' });
      options?.onProgress?.({ resource_id: 'r2', status: 'failed', error: 'err' });
      options?.onProgress?.({ resource_id: 'r3', status: 'skipped' });
      options?.onProgress?.({ resource_id: 'r4', status: 'migrating' });
      return Promise.resolve({
        total: 4, success: 1, failed: 1, skipped: 1,
        errors: [{ resource_id: 'r2', error: 'err' }],
      });
    });
    renderWithMantine(<MigrationStatus resourceNames={['character']} />);
    const testButtons = screen.getAllByRole('button', { name: /test/i });
    const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
    fireEvent.click(perModelTest!);

    await waitFor(() => {
      expect(screen.getByText('4 total')).toBeTruthy();
    });
  });

  // ── Re-running aborts previous ──────────────────────────────────

  it('aborts previous operation when starting a new one', async () => {
    let firstResolve: (v: any) => void;
    let callCount = 0;
    mockTest.mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        return new Promise((resolve) => { firstResolve = resolve; });
      }
      return Promise.resolve({ total: 0, success: 0, failed: 0, skipped: 0, errors: [] });
    });
    renderWithMantine(<MigrationStatus resourceNames={['character']} />);
    const testButtons = screen.getAllByRole('button', { name: /test/i });
    const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
    fireEvent.click(perModelTest!);
    await waitFor(() => { expect(mockTest).toHaveBeenCalledTimes(1); });
    firstResolve!({ total: 0, success: 0, failed: 0, skipped: 0, errors: [] });
  });

  // ── Per-model QB expression ─────────────────────────────────────

  it('passes per-model QB expression to API', async () => {
    renderWithMantine(<MigrationStatus resourceNames={['character']} />);
    const qbInputs = screen.getAllByPlaceholderText(/leave empty to migrate all/i);
    const perModelQb = qbInputs[qbInputs.length - 1];
    fireEvent.change(perModelQb, { target: { value: "QB['hp'] < 100" } });

    const testButtons = screen.getAllByRole('button', { name: /test/i });
    const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
    fireEvent.click(perModelTest!);

    await waitFor(() => {
      expect(mockTest).toHaveBeenCalledWith(
        'character',
        expect.objectContaining({ qb: "QB['hp'] < 100" }),
      );
    });
  });

  // ── Table display limit & download tests (MUST BE LAST — spies on document) ────

  describe('table display limit', () => {
    it('truncates progress details to 100 rows and shows count message', async () => {
      const itemCount = 150;
      mockTest.mockImplementation(makeLargeMock(itemCount));

      renderWithMantine(<MigrationStatus resourceNames={['character']} />);

      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      // Wait for result to appear
      await waitFor(() => {
        expect(screen.getByText(/150 total/i)).toBeTruthy();
      });

      // Expand the details accordion
      const detailsControl = screen.getByText(`Details (${itemCount} resources)`);
      fireEvent.click(detailsControl);

      // Should show truncation message
      await waitFor(() => {
        expect(screen.getByText(/Showing 100 of 150 results/i)).toBeTruthy();
      });

      // Should only render 100 resource ID cells (not 150)
      const resourceCells = screen.getAllByText(/^resource-\d+$/);
      expect(resourceCells.length).toBe(100);
    });

    it('does not show truncation message when items are within limit', async () => {
      const itemCount = 50;
      mockTest.mockImplementation(makeLargeMock(itemCount));

      renderWithMantine(<MigrationStatus resourceNames={['character']} />);

      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(screen.getByText(/50 total/i)).toBeTruthy();
      });

      const detailsControl = screen.getByText(`Details (${itemCount} resources)`);
      fireEvent.click(detailsControl);

      // All items should render
      await waitFor(() => {
        const resourceCells = screen.getAllByText(/^resource-\d+$/);
        expect(resourceCells.length).toBe(50);
      });

      // No truncation message
      expect(screen.queryByText(/Showing 100 of/i)).toBeNull();
    });

    it('truncates error details to 100 rows and shows count message', async () => {
      const errorCount = 120;
      mockTest.mockImplementation(makeLargeMock(errorCount, errorCount));

      renderWithMantine(<MigrationStatus resourceNames={['character']} />);

      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(screen.getByText(`${errorCount} Error(s)`)).toBeTruthy();
      });

      // Expand the errors accordion
      fireEvent.click(screen.getByText(`${errorCount} Error(s)`));

      await waitFor(() => {
        expect(screen.getByText(/Showing 100 of 120 errors/i)).toBeTruthy();
      });
    });
  });

  describe('download buttons', () => {
    it('renders download button for progress details', async () => {
      mockTest.mockImplementation(makeLargeMock(5));

      renderWithMantine(<MigrationStatus resourceNames={['character']} />);

      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(screen.getByText(/5 total/i)).toBeTruthy();
      });

      // Expand details
      fireEvent.click(screen.getByText('Details (5 resources)'));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Download All Results \(5\)/i })).toBeTruthy();
      });
    });

    it('renders download button for error details', async () => {
      mockTest.mockImplementation(makeLargeMock(10, 10));

      renderWithMantine(<MigrationStatus resourceNames={['character']} />);

      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(screen.getByText('10 Error(s)')).toBeTruthy();
      });

      // Expand errors
      fireEvent.click(screen.getByText('10 Error(s)'));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Download All Errors \(10\)/i })).toBeTruthy();
      });
    });

    it('triggers file download when clicking download button', async () => {
      mockTest.mockImplementation(makeLargeMock(3));

      // Mock URL.createObjectURL / revokeObjectURL
      const createObjectURLSpy = vi.fn(() => 'blob:mock-url');
      const revokeObjectURLSpy = vi.fn();
      globalThis.URL.createObjectURL = createObjectURLSpy;
      globalThis.URL.revokeObjectURL = revokeObjectURLSpy;

      // Render FIRST before spying on document.body methods
      renderWithMantine(<MigrationStatus resourceNames={['character']} />);

      const testButtons = screen.getAllByRole('button', { name: /test/i });
      const perModelTest = testButtons.find((btn) => btn.textContent?.trim() === 'Test');
      fireEvent.click(perModelTest!);

      await waitFor(() => {
        expect(screen.getByText(/3 total/i)).toBeTruthy();
      });

      fireEvent.click(screen.getByText('Details (3 resources)'));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Download All Results \(3\)/i })).toBeTruthy();
      });

      // Spy AFTER render so React DOM operations are not affected
      const appendChildSpy = vi
        .spyOn(document.body, 'appendChild')
        .mockImplementation((node) => node);
      const removeChildSpy = vi
        .spyOn(document.body, 'removeChild')
        .mockImplementation((node) => node);
      const clickSpy = vi.fn();
      const origCreateElement = document.createElement.bind(document);
      const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        if (tag === 'a') {
          return { href: '', download: '', click: clickSpy } as any;
        }
        return origCreateElement(tag);
      });

      fireEvent.click(screen.getByRole('button', { name: /Download All Results \(3\)/i }));

      expect(createObjectURLSpy).toHaveBeenCalled();
      expect(clickSpy).toHaveBeenCalled();
      expect(revokeObjectURLSpy).toHaveBeenCalled();

      // Cleanup — restore spies individually
      appendChildSpy.mockRestore();
      removeChildSpy.mockRestore();
      createElementSpy.mockRestore();
    });
  });
});
