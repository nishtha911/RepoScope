import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Footer from './Footer';

describe('Footer', () => {
  it('renders brand, philosophy, and architectural tagline', () => {
    render(
      <Footer
        offlinePreview
        activeTab="OVERVIEW"
        onTabChange={vi.fn()}
      />,
    );

    expect(screen.getByText('REPOSCOPE')).toBeInTheDocument();
    expect(screen.getByText(/FORM FOLLOWS FUNCTION · ARCHITECTURE AS CODE/i)).toBeInTheDocument();
    expect(screen.getByText('INTELLIGENCE PIPELINES')).toBeInTheDocument();
    expect(screen.getByText('WORKSPACE VIEWS')).toBeInTheDocument();
    expect(screen.getByText('SYSTEM TELEMETRY')).toBeInTheDocument();
  });

  it('renders pipeline stages and statuses', () => {
    render(
      <Footer
        offlinePreview
        activeTab="OVERVIEW"
        onTabChange={vi.fn()}
      />,
    );

    expect(screen.getByText('PASS 1: AST SCOPE MAP')).toBeInTheDocument();
    expect(screen.getByText('PASS 2: REF RESOLVER')).toBeInTheDocument();
    expect(screen.getByText('RETRIEVAL: RRF FUSION k=60')).toBeInTheDocument();
  });

  it('triggers onTabChange when clicking navigation view button', () => {
    const onTabChange = vi.fn();
    render(
      <Footer
        offlinePreview
        activeTab="OVERVIEW"
        onTabChange={onTabChange}
      />,
    );

    const chatTabBtn = screen.getByRole('button', { name: /04 \/\/ CODEBASE CHAT & RAG/i });
    fireEvent.click(chatTabBtn);

    expect(onTabChange).toHaveBeenCalledWith('RAG');
  });

  it('displays offline fixture status beacon in preview mode', () => {
    render(
      <Footer
        offlinePreview
        activeTab="OVERVIEW"
        onTabChange={vi.fn()}
      />,
    );

    expect(screen.getByText(/OFFLINE FIXTURE PREVIEW · ZERO NETWORK/i)).toBeInTheDocument();
  });

  it('displays online API version when connected', () => {
    render(
      <Footer
        offlinePreview={false}
        activeTab="OVERVIEW"
        onTabChange={vi.fn()}
        apiHealth={{ status: 'ok', v: '1.2' }}
        isHealthError={false}
      />,
    );

    expect(screen.getByText(/ONLINE · FASTAPI GATEWAY v1.2/i)).toBeInTheDocument();
  });
});
