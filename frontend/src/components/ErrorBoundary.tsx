import { Component } from 'react';
import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = {
    hasError: false,
  };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="code-viewer__error" role="alert">
          <h4>Unable to display the code preview</h4>
          <p>Close and reopen the preview to try again.</p>
        </div>
      );
    }

    return this.props.children;
  }
}