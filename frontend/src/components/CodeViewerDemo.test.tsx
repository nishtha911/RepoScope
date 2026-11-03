// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
} from '@testing-library/react';

import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';

import CodeViewerDemo from './CodeViewerDemo';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('CodeViewerDemo', () => {
  it('shows fixture code without making a fetch request', () => {
    const fetchMock = vi.fn();

    vi.stubGlobal('fetch', fetchMock);

    render(<CodeViewerDemo />);

    expect(
      screen.getByRole('heading', {
        name: 'DAY 5 — OFFLINE CODE VIEWER DEMO',
      }),
    ).toBeTruthy();

    expect(
      screen.getByRole('region', {
        name: 'Code preview',
      }),
    ).toBeTruthy();

    expect(
      screen.getByText(/FIXTURE PREVIEW/i),
    ).toBeTruthy();

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('switches to the empty state and restores the fixture', () => {
    render(<CodeViewerDemo />);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Show empty state',
      }),
    );

    expect(
      screen.getByRole('heading', {
        name: 'No source selected',
      }),
    ).toBeTruthy();

    expect(
      screen.queryByRole('region', {
        name: 'Code preview',
      }),
    ).toBeNull();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Show fixture code',
      }),
    );

    expect(
      screen.getByRole('region', {
        name: 'Code preview',
      }),
    ).toBeTruthy();

    expect(
      screen.queryByRole('heading', {
        name: 'No source selected',
      }),
    ).toBeNull();
  });
});