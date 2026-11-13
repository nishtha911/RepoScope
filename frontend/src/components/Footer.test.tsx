import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import Footer from './Footer';

describe('Footer', () => {
  it('renders brand name and copyright', () => {
    render(<Footer offlinePreview activeTab="OVERVIEW" onTabChange={vi.fn()} />);

    expect(screen.getByText('REPOSCOPE')).toBeInTheDocument();
    expect(screen.getByText(/© 2026/)).toBeInTheDocument();
  });

  it('shows Offline Preview status when offlinePreview=true', () => {
    render(<Footer offlinePreview activeTab="OVERVIEW" onTabChange={vi.fn()} />);

    expect(screen.getByText('Offline Preview')).toBeInTheDocument();
  });

  it('shows connected status with API version when online', () => {
    render(
      <Footer
        offlinePreview={false}
        activeTab="OVERVIEW"
        onTabChange={vi.fn()}
        apiHealth={{ status: 'ok', v: '1.2' }}
        isHealthError={false}
      />,
    );

    expect(screen.getByText(/API v1\.2 · Connected/i)).toBeInTheDocument();
  });

  it('shows server unreachable status on health error', () => {
    render(
      <Footer
        offlinePreview={false}
        activeTab="OVERVIEW"
        onTabChange={vi.fn()}
        isHealthError
      />,
    );

    expect(screen.getByText('Server Unreachable')).toBeInTheDocument();
  });

  it('renders footer as a contentinfo landmark', () => {
    render(<Footer offlinePreview activeTab="OVERVIEW" onTabChange={vi.fn()} />);

    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
  });
});
