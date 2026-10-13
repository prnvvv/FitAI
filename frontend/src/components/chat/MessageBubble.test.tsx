import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MessageBubble } from './MessageBubble'
import type { Message } from '../../types'

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
})
