import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { chatApi } from '../services/api';
import { ChatMessage, UIResponseType } from '../types';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  responseType?: UIResponseType;
  responseData?: Record<string, unknown>;
  timestamp: Date;
  isLoading?: boolean;
}

interface ChatContextType {
  messages: Message[];
  threadId: string | null;
  isLoading: boolean;
  sendMessage: (content: string) => Promise<void>;
  clearChat: () => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const sendMessage = useCallback(async (content: string) => {
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      timestamp: new Date(),
    };

    // Add user message and loading placeholder
    const loadingId = crypto.randomUUID();
    setMessages(prev => [
      ...prev,
      userMessage,
      {
        id: loadingId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        isLoading: true,
      },
    ]);

    setIsLoading(true);

    try {
      const { data, error } = await chatApi.send(content, threadId || undefined);

      if (error) {
        setMessages(prev =>
          prev.map(m =>
            m.id === loadingId
              ? {
                  ...m,
                  content: `Error: ${error}`,
                  isLoading: false,
                  responseType: 'error' as UIResponseType,
                }
              : m
          )
        );
        return;
      }

      if (data) {
        setThreadId(data.thread_id);

        setMessages(prev =>
          prev.map(m =>
            m.id === loadingId
              ? {
                  ...m,
                  content: data.content,
                  responseType: data.response_type as UIResponseType,
                  responseData: data.response_data,
                  isLoading: false,
                }
              : m
          )
        );
      }
    } catch (err) {
      setMessages(prev =>
        prev.map(m =>
          m.id === loadingId
            ? {
                ...m,
                content: 'An unexpected error occurred. Please try again.',
                isLoading: false,
                responseType: 'error' as UIResponseType,
              }
            : m
        )
      );
    } finally {
      setIsLoading(false);
    }
  }, [threadId]);

  const clearChat = useCallback(() => {
    setMessages([]);
    setThreadId(null);
  }, []);

  return (
    <ChatContext.Provider value={{ messages, threadId, isLoading, sendMessage, clearChat }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
}
