import posthog from 'posthog-js';

export enum AnalyticsEventType {
  CHAT_THREAD_CREATED = 'chat_thread_created',
  CHAT_MESSAGE_SENT = 'chat_message_sent'
}

/**
 * Track chat thread creation event
 * @param chatSessionId The ID of the chat session
 * @param personaId The ID of the persona
 * @param description The description of the chat thread (optional)
 */
export function trackChatThreadCreated(
  chatSessionId: string, 
  personaId: number, 
  description: string | null
) {
  posthog.capture(AnalyticsEventType.CHAT_THREAD_CREATED, {
    chat_session_id: chatSessionId,
    persona_id: personaId,
    description: description ?? undefined
  });
}

/**
 * Track chat message sent event
 * @param chatSessionId The ID of the chat session
 * @param messageId The ID of the message
 * @param isUserMessage Whether the message is from the user
 * @param hasAttachments Whether the message has attachments
 */
export function trackChatMessageSent(
  chatSessionId: string,
  messageId: number,
  isUserMessage: boolean,
  hasAttachments: boolean
) {
  posthog.capture(AnalyticsEventType.CHAT_MESSAGE_SENT, {
    chat_session_id: chatSessionId,
    message_id: messageId,
    is_user_message: isUserMessage,
    has_attachments: hasAttachments
  });
} 