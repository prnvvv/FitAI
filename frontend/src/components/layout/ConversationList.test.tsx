import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConversationList } from './ConversationList'
import type { Conversation } from '../../types'

const mockConversations: Conversation[] = [
  { id: '1', title: 'Workout plan', created_at: '', updated_at: '' },
  { id: '2', title: 'Nutrition goals', created_at: '', updated_at: '' },
]

describe('ConversationList', () => {
  it('renders conversations', () => {
    render(
      <ConversationList
        conversations={mockConversations}
        selectedId={null}
        loading={false}
        error={null}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByText('Workout plan')).toBeInTheDocument()
    expect(screen.getByText('Nutrition goals')).toBeInTheDocument()
  })

  it('highlights selected conversation', () => {
    render(
      <ConversationList
        conversations={mockConversations}
        selectedId="1"
        loading={false}
        error={null}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    const item = screen.getByTestId('conversation-item-1')
    expect(item).toHaveClass('conversation-item--selected')
  })

  it('calls onSelect when conversation is clicked', () => {
    const onSelect = vi.fn()
    render(
      <ConversationList
        conversations={mockConversations}
        selectedId={null}
        loading={false}
        error={null}
        onSelect={onSelect}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByText('Workout plan'))
    expect(onSelect).toHaveBeenCalledWith('1')
  })

  it('calls onRename after inline editing', () => {
    const onRename = vi.fn()
    render(
      <ConversationList
        conversations={mockConversations}
        selectedId={null}
        loading={false}
        error={null}
        onSelect={vi.fn()}
        onRename={onRename}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getAllByLabelText('Conversation options')[0])
    fireEvent.click(screen.getByRole('menuitem', { name: /Rename/i }))
    const input = screen.getByLabelText('Rename conversation')
    fireEvent.change(input, { target: { value: 'Updated title' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRename).toHaveBeenCalledWith('1', 'Updated title')
  })

  it('calls onDelete after confirmation', () => {
    const onDelete = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(
      <ConversationList
        conversations={mockConversations}
        selectedId={null}
        loading={false}
        error={null}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onDelete={onDelete}
      />,
    )
    fireEvent.click(screen.getAllByLabelText('Conversation options')[0])
    fireEvent.click(screen.getByRole('menuitem', { name: /Delete/i }))
    expect(onDelete).toHaveBeenCalledWith('1')
    vi.restoreAllMocks()
  })

  it('shows empty state when no conversations', () => {
    render(
      <ConversationList
        conversations={[]}
        selectedId={null}
        loading={false}
        error={null}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByText('No chats found')).toBeInTheDocument()
  })
})
