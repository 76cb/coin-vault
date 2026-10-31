import { Component, ReactNode } from "react";

/** If a page fails to draw, say so with the reason instead of leaving a blank screen. */
export default class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null }); // another page: try again
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page-error" role="alert">
        <h1>This page couldn't be shown</h1>
        <p>Something went wrong while drawing it: <code>{this.state.error.message}</code></p>
        <p>
          <button type="button" className="primary" onClick={() => window.location.reload()}>Reload</button>{" "}
          <a href="/">Back to the collection</a>
        </p>
      </div>
    );
  }
}
