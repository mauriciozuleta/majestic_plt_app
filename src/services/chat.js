export const sendChatMessage = async (message) => {
  // TODO: replace with API call
  return {
    id: Date.now(),
    sender: 'bot',
    text: `Echo: ${message}`,
    createdAt: new Date().toISOString(),
  }
}
