import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

  const renderList = (onDelete: () => void | Promise<void>) =>
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

  const openDeleteDialog = () => {
    fireEvent.click(screen.getAllByLabelText('Conversation options')[0])
    fireEvent.click(screen.getByRole('menuitem', { name: /Delete/i }))
  }

  it('asks in-app for confirmation and does not delete until confirmed', async () => {
    const nativeConfirm = vi.spyOn(window, 'confirm')
    const onDelete = vi.fn()
    renderList(onDelete)
    openDeleteDialog()
    expect(screen.getByRole('dialog', { name: 'Delete conversation?' })).toBeInTheDocument()
    expect(onDelete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith('1'))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(nativeConfirm).not.toHaveBeenCalled()
    vi.restoreAllMocks()
  })

  it('cancel and Escape close the dialog without deleting', () => {
    const onDelete = vi.fn()
    renderList(onDelete)
    openDeleteDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    openDeleteDialog()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(onDelete).not.toHaveBeenCalled()
  })

  it('keeps the dialog open with an error when deletion fails', async () => {
    const onDelete = vi.fn().mockRejectedValue(new Error('Server unavailable'))
    renderList(onDelete)
    openDeleteDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Server unavailable')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('blocks duplicate submissions while deleting', async () => {
    let finish: () => void = () => undefined
    const onDelete = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)))
    renderList(onDelete)
    openDeleteDialog()
    const button = screen.getByRole('button', { name: 'Delete' })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(onDelete).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Working…' })).toBeDisabled()
    finish()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
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
