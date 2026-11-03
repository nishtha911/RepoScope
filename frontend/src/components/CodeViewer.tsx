import { Highlight, themes } from 'prism-react-renderer';
import EmptyState from './EmptyState';
import './CodeViewer.css';

interface Props {
  code?: string | null;
  filePath?: string;
  language?: string;
  startLine?: number;
  highlightStart?: number;
  highlightEnd?: number;
  isFixture?: boolean;
}

export default function CodeViewer({
  code,
  filePath = '',
  language = 'python',
  startLine = 1,
  highlightStart,
  highlightEnd,
  isFixture = false,
}: Props) {
  if (code == null || code.length === 0) {
    return <EmptyState />;
  }

  const normalizedCode = code.replace(/\r\n?/g, '\n');
  const pathParts = filePath.split(/[\\/]/).filter(Boolean);

  const firstLine =
    Number.isSafeInteger(startLine) && startLine > 0 ? startLine : 1;

  const hasHighlight =
    highlightStart !== undefined &&
    highlightEnd !== undefined &&
    Number.isSafeInteger(highlightStart) &&
    Number.isSafeInteger(highlightEnd) &&
    highlightStart > 0 &&
    highlightEnd >= highlightStart;

  return (
    <section className="code-viewer" aria-label="Code preview">
      <header className="code-viewer__header">
        <nav aria-label="Source file breadcrumb">
          <ol className="code-viewer__breadcrumbs">
            {pathParts.length > 0 ? (
              pathParts.map((part, index) => (
                <li key={`${index}-${part}`}>
                  {index > 0 && (
                    <span
                      className="code-viewer__separator"
                      aria-hidden="true"
                    >
                      /
                    </span>
                  )}

                  <span
                    aria-current={
                      index === pathParts.length - 1 ? 'page' : undefined
                    }
                  >
                    {part}
                  </span>
                </li>
              ))
            ) : (
              <li>Untitled source</li>
            )}
          </ol>
        </nav>

        <span className="code-viewer__language">{language}</span>
      </header>

      {isFixture && (
        <p className="code-viewer__notice">
          FIXTURE PREVIEW — synthetic demonstration code, not the selected
          symbol&apos;s repository source.
        </p>
      )}

      <Highlight
        theme={themes.vsDark}
        code={normalizedCode}
        language={language}
      >
        {({
          className,
          style,
          tokens,
          getLineProps,
          getTokenProps,
        }) => (
          <pre
            className={`${className} code-viewer__pre`}
            style={style}
            tabIndex={0}
            aria-label={`Source code for ${filePath || 'untitled source'}`}
          >
            <code className="code-viewer__code">
              {tokens.map((line, index) => {
                const lineNumber = firstLine + index;

                const isHighlighted =
                  hasHighlight &&
                  highlightStart !== undefined &&
                  highlightEnd !== undefined &&
                  lineNumber >= highlightStart &&
                  lineNumber <= highlightEnd;

                const lineProps = getLineProps({ line });

                return (
                  <span
                    {...lineProps}
                    key={lineNumber}
                    className={[
                      lineProps.className,
                      'code-viewer__line',
                      isHighlighted
                        ? 'code-viewer__line--highlighted'
                        : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    data-line-number={lineNumber}
                    data-highlighted={isHighlighted ? 'true' : 'false'}
                  >
                    <span
                      className="code-viewer__line-number"
                      aria-hidden="true"
                    >
                      {lineNumber}
                    </span>

                    <span className="code-viewer__line-content">
                      {line.map((token, tokenIndex) => (
                        <span
                          {...getTokenProps({ token })}
                          key={tokenIndex}
                        />
                      ))}
                    </span>

                    {'\n'}
                  </span>
                );
              })}
            </code>
          </pre>
        )}
      </Highlight>
    </section>
  );
}