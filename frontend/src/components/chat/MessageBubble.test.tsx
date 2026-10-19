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

  it('renders escaped line-break html as a real line break', () => {
    const { container } = render(
      <MessageBubble
        message={{ ...assistantMessage, content: 'Warm up 5 min<br>Then 3 sets of 8' }}
      />,
    )
    expect(screen.queryByText(/<br>/)).not.toBeInTheDocument()
    expect(container.querySelector('.message__markdown br')).not.toBeNull()
  })

  it('wraps markdown tables in a scroll container', () => {
    const { container } = render(
      <MessageBubble
        message={{
          ...assistantMessage,
          content: '| Day | Exercise |\n| --- | --- |\n| Mon | Squat |',
        }}
      />,
    )
    const wrapper = container.querySelector('.message__table-scroll')
    expect(wrapper).not.toBeNull()
    expect(wrapper?.querySelector('table')).not.toBeNull()
    expect(wrapper?.getAttribute('tabindex')).toBe('0')
  })

  it('keeps code blocks untouched', () => {
    const { container } = render(
      <MessageBubble
        message={{ ...assistantMessage, content: '```html\n<b>bold</b>\n```' }}
      />,
    )
    expect(container.querySelector('pre code')?.textContent?.trim()).toBe('<b>bold</b>')
  })
})
