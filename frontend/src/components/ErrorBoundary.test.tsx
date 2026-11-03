// @vitest-environment jsdom

import {
  cleanup,
  render,
  screen,
} from '@testing-library/react';

import {
  afterEach,
  describe,
  expect,
  it,
} from 'vitest';

import ErrorBoundary from './ErrorBoundary';

interface PreviewChildProps {
  shouldThrow: boolean;
}

function PreviewChild({
  shouldThrow,
}: PreviewChildProps) {
  if (shouldThrow) {
    throw new Error('Intentional preview rendering failure');
  }

  return <p>Preview rendered successfully</p>;
}

afterEach(cleanup);

describe('ErrorBoundary', () => {
  it('renders its children when they do not throw', () => {
    render(
      <ErrorBoundary>
        <PreviewChild shouldThrow={false} />
      </ErrorBoundary>,
    );

    expect(
      screen.getByText('Preview rendered successfully'),
    ).toBeTruthy();

    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows the fallback when a child throws during rendering', () => {
    render(
      <ErrorBoundary>
        <PreviewChild shouldThrow />
      </ErrorBoundary>,
      {
        onCaughtError: () => {
          // This rendering error is intentional for this test.
        },
      },
    );

    expect(screen.getByRole('alert')).toBeTruthy();

    expect(
      screen.getByRole('heading', {
        name: 'Unable to display the code preview',
      }),
    ).toBeTruthy();

    expect(
      screen.queryByText('Preview rendered successfully'),
    ).toBeNull();
  });

  it('recovers when the boundary is remounted with a new key', () => {
    const { rerender } = render(
      <ErrorBoundary key="failed-preview">
        <PreviewChild shouldThrow />
      </ErrorBoundary>,
      {
        onCaughtError: () => {
          // This rendering error is intentional for this test.
        },
      },
    );

    expect(screen.getByRole('alert')).toBeTruthy();

    rerender(
      <ErrorBoundary key="fresh-preview">
        <PreviewChild shouldThrow={false} />
      </ErrorBoundary>,
    );

    expect(
      screen.getByText('Preview rendered successfully'),
    ).toBeTruthy();

    expect(screen.queryByRole('alert')).toBeNull();
  });
});