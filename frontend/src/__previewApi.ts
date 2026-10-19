/** Throwaway mock of the API client for the chat verification harness. Never committed. */

export const api = {
  listConversations: async () => [],
  getConversation: async () => null,
  createConversation: async () => ({ id: 'c1', title: 'New chat', created_at: '', updated_at: '' }),
  getMessages: async () => [],
  sendMessage: async (payload: { message: string }) => {
    console.log('SEND', JSON.stringify(payload.message))
    return {
      conversation_id: 'c1',
      title: payload.message.slice(0, 40),
      response: `You said: ${payload.message}`,
    }
  },
  renameConversation: async () => undefined,
  deleteConversation: async () => undefined,
  onAuthError: undefined,
}

export const toMessage = (err: unknown, fallback: string) => (err instanceof Error ? err.message : fallback)
export const isAbortError = () => false