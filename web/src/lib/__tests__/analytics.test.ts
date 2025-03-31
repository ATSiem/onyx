import { 
  AnalyticsEventType,
  trackChatThreadCreated,
  trackChatMessageSent 
} from '../analytics';

// Mock the posthog library
jest.mock('posthog-js', () => ({
  __esModule: true,
  default: {
    capture: jest.fn(),
  },
}));

// Import the mocked posthog
import posthog from 'posthog-js';

describe('Analytics', () => {
  beforeEach(() => {
    // Clear all mocks before each test
    jest.clearAllMocks();
  });

  describe('trackChatThreadCreated', () => {
    it('should call posthog.capture with correct parameters', () => {
      // Arrange
      const chatSessionId = 'test-session-id';
      const personaId = 123;
      const description = 'Test description';

      // Act
      trackChatThreadCreated(chatSessionId, personaId, description);

      // Assert
      expect(posthog.capture).toHaveBeenCalledTimes(1);
      expect(posthog.capture).toHaveBeenCalledWith(
        AnalyticsEventType.CHAT_THREAD_CREATED,
        {
          chat_session_id: chatSessionId,
          persona_id: personaId,
          description: description
        }
      );
    });

    it('should handle null description', () => {
      // Arrange
      const chatSessionId = 'test-session-id';
      const personaId = 123;
      const description = null;

      // Act
      trackChatThreadCreated(chatSessionId, personaId, description);

      // Assert
      expect(posthog.capture).toHaveBeenCalledTimes(1);
      expect(posthog.capture).toHaveBeenCalledWith(
        AnalyticsEventType.CHAT_THREAD_CREATED,
        {
          chat_session_id: chatSessionId,
          persona_id: personaId,
          description: undefined
        }
      );
    });
  });

  describe('trackChatMessageSent', () => {
    it('should call posthog.capture with correct parameters for user message', () => {
      // Arrange
      const chatSessionId = 'test-session-id';
      const messageId = 456;
      const isUserMessage = true;
      const hasAttachments = false;

      // Act
      trackChatMessageSent(chatSessionId, messageId, isUserMessage, hasAttachments);

      // Assert
      expect(posthog.capture).toHaveBeenCalledTimes(1);
      expect(posthog.capture).toHaveBeenCalledWith(
        AnalyticsEventType.CHAT_MESSAGE_SENT,
        {
          chat_session_id: chatSessionId,
          message_id: messageId,
          is_user_message: isUserMessage,
          has_attachments: hasAttachments
        }
      );
    });

    it('should call posthog.capture with correct parameters for assistant message with attachments', () => {
      // Arrange
      const chatSessionId = 'test-session-id';
      const messageId = 789;
      const isUserMessage = false;
      const hasAttachments = true;

      // Act
      trackChatMessageSent(chatSessionId, messageId, isUserMessage, hasAttachments);

      // Assert
      expect(posthog.capture).toHaveBeenCalledTimes(1);
      expect(posthog.capture).toHaveBeenCalledWith(
        AnalyticsEventType.CHAT_MESSAGE_SENT,
        {
          chat_session_id: chatSessionId,
          message_id: messageId,
          is_user_message: isUserMessage,
          has_attachments: hasAttachments
        }
      );
    });
  });
}); 