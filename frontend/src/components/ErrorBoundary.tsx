import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

// M9: without this, an uncaught render error anywhere in the dashboard
// (a bad API response shape, a null the UI didn't guard against, etc.)
// unmounts the whole React tree and leaves the user staring at a blank
// white page with no indication anything went wrong or how to recover.
// This catches it, shows a recoverable message, and lets them reload
// rather than needing to be told "try refreshing" over support chat.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Uncaught error in dashboard:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '60vh',
          textAlign: 'center',
          padding: '2rem',
          gap: '1rem',
        }}>
          <h2>Something went wrong</h2>
          <p style={{ color: 'var(--color-text-light, #666)', maxWidth: 420 }}>
            This page hit an unexpected error. Your data is safe — reloading
            usually fixes this.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '10px 24px',
              borderRadius: 6,
              border: 'none',
              background: 'var(--color-primary, #4f46e5)',
              color: 'white',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Reload page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
