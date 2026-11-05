import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import MarkdownRenderer from './MarkdownRenderer';
import type { CitationEvidence } from '../types/chat';

const mockCitations: Record<string, CitationEvidence> = {
  E1: {
    evidence_id: 'E1',
    symbol_id: 101,
    name: 'SymbolResolver.resolve_calls',
    file_path: 'backend/reposcope/parsing/resolver.py',
    start_line: 45,
    end_line: 68,
    snippet: 'def resolve_calls(self, ast_tree): return []',
    kind: 'function',
  },
  E2: {
    evidence_id: 'E2',
    symbol_id: 301,
    name: 'search_repo',
    file_path: 'backend/reposcope/api/repos.py',
    start_line: 112,
    end_line: 140,
    snippet: '@router.post("/repos/{id}/search")',
    kind: 'endpoint',
  },
};

describe('MarkdownRenderer', () => {
  it('renders headings and paragraphs', () => {
    const markdown = `# Main Title\n\n## Sub Title\n\n### Section Title\n\nThis is a paragraph with **bold** and *italic* text.`;
    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Main Title');
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Sub Title');
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Section Title');
    expect(screen.getByText(/This is a paragraph with/i)).toBeInTheDocument();
    expect(screen.getByText('bold')).toBeInTheDocument();
  });

  it('renders inline citation pills for [E1] and [E2]', () => {
    const markdown = `The AST scope is resolved in [E1] and queried via search endpoint [E2].`;
    render(<MarkdownRenderer content={markdown} citations={mockCitations} />);

    expect(screen.getByRole('button', { name: /Citation \[E1\]/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Citation \[E2\]/i })).toBeInTheDocument();
  });

  it('renders [GAP] badge for unresolved claims', () => {
    const markdown = `Authentication coverage is currently [GAP] in this module.`;
    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByText('[GAP]')).toBeInTheDocument();
  });

  it('renders code blocks with language badge and copy action', () => {
    const markdown = "```python\ndef test_algo():\n    assert True\n```";
    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByText('PYTHON')).toBeInTheDocument();
    expect(screen.getByText('COPY CODE')).toBeInTheDocument();
    expect(screen.getByText(/def test_algo/)).toBeInTheDocument();
  });

  it('renders lists and blockquotes', () => {
    const markdown = `> Important architectural notice\n\n- Item Alpha\n- Item Beta\n\n1. First Step\n2. Second Step`;
    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByText('Important architectural notice')).toBeInTheDocument();
    expect(screen.getByText('Item Alpha')).toBeInTheDocument();
    expect(screen.getByText('Item Beta')).toBeInTheDocument();
    expect(screen.getByText('First Step')).toBeInTheDocument();
    expect(screen.getByText('Second Step')).toBeInTheDocument();
  });
});
