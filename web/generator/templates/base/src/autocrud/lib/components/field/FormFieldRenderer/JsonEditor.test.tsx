/**
 * JsonEditor — Unit tests.
 *
 * Monaco Editor itself cannot render in happy-dom, so we test:
 * 1. Component mounts without crashing (smoke test)
 * 2. The toJsonString normalisation utility (exported for testing)
 *
 * Integration tests with actual Monaco rendering should use a real browser.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { JsonEditor } from './JsonEditor';

/** Monaco Editor doesn't work in happy-dom — mock it */
vi.mock('@monaco-editor/react', () => ({
  default: ({ value, onChange, height }: any) => (
    <textarea
      data-testid="mock-monaco"
      value={value ?? ''}
      onChange={(e) => onChange?.(e.target.value)}
      style={{ height }}
    />
  ),
}));

function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

/** Helper: get the last mock-monaco element (React re-renders may create multiples) */
function getMonaco(container: ReturnType<typeof render>) {
  const all = container.getAllByTestId('mock-monaco');
  return all[all.length - 1] as HTMLTextAreaElement;
}

describe('JsonEditor', () => {
  it('renders label and editor', () => {
    const result = renderWithMantine(<JsonEditor label="Event X8" value="" onChange={() => {}} />);
    expect(screen.getByText('Event X8')).toBeDefined();
    expect(getMonaco(result)).toBeDefined();
  });

  it('shows required asterisk when required=true', () => {
    renderWithMantine(<JsonEditor label="Data" required value="" onChange={() => {}} />);
    expect(screen.getByText('*')).toBeDefined();
  });

  it('shows error message when error is provided', () => {
    renderWithMantine(
      <JsonEditor label="Data" value="" onChange={() => {}} error="Invalid JSON" />,
    );
    expect(screen.getByText('Invalid JSON')).toBeDefined();
  });

  it('normalises object value to pretty-printed JSON string', () => {
    const result = renderWithMantine(
      <JsonEditor label="Data" value={{ foo: 'bar', nested: [1, 2] }} onChange={() => {}} />,
    );
    const textarea = getMonaco(result);
    // Should be pretty-printed
    expect(textarea.value).toContain('"foo": "bar"');
    expect(textarea.value).toContain('\n');
  });

  it('normalises string JSON value to pretty-printed format', () => {
    const result = renderWithMantine(
      <JsonEditor label="Data" value='{"a":1}' onChange={() => {}} />,
    );
    const textarea = getMonaco(result);
    expect(textarea.value).toBe('{\n  "a": 1\n}');
  });

  it('passes through non-JSON string as-is', () => {
    const result = renderWithMantine(
      <JsonEditor label="Data" value="not json" onChange={() => {}} />,
    );
    const textarea = getMonaco(result);
    expect(textarea.value).toBe('not json');
  });

  it('handles null/undefined value gracefully', () => {
    const result = renderWithMantine(<JsonEditor label="Data" value={null} onChange={() => {}} />);
    const textarea = getMonaco(result);
    expect(textarea.value).toBe('');
  });

  it('calls onChange when editor content changes', () => {
    const handleChange = vi.fn();
    const result = renderWithMantine(<JsonEditor label="Data" value="" onChange={handleChange} />);
    const textarea = getMonaco(result);
    // Use fireEvent.change so React synthetic event fires the mock's onChange
    fireEvent.change(textarea, { target: { value: '{"new": true}' } });
    expect(handleChange).toHaveBeenCalledWith('{"new": true}');
  });

  it('toggles expand/collapse when ActionIcon is clicked', () => {
    const { container } = renderWithMantine(
      <JsonEditor label="Data" value="{}" onChange={() => {}} height={200} />,
    );
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBeGreaterThanOrEqual(1);
    // Click expand
    fireEvent.click(buttons[0]);
    // Click collapse
    fireEvent.click(buttons[0]);
  });

  it('returns empty string for undefined value', () => {
    const result = renderWithMantine(
      <JsonEditor label="Data" value={undefined} onChange={() => {}} />,
    );
    const textarea = getMonaco(result);
    expect(textarea.value).toBe('');
  });

  it('returns empty string for empty string value', () => {
    const result = renderWithMantine(<JsonEditor label="Data" value="" onChange={() => {}} />);
    const textarea = getMonaco(result);
    expect(textarea.value).toBe('');
  });

  it('uses custom height prop', () => {
    const result = renderWithMantine(
      <JsonEditor label="Data" value="" onChange={() => {}} height={400} />,
    );
    const textarea = getMonaco(result);
    // Mock passes height as style; value may include px unit
    expect(textarea.style.height).toMatch(/400/);
  });
});
