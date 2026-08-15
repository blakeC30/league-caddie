import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Intentionally silent — avoid exposing stack traces in DevTools.
    // When error reporting (e.g. Sentry) is added, send the error here.
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-ink-50 px-4">
          <div className="bg-white border border-ink-200 rounded-sm p-10 max-w-md w-full text-center shadow-sheet">
            <div className="w-12 h-12 bg-flag-50 text-flag-600 rounded-xs flex items-center justify-center mx-auto mb-4">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-ink-900 mb-2">
              Something went wrong
            </h1>
            <p className="text-sm text-ink-500 mb-6">
              An unexpected error occurred. Try refreshing the page.
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false });
                window.location.href = "/";
              }}
              className="bg-fairway-700 hover:bg-fairway-700 text-white font-semibold py-3 px-6 rounded-xs shadow-sheet"
            >
              Go to home page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
