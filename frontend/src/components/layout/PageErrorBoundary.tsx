import { Component, type ErrorInfo, type ReactNode } from 'react'

interface PageErrorBoundaryProps {
  /** Shown to the user, e.g. "Plan". */
  name: string
  children: ReactNode
}

interface PageErrorBoundaryState {
  error: Error | null
}

/**
 * Keeps one broken page from blanking the whole app.
 *
 * A render-time throw inside a page would otherwise unmount the entire React
 * tree (there is no boundary above the router), leaving a blank screen with no
 * explanation and no way back. This shows a calm message with a Retry button
 * that resets the boundary, and logs the error with its component stack in dev.
 */
export class PageErrorBoundary extends Component<PageErrorBoundaryProps, PageErrorBoundaryState> {
  state: PageErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): PageErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (import.meta.env.DEV) {
      console.error(`[${this.props.name}] render failed`, error, info.componentStack)
    }
  }

  private readonly retry = () => {
    this.setState({ error: null })
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children
    return (
      <div className="page page__crash" role="alert">
        <div className="page__crash-card">
          <h1 className="page__crash-title">{this.props.name} couldn't be displayed</h1>
          <p className="page__crash-copy">
            Something went wrong while drawing this page. Your data is safe — retry, and if it keeps
            happening, try reloading the app.
          </p>
          <button type="button" className="profile__save" onClick={this.retry}>
            Retry
          </button>
        </div>
      </div>
    )
  }
}