import React, { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg m-2">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-red-700 text-sm font-medium">⚠️ Component Error</span>
          </div>
          <p className="text-xs text-red-600 mb-2">
            {this.state.error?.message ?? "Unknown error"}
          </p>
          {this.state.errorInfo && (
            <pre className="text-[10px] text-red-400 max-h-32 overflow-auto mb-2">
              {this.state.errorInfo.componentStack}
            </pre>
          )}
          <button
            onClick={this.handleRetry}
            className="text-[10px] px-2 py-1 rounded-md bg-red-100 text-red-700 hover:bg-red-200"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
