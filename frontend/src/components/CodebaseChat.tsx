import React, { useState, useRef, useEffect, useCallback } from 'react';
import type { ChatMessage, CitationEvidence } from '../types/chat';
import {
  initialChatMessages,
  sampleStarterPrompts,
  fixturePromptResponses,
  fixtureEvidence,
} from '../fixtures/chat';
import MarkdownRenderer from './MarkdownRenderer';
import './CodebaseChat.css';

interface Props {
  repoId: number;
  repoName: string;
  apiBase?: string;
  offlinePreview?: boolean;
  onSelectSymbol?: (symbolId: number) => void;
}

function pickFixtureResponse(query: string) {
  const q = query.toLowerCase();
  if (q.includes('resolver') || q.includes('ast') || q.includes('pass')) {
    return fixturePromptResponses.resolver;
  }
  if (q.includes('rrf') || q.includes('search') || q.includes('fusion') || q.includes('hybrid')) {
    return fixturePromptResponses.search;
  }
  if (q.includes('evidence') || q.includes('gap') || q.includes('pack') || q.includes('citation')) {
    return fixturePromptResponses.evidence;
  }
  return fixturePromptResponses.default;
}

export const CodebaseChat: React.FC<Props> = ({
  repoId,
  repoName,
  apiBase = 'http://localhost:8000/api',
  offlinePreview = true,
  onSelectSymbol,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>(initialChatMessages);
  const [inputValue, setInputValue] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [expandedDrawers, setExpandedDrawers] = useState<Record<string, boolean>>({});

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-scroll to bottom of messages container
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Clean up streaming on unmount
  useEffect(() => {
    return () => {
      if (streamIntervalRef.current) {
        clearInterval(streamIntervalRef.current);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const toggleDrawer = (messageId: string) => {
    setExpandedDrawers((prev) => ({
      ...prev,
      [messageId]: !prev[messageId],
    }));
  };

  const handleStopGeneration = useCallback(() => {
    if (streamIntervalRef.current) {
      clearInterval(streamIntervalRef.current);
      streamIntervalRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsGenerating(false);

    setMessages((prev) =>
      prev.map((msg) =>
        msg.isStreaming ? { ...msg, isStreaming: false } : msg,
      ),
    );
  }, []);

  const handleClearChat = useCallback(() => {
    handleStopGeneration();
    setMessages(initialChatMessages);
    setExpandedDrawers({});
  }, [handleStopGeneration]);

  const executeSendMessage = useCallback(
    async (queryText: string) => {
      const trimmed = queryText.trim();
      if (!trimmed || isGenerating) return;

      const now = Date.now();
      const userMessageId = `user-${now}`;
      const assistantMessageId = `asst-${now}`;

      const userMsg: ChatMessage = {
        id: userMessageId,
        role: 'user',
        content: trimmed,
        timestamp: now,
      };

      const initialAssistantMsg: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: now,
        isStreaming: true,
        citations: {},
      };

      setMessages((prev) => [...prev, userMsg, initialAssistantMsg]);
      setInputValue('');
      setIsGenerating(true);

      if (offlinePreview) {
        // Offline preview mode: Realistic simulated token streaming
        const target = pickFixtureResponse(trimmed);
        const fullText = target.content;
        // Split words to stream tokens
        const words = fullText.split(' ');
        let currentWordIndex = 0;
        let accumulatedText = '';

        streamIntervalRef.current = setInterval(() => {
          if (currentWordIndex >= words.length) {
            if (streamIntervalRef.current) {
              clearInterval(streamIntervalRef.current);
              streamIntervalRef.current = null;
            }
            setIsGenerating(false);
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? {
                      ...msg,
                      content: fullText,
                      isStreaming: false,
                      citations: target.citations,
                      latencyMs: target.latencyMs,
                    }
                  : msg,
              ),
            );
          } else {
            // Stream 2 words per tick for high realism
            const nextChunk =
              words.slice(currentWordIndex, currentWordIndex + 2).join(' ') + ' ';
            accumulatedText += nextChunk;
            currentWordIndex += 2;

            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? {
                      ...msg,
                      content: accumulatedText,
                      citations: target.citations,
                    }
                  : msg,
              ),
            );
          }
        }, 40);
      } else {
        // Online mode: Connect to API
        const controller = new AbortController();
        abortControllerRef.current = controller;
        const startTime = performance.now();

        try {
          const response = await fetch(`${apiBase}/repos/${repoId}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: trimmed }),
            signal: controller.signal,
          });

          const elapsed = Math.round(performance.now() - startTime);

          if (!response.ok) {
            throw new Error(
              `API returned status ${response.status}: ${response.statusText}`,
            );
          }

          const data = await response.json();
          const content = data.answer || data.content || 'No response generated.';
          const citations: Record<string, CitationEvidence> =
            data.citations || fixtureEvidence;

          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    content,
                    isStreaming: false,
                    citations,
                    latencyMs: elapsed,
                  }
                : msg,
            ),
          );
        } catch (err: unknown) {
          if (err instanceof DOMException && err.name === 'AbortError') {
            // Cancelled by user
            return;
          }

          const errorMessage =
            err instanceof Error ? err.message : 'Unknown error';
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    content: `⚠️ **Failed to generate answer from server**: ${errorMessage}\n\nYou can switch to **OFFLINE PREVIEW** mode in the header to interact with pre-indexed graph evidence and simulated streaming responses.`,
                    isStreaming: false,
                    error: errorMessage,
                  }
                : msg,
            ),
          );
        } finally {
          setIsGenerating(false);
          abortControllerRef.current = null;
        }
      }
    },
    [apiBase, isGenerating, offlinePreview, repoId],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void executeSendMessage(inputValue);
    }
  };

  return (
    <div className="codebase-chat" role="region" aria-label="Codebase Chat Interface">
      {/* HEADER */}
      <header className="codebase-chat__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <h2 className="codebase-chat__title">CODEBASE CHAT // GRAPHRAG</h2>
          <span
            className={`codebase-chat__badge ${
              offlinePreview ? 'codebase-chat__badge--offline' : ''
            }`}
          >
            {offlinePreview ? 'OFFLINE FIXTURE STREAM' : 'POST /api/repos/{id}/ask'}
          </span>
        </div>

        <div className="codebase-chat__header-actions">
          <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: '#475569' }}>
            REPO: <strong>{repoName}</strong> (#{repoId})
          </span>

          <button
            type="button"
            className="bauhaus-btn-invert"
            style={{ padding: '4px 10px', fontSize: '0.72rem' }}
            onClick={handleClearChat}
            disabled={isGenerating}
            aria-label="Clear chat messages"
          >
            CLEAR CHAT
          </button>
        </div>
      </header>

      {/* MESSAGES LOG CONTAINER */}
      <div
        className="codebase-chat__messages-container"
        role="log"
        aria-live="polite"
        aria-label="Chat messages"
      >
        {messages.map((message) => {
          const isUser = message.role === 'user';
          const citationsList = message.citations
            ? Object.values(message.citations)
            : [];
          const hasCitations = citationsList.length > 0;
          const isDrawerOpen = !!expandedDrawers[message.id];

          return (
            <div
              key={message.id}
              className={`chat-bubble-wrap ${
                isUser ? 'chat-bubble-wrap--user' : 'chat-bubble-wrap--assistant'
              }`}
            >
              {isUser ? (
                // USER MESSAGE BUBBLE
                <div className="chat-bubble chat-bubble--user">
                  <div className="chat-bubble__meta">
                    <span>YOU</span>
                    <span>{new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                  <div>{message.content}</div>
                </div>
              ) : (
                // ASSISTANT MESSAGE BUBBLE
                <div className="chat-bubble chat-bubble--assistant">
                  <div className="chat-bubble__header">
                    <span className="chat-bubble__agent-title">
                      <span>◆</span>
                      <span>REPOSCOPE GRAPHRAG ENGINE</span>
                    </span>

                    <span className="chat-bubble__timestamp">
                      {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  {/* MESSAGE CONTENT WITH MARKDOWN & EXPANDABLE CITATIONS */}
                  <div className="chat-bubble__content">
                    <MarkdownRenderer
                      content={message.content}
                      citations={message.citations}
                      onSelectSymbol={onSelectSymbol}
                    />

                    {message.isStreaming && (
                      <span
                        className="chat-bubble__streaming-cursor"
                        aria-label="Streaming in progress"
                      />
                    )}
                  </div>

                  {/* STREAMING STATUS BAR & STOP BUTTON */}
                  {message.isStreaming && (
                    <div className="chat-bubble__streaming-bar">
                      <span>⚡ GENERATING STREAMING EVIDENCE RESPONSE…</span>
                      <button
                        type="button"
                        className="chat-bubble__stop-btn"
                        onClick={handleStopGeneration}
                        aria-label="Stop generation"
                      >
                        STOP STREAMING ✕
                      </button>
                    </div>
                  )}

                  {/* METRICS & FOOTER (ONCE STREAMING COMPLETES) */}
                  {!message.isStreaming && (
                    <div className="chat-bubble__footer">
                      <div className="chat-bubble__metrics-row">
                        {message.latencyMs !== undefined && (
                          <span>
                            ⚡ LATENCY: <strong className="chat-bubble__latency-tag">{message.latencyMs}ms</strong>
                          </span>
                        )}

                        {hasCitations && (
                          <span>
                            CITED EVIDENCE: <strong>{citationsList.length} sources</strong>
                          </span>
                        )}

                        <div className="chat-bubble__action-buttons">
                          <button
                            type="button"
                            className="chat-bubble__copy-btn"
                            onClick={() => void navigator.clipboard.writeText(message.content)}
                            aria-label="Copy assistant answer"
                          >
                            COPY ANSWER
                          </button>
                        </div>
                      </div>

                      {/* EXPANDABLE REFERENCED EVIDENCE DRAWER */}
                      {hasCitations && (
                        <div className="chat-bubble__evidence-drawer">
                          <button
                            type="button"
                            className="chat-bubble__evidence-drawer-header"
                            onClick={() => toggleDrawer(message.id)}
                            aria-expanded={isDrawerOpen}
                            aria-label="Toggle referenced evidence list"
                          >
                            <span>
                              REFERENCED EVIDENCE ({citationsList.length}):{' '}
                              {citationsList.map((c) => `[${c.evidence_id}]`).join(' ')}
                            </span>
                            <span>{isDrawerOpen ? '▲ COLLAPSE' : '▼ EXPAND ALL'}</span>
                          </button>

                          {isDrawerOpen && (
                            <ul className="chat-bubble__evidence-list">
                              {citationsList.map((evidence) => (
                                <li key={evidence.evidence_id} className="chat-bubble__evidence-item">
                                  <div className="chat-bubble__evidence-item-header">
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                      <span className="chat-bubble__evidence-id">
                                        [{evidence.evidence_id}]
                                      </span>
                                      <strong>{evidence.name}</strong>
                                      <span style={{ fontSize: '0.68rem', textTransform: 'uppercase', color: '#64748b' }}>
                                        ({evidence.kind})
                                      </span>
                                    </div>

                                    {evidence.symbol_id && onSelectSymbol && (
                                      <button
                                        type="button"
                                        className="bauhaus-btn-invert"
                                        style={{ padding: '2px 8px', fontSize: '0.68rem' }}
                                        onClick={() => onSelectSymbol(evidence.symbol_id!)}
                                      >
                                        INSPECT SYMBOL →
                                      </button>
                                    )}
                                  </div>

                                  <div className="chat-bubble__evidence-path">
                                    {evidence.file_path}:{evidence.start_line}-{evidence.end_line}
                                  </div>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* QUICK PROMPT STARTER CHIPS */}
      <div className="codebase-chat__starters">
        <span className="codebase-chat__starters-label">SUGGESTIONS:</span>
        {sampleStarterPrompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="codebase-chat__starter-chip"
            onClick={() => void executeSendMessage(prompt)}
            disabled={isGenerating}
          >
            {prompt}
          </button>
        ))}
      </div>

      {/* INPUT FORM */}
      <form
        className="codebase-chat__input-form"
        onSubmit={(e) => {
          e.preventDefault();
          void executeSendMessage(inputValue);
        }}
      >
        <textarea
          className="codebase-chat__textarea"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about symbols, architecture, citations, or endpoints (e.g., 'How does the resolver work?')..."
          rows={3}
          maxLength={4000}
          aria-label="Ask a question about the repository"
        />

        <div className="codebase-chat__controls-row">
          <span className="codebase-chat__tip">
            Press <kbd style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>Enter</kbd> to send, <kbd style={{ fontFamily: 'var(--font-mono)' }}>Shift+Enter</kbd> for new line
          </span>

          <button
            type="submit"
            className="codebase-chat__send-btn"
            disabled={!inputValue.trim() || isGenerating}
          >
            {isGenerating ? 'GENERATING…' : 'ASK REPOSCOPE →'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default CodebaseChat;
