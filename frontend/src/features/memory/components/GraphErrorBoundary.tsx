"use client";

import React, { Component, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

/**
 * Error boundary specifically for the 3D graph component.
 * WebGL/Three.js can fail for various reasons (no WebGL support, GPU issues, memory).
 * This provides a graceful fallback UI.
 */
export class GraphErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log the error for debugging
    console.error("MemoryGraph Error:", error);
    console.error("Component Stack:", errorInfo.componentStack);

    this.setState({
      error,
      errorInfo,
    });
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      const isWebGLError =
        this.state.error?.message?.toLowerCase().includes("webgl") ||
        this.state.error?.message?.toLowerCase().includes("context");

      return (
        <div className="graph-error-boundary">
          <div className="graph-error-content">
            <AlertTriangle size={48} className="graph-error-icon" />
            <h3 className="graph-error-title">
              {isWebGLError
                ? "WebGL Not Available"
                : "Graph Visualization Error"}
            </h3>
            <p className="graph-error-message">
              {isWebGLError
                ? "Your browser or device does not support WebGL, which is required for the 3D graph visualization. Try using a different browser or enabling hardware acceleration."
                : "An error occurred while rendering the knowledge graph. This could be due to memory constraints or an incompatible browser."}
            </p>
            {process.env.NODE_ENV === "development" && this.state.error && (
              <details className="graph-error-details">
                <summary>Error Details</summary>
                <pre>{this.state.error.message}</pre>
                {this.state.errorInfo && (
                  <pre>{this.state.errorInfo.componentStack}</pre>
                )}
              </details>
            )}
            <button
              onClick={this.handleReset}
              className="graph-error-retry-btn"
            >
              <RefreshCw size={16} />
              <span>Try Again</span>
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default GraphErrorBoundary;
