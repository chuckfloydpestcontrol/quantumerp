import React from 'react';
import { User, Bot, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { UIResponseType } from '../types';
import { GenerativeUI } from './GenerativeUI';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  responseType?: UIResponseType;
  responseData?: Record<string, unknown>;
  isLoading?: boolean;
  onAction?: (action: string, payload?: unknown) => void;
}

export function ChatMessage({
  role,
  content,
  responseType,
  responseData,
  isLoading,
  onAction,
}: ChatMessageProps) {
  const isUser = role === 'user';

  return (
    <div
      className={`flex gap-3 animate-fade-in ${
        isUser ? 'flex-row-reverse' : ''
      }`}
    >
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? 'bg-quantum-600' : 'bg-gray-200'
        }`}
      >
        {isUser ? (
          <User size={16} className="text-white" />
        ) : (
          <Bot size={16} className="text-gray-600" />
        )}
      </div>

      {/* Message Content */}
      <div className={`flex-1 max-w-[85%] ${isUser ? 'text-right' : ''}`}>
        {isLoading ? (
          <div className="inline-flex items-center gap-2 px-4 py-3 bg-gray-100 rounded-2xl">
            <Loader2 size={16} className="animate-spin text-quantum-600" />
            <span className="text-sm text-gray-500">Thinking...</span>
          </div>
        ) : (
          <>
            {/* Text content */}
            {content && (
              <div
                className={`inline-block px-4 py-3 rounded-2xl text-sm ${
                  isUser
                    ? 'bg-quantum-600 text-white'
                    : 'bg-gray-100 text-gray-800'
                }`}
              >
                {isUser ? (
                  <div className="whitespace-pre-wrap">{content}</div>
                ) : (
                  <div className="prose prose-sm max-w-none prose-headings:mt-2 prose-headings:mb-1 prose-p:my-1 prose-ul:my-1 prose-li:my-0">
                    <ReactMarkdown>{content}</ReactMarkdown>
                  </div>
                )}
              </div>
            )}

            {/* Generative UI component */}
            {!isUser && responseType && responseType !== 'text' && responseData && (
              <div className="mt-3">
                <GenerativeUI
                  type={responseType}
                  data={responseData}
                  onAction={onAction}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
