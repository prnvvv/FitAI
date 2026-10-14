import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MessageBubble } from './MessageBubble'
import { api } from '../../services/api'
import type { Message } from '../../types'

vi.mock('../../services/api', () => ({
  api: {
    confirmMemoryUpdate: vi.fn(),
    rejectMemoryUpdate: vi.fn(),
    confirmChatAction: vi.fn(),
    rejectChatAction: vi.fn(),
  },
}))

const userMessage: Message = {
  id: '1',
  conversation_id: 'c1',
  role: 'user',
  content: 'Hi',
  created_at: '',
}

const assistantMessage: Message = {
  id: '2',
  conversation_id: 'c1',
  role: 'assistant',
  content: 'Hello **there**',
  created_at: '',
}

describe('MessageBubble', () => {
  it('renders user message', () => {
    render(<MessageBubble message={userMessage} />)
    expect(screen.getByText('Hi')).toBeInTheDocument()
  })

  it('renders assistant markdown', () => {
    render(<MessageBubble message={assistantMessage} />)
    expect(screen.getByText('there')).toBeInTheDocument()
  })

  describe('confirmable chat actions', () => {
    const reply: Message = {
      id: 'm3',
      conversation_id: 'c1',
      role: 'assistant',
      content: 'Done',
      created_at: '',
    }

    const workoutMessage: Message = {
      id: '2',
      conversation_id: 'c1',
      role: 'assistant',
      content: 'Just confirm and I will add it.',
      metadata: {
        actions: [
          {
            type: 'log_workout',
            proposal_id: 'a1',
            title: 'Add to calendar',
            description: 'Treadmill 120 min',
          },
        ],
      },
      created_at: '',
    }

    beforeEach(() => {
      vi.mocked(api.confirmChatAction).mockResolvedValue({ message: reply })
      vi.mocked(api.rejectChatAction).mockResolvedValue({ message: reply })
    })

    it('renders a workout action card', () => {
      render(<MessageBubble message={workoutMessage} />)
      expect(screen.getByText('Add to calendar')).toBeInTheDocument()
      expect(screen.getByText('Treadmill 120 min')).toBeInTheDocument()
    })

    it('confirms a chat action and appends the reply', async () => {
      const onReply = vi.fn()
      render(<MessageBubble message={workoutMessage} onReply={onReply} />)
      await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))
      await waitFor(() => expect(api.confirmChatAction).toHaveBeenCalledWith('a1'))
      expect(onReply).toHaveBeenCalledWith(reply)
    })

    it('dismisses a chat action and appends the reply', async () => {
      const onReply = vi.fn()
      render(<MessageBubble message={workoutMessage} onReply={onReply} />)
      await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
      await waitFor(() => expect(api.rejectChatAction).toHaveBeenCalledWith('a1'))
      expect(onReply).toHaveBeenCalledWith(reply)
    })
  })
})
