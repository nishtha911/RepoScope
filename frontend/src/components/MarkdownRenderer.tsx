import React, { useState } from 'react';
import type { CitationEvidence } from '../types/chat';
import CitationPill from './CitationPill';
import './MarkdownRenderer.css';

interface Props {
  content: string;
  citations?: Record<string, CitationEvidence>;
  onSelectSymbol?: (symbolId: number) => void;
}

interface CodeBlockProps {
  language: string;
  code: string;
}

const CodeBlock: React.FC<CodeBlockProps> = ({ language, code }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    void navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="markdown-codeblock">
      <div className="markdown-codeblock__header">
        <span className="markdown-codeblock__lang">
          {(language || 'TEXT').toUpperCase()}
        </span>
        <button
          type="button"
          className="markdown-codeblock__copy-btn"
          onClick={handleCopy}
          aria-label="Copy code block"
        >
          {copied ? 'COPIED!' : 'COPY CODE'}
        </button>
      </div>
      <pre className="markdown-codeblock__pre">
        <code>{code}</code>
      </pre>
    </div>
  );
};

export const MarkdownRenderer: React.FC<Props> = ({
  content,
  citations = {},
  onSelectSymbol,
}) => {
  // Render inline formatting: citations, [GAP], bold, italics, code, links
  const renderInline = (text: string, keyPrefix: string): React.ReactNode[] => {
    // Regex matches citation [E1..n], [GAP], inline `code`, **bold**, *italic*
    const tokenRegex = /(\[E\d+\]|\[GAP\]|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
    const parts = text.split(tokenRegex);

    return parts.map((part, index) => {
      const key = `${keyPrefix}-${index}`;
      if (!part) return null;

      // Check Citation [E1..n]
      const citationMatch = part.match(/^\[(E\d+)\]$/);
      if (citationMatch) {
        const evidenceId = citationMatch[1];
        const evidence = citations[evidenceId];
        return (
          <CitationPill
            key={key}
            evidenceId={evidenceId}
            evidence={evidence}
            onSelectSymbol={onSelectSymbol}
          />
        );
      }

      // Check [GAP]
      if (part === '[GAP]') {
        return (
          <span key={key} className="markdown-gap-badge" title="Identified coverage or knowledge gap">
            [GAP]
          </span>
        );
      }

      // Inline code `code`
      if (part.startsWith('`') && part.endsWith('`') && part.length >= 2) {
        return <code key={key}>{part.slice(1, -1)}</code>;
      }

      // Bold **bold**
      if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
        return <strong key={key}>{part.slice(2, -2)}</strong>;
      }

      // Italic *italic*
      if (part.startsWith('*') && part.endsWith('*') && part.length >= 2) {
        return <em key={key}>{part.slice(1, -1)}</em>;
      }

      // Link [text](url)
      const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (linkMatch) {
        return (
          <a
            key={key}
            href={linkMatch[2]}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#2563eb', textDecoration: 'underline', fontWeight: 600 }}
          >
            {linkMatch[1]}
          </a>
        );
      }

      return <React.Fragment key={key}>{part}</React.Fragment>;
    });
  };

  // Split into blocks: code blocks and standard text blocks
  const blocks: React.ReactNode[] = [];
  const lines = content.split('\n');
  let inCodeBlock = false;
  let codeBlockLang = '';
  let codeBlockLines: string[] = [];
  let textLines: string[] = [];
  let blockIdx = 0;

  const flushTextLines = () => {
    if (textLines.length === 0) return;
    const current = [...textLines];
    textLines = [];

    let i = 0;
    while (i < current.length) {
      const line = current[i];

      // Empty line
      if (!line.trim()) {
        i++;
        continue;
      }

      // Headings
      if (line.startsWith('### ')) {
        blocks.push(
          <h3 key={`h3-${blockIdx++}`}>
            {renderInline(line.slice(4), `h3-${blockIdx}`)}
          </h3>,
        );
        i++;
        continue;
      }
      if (line.startsWith('## ')) {
        blocks.push(
          <h2 key={`h2-${blockIdx++}`}>
            {renderInline(line.slice(3), `h2-${blockIdx}`)}
          </h2>,
        );
        i++;
        continue;
      }
      if (line.startsWith('# ')) {
        blocks.push(
          <h1 key={`h1-${blockIdx++}`}>
            {renderInline(line.slice(2), `h1-${blockIdx}`)}
          </h1>,
        );
        i++;
        continue;
      }

      // Blockquotes
      if (line.startsWith('> ')) {
        const quoteLines: string[] = [];
        while (i < current.length && current[i].startsWith('> ')) {
          quoteLines.push(current[i].slice(2));
          i++;
        }
        blocks.push(
          <blockquote key={`quote-${blockIdx++}`}>
            {quoteLines.map((ql, qIdx) => (
              <p key={`qp-${qIdx}`}>{renderInline(ql, `qp-${blockIdx}-${qIdx}`)}</p>
            ))}
          </blockquote>,
        );
        continue;
      }

      // Unordered lists (- or *)
      if (/^[-*]\s+/.test(line)) {
        const listItems: string[] = [];
        while (i < current.length && /^[-*]\s+/.test(current[i])) {
          listItems.push(current[i].replace(/^[-*]\s+/, ''));
          i++;
        }
        blocks.push(
          <ul key={`ul-${blockIdx++}`}>
            {listItems.map((item, lIdx) => (
              <li key={`li-${lIdx}`}>{renderInline(item, `ul-${blockIdx}-${lIdx}`)}</li>
            ))}
          </ul>,
        );
        continue;
      }

      // Ordered lists (1., 2., etc.)
      if (/^\d+\.\s+/.test(line)) {
        const listItems: string[] = [];
        while (i < current.length && /^\d+\.\s+/.test(current[i])) {
          listItems.push(current[i].replace(/^\d+\.\s+/, ''));
          i++;
        }
        blocks.push(
          <ol key={`ol-${blockIdx++}`}>
            {listItems.map((item, lIdx) => (
              <li key={`oli-${lIdx}`}>{renderInline(item, `ol-${blockIdx}-${lIdx}`)}</li>
            ))}
          </ol>,
        );
        continue;
      }

      // Paragraph - gather consecutive non-empty lines that aren't other elements
      const paragraphLines: string[] = [];
      while (
        i < current.length &&
        current[i].trim() &&
        !current[i].startsWith('#') &&
        !current[i].startsWith('> ') &&
        !/^[-*]\s+/.test(current[i]) &&
        !/^\d+\.\s+/.test(current[i])
      ) {
        paragraphLines.push(current[i]);
        i++;
      }

      blocks.push(
        <p key={`p-${blockIdx++}`}>
          {paragraphLines.map((pLine, pIdx) => (
            <React.Fragment key={`pline-${pIdx}`}>
              {pIdx > 0 && ' '}
              {renderInline(pLine, `p-${blockIdx}-${pIdx}`)}
            </React.Fragment>
          ))}
        </p>,
      );
    }
  };

  for (const line of lines) {
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        // End of code block
        blocks.push(
          <CodeBlock
            key={`code-${blockIdx++}`}
            language={codeBlockLang}
            code={codeBlockLines.join('\n')}
          />,
        );
        inCodeBlock = false;
        codeBlockLines = [];
        codeBlockLang = '';
      } else {
        // Start of code block
        flushTextLines();
        inCodeBlock = true;
        codeBlockLang = line.slice(3).trim();
      }
    } else if (inCodeBlock) {
      codeBlockLines.push(line);
    } else {
      textLines.push(line);
    }
  }

  if (inCodeBlock) {
    // Unclosed code block (e.g. streaming in progress)
    blocks.push(
      <CodeBlock
        key={`code-open-${blockIdx++}`}
        language={codeBlockLang}
        code={codeBlockLines.join('\n')}
      />,
    );
  } else {
    flushTextLines();
  }

  return <div className="markdown-body">{blocks}</div>;
};

export default MarkdownRenderer;
