import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../../context/AuthContext'
import { Sidebar } from './Sidebar'
import type { Conversation } from '../../types'

const mockConversations: Conversation[] = [
  { id: '1', title: 'Workout plan', created_at: '', updated_at: '' },
  { id: '2', title: 'Nutrition goals', created_at: '', updated_at: '' },
]

function renderSidebar(props = {}) {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Sidebar
          open={true}
          onToggle={vi.fn()}
          onClose={vi.fn()}
          conversations={mockConversations}
          selectedId={null}
          loading={false}
          error={null}
          searchQuery=""
          onSearchQueryChange={vi.fn()}
          onSelectConversation={vi.fn()}
          onNewChat={vi.fn()}
          onRename={vi.fn()}
          onDelete={vi.fn()}
          {...props}
        />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Sidebar', () => {
  it('renders conversation list', () => {
    renderSidebar()
    expect(screen.getByText('Workout plan')).toBeInTheDocument()
    expect(screen.getByText('Nutrition goals')).toBeInTheDocument()
  })

  it('calls onToggle when header toggle button is clicked', () => {
    const onToggle = vi.fn()
    renderSidebar({ onToggle })
    fireEvent.click(screen.getByLabelText('Close sidebar'))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('filters conversations via search input', () => {
    const onSearchQueryChange = vi.fn()
    renderSidebar({ onSearchQueryChange })
    const input = screen.getByLabelText('Search conversations')
    fireEvent.change(input, { target: { value: 'nutrition' } })
    expect(onSearchQueryChange).toHaveBeenCalledWith('nutrition')
  })

  it('calls onNewChat when new chat button is clicked', () => {
    const onNewChat = vi.fn()
    renderSidebar({ onNewChat })
    fireEvent.click(screen.getByRole('button', { name: 'New chat' }))
    expect(onNewChat).toHaveBeenCalledTimes(1)
  })

  it('shows the wordmark only when expanded', () => {
    const { unmount } = renderSidebar()
    expect(screen.getByText('FitAI')).toBeInTheDocument()
    unmount()

    renderSidebar({ open: false })
    expect(screen.queryByText('FitAI')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Open sidebar')).toBeInTheDocument()
  })

  it('keeps the collapsed rail icon-only on every route', () => {
    for (const route of ['/plan', '/progress', '/library']) {
      const view = render(
        <MemoryRouter initialEntries={[route]}>
          <AuthProvider>
            <Sidebar
              open={false}
              onToggle={vi.fn()}
              onClose={vi.fn()}
              conversations={mockConversations}
              selectedId={null}
              loading={false}
              error={null}
              searchQuery=""
              onSearchQueryChange={vi.fn()}
              onSelectConversation={vi.fn()}
              onNewChat={vi.fn()}
              onRename={vi.fn()}
              onDelete={vi.fn()}
            />
          </AuthProvider>
        </MemoryRouter>,
      )
      const rail = view.container.querySelector('.sidebar') as HTMLElement
      expect(rail.textContent).toBe('')
      view.unmount()
    }
  })
})
