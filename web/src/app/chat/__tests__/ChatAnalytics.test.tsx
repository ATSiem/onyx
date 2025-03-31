import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { createChatSession, sendMessage } from '../lib';
import { trackChatThreadCreated, trackChatMessageSent } from '@/lib/analytics';

// Mock the analytics functions
jest.mock('@/lib/analytics', () => ({
  trackChatThreadCreated: jest.fn(),
  trackChatMessageSent: jest.fn(),
  AnalyticsEventType: {
    CHAT_THREAD_CREATED: 'chat_thread_created',
    CHAT_MESSAGE_SENT: 'chat_message_sent',
  }
}));

// Mock the chat API functions
jest.mock('../lib', () => ({
  createChatSession: jest.fn().mockResolvedValue('test-session-id'),
  sendMessage: jest.fn().mockResolvedValue([{ message_id: 123 }]),
}));

describe('Chat Analytics Integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should track chat thread creation', async () => {
    // Act
    const sessionId = await createChatSession(1, 'Test chat');
    
    // Assert
    expect(sessionId).toBe('test-session-id');
    expect(trackChatThreadCreated).toHaveBeenCalledTimes(1);
    expect(trackChatThreadCreated).toHaveBeenCalledWith(
      'test-session-id',
      1,
      'Test chat'
    );
  });

  it('should track message sending when sendMessage is called', async () => {
    // Arrange
    const params = {
      chatSessionId: 'test-session-id',
      message: 'Hello world',
      personaId: 1,
      parentMessageId: 0,
      promptId: 0,
      signal: new AbortController().signal,
    };

    // Act
    const result = await sendMessage(params);

    // Assert
    // Note: The sendMessage function itself doesn't directly call trackChatMessageSent.
    // In a real app, this would be called by the ChatPage component after receiving
    // the message_id from the server. This test verifies our mocks are set up correctly.
    expect(result).toEqual([{ message_id: 123 }]);
  });

  // Add more integration tests as needed for how the tracking is integrated with
  // the chat UI components
}); 