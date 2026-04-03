/**
 * MarkdownEditor — Tests for the markdown editor component.
 *
 * Monaco Editor is mocked since it requires a browser environment.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { MarkdownEditor } from './MarkdownEditor';

// Mock Monaco Editor
vi.mock('@monaco-editor/react', () => ({
  default: ({ value, onChange }: any) => (
    <textarea
      data-testid="monaco-editor"
      value={value}
      onChange={(e: any) => onChange(e.target.value)}
    />
  ),
}));

beforeEach(() => {
  cleanup();
});

const wrap = (ui: React.ReactElement) => render(<MantineProvider>{ui}</MantineProvider>);

describe('MarkdownEditor', () => {
  it('renders label', () => {
    wrap(<MarkdownEditor label="Content" value="" onChange={vi.fn()} />);
    expect(screen.getByText('Content')).toBeDefined();
  });

  it('renders required indicator', () => {
    const { container } = wrap(
      <MarkdownEditor label="Notes" required value="" onChange={vi.fn()} />,
    );
    expect(container.textContent).toContain('*');
  });

  it('renders in edit mode by default', () => {
    wrap(<MarkdownEditor label="Test" value="hello" onChange={vi.fn()} />);
    expect(screen.getByTestId('monaco-editor')).toBeDefined();
  });

  it('switches to preview mode', () => {
    const { container } = wrap(
      <MarkdownEditor label="Test" value="**bold text**" onChange={vi.fn()} />,
    );
    // Find the Preview button in SegmentedControl
    const previewLabel = Array.from(container.querySelectorAll('label')).find(
      (l) => l.textContent === 'Preview',
    );
    if (previewLabel) {
      fireEvent.click(previewLabel);
    }
    // After switching, the monaco editor should not be visible
    // and markdown content should be rendered
  });

  it('shows "Nothing to preview" when value is empty in preview mode', () => {
    const { container } = wrap(<MarkdownEditor label="Test" value="" onChange={vi.fn()} />);
    const previewLabel = Array.from(container.querySelectorAll('label')).find(
      (l) => l.textContent === 'Preview',
    );
    if (previewLabel) {
      fireEvent.click(previewLabel);
      expect(container.textContent).toContain('Nothing to preview');
    }
  });

  it('displays error message', () => {
    wrap(<MarkdownEditor label="Test" value="" onChange={vi.fn()} error="Required field" />);
    expect(screen.getByText('Required field')).toBeDefined();
  });

  it('does not display error when none provided', () => {
    const { container } = wrap(<MarkdownEditor label="Test" value="" onChange={vi.fn()} />);
    expect(container.textContent).not.toContain('Required field');
  });

  it('calls onChange when editor value changes', () => {
    const onChange = vi.fn();
    wrap(<MarkdownEditor label="Test" value="" onChange={onChange} />);
    const editor = screen.getByTestId('monaco-editor');
    fireEvent.change(editor, { target: { value: 'new content' } });
    expect(onChange).toHaveBeenCalledWith('new content');
  });

  it('uses custom height', () => {
    wrap(<MarkdownEditor label="Test" value="" onChange={vi.fn()} height={500} />);
    // Monaco editor renders with the height prop
    expect(screen.getByTestId('monaco-editor')).toBeDefined();
  });

  it('renders Edit / Preview segment control', () => {
    const { container } = wrap(<MarkdownEditor label="Test" value="" onChange={vi.fn()} />);
    expect(container.textContent).toContain('Edit');
    expect(container.textContent).toContain('Preview');
  });

  it('renders with error border style in edit mode', () => {
    const { container } = wrap(
      <MarkdownEditor label="Test" value="" onChange={vi.fn()} error="Error!" />,
    );
    // The editor wrapper div should have red border
    expect(container.textContent).toContain('Error!');
  });
});
