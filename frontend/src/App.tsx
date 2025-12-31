import React, { useRef, useEffect } from 'react';
import { ChatProvider, useChat } from './contexts/ChatContext';
import { Sidebar } from './components/Sidebar';
import { ChatInput } from './components/ChatInput';
import { ChatMessage } from './components/ChatMessage';
import { Bot, Zap, Clock, Package } from 'lucide-react';

function WelcomeScreen({ onSuggestionClick }: { onSuggestionClick: (msg: string) => void }) {
  const suggestions = [
    {
      icon: Zap,
      title: 'Get a Quote',
      description: 'Calculate pricing for a manufacturing job',
      prompt: 'Quote 25 custom brackets for Acme Corp, aluminum, need by next Friday',
    },
    {
      icon: Clock,
      title: 'Schedule Production',
      description: 'Reserve machine time for urgent work',
      prompt: 'Schedule an emergency run of 50 parts for Premier Manufacturing',
    },
    {
      icon: Package,
      title: 'Check Inventory',
      description: 'View stock levels and availability',
      prompt: 'Do we have aluminum 6061 in stock?',
    },
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <div className="w-16 h-16 bg-quantum-100 rounded-2xl flex items-center justify-center mb-6">
        <Bot size={32} className="text-quantum-600" />
      </div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-2">
        Welcome to Quantum HUB
      </h1>
      <p className="text-gray-500 text-center max-w-md mb-8">
        Your AI-powered manufacturing ERP. Ask me anything about quotes, scheduling, inventory, or job status.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-3xl w-full">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion.title}
            onClick={() => onSuggestionClick(suggestion.prompt)}
            className="p-4 bg-white border border-gray-200 rounded-xl hover:border-quantum-300 hover:shadow-md transition-all text-left group"
          >
            <div className="w-10 h-10 bg-quantum-50 rounded-lg flex items-center justify-center mb-3 group-hover:bg-quantum-100 transition-colors">
              <suggestion.icon size={20} className="text-quantum-600" />
            </div>
            <div className="font-medium text-gray-900 mb-1">{suggestion.title}</div>
            <div className="text-sm text-gray-500">{suggestion.description}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

function ChatWindow() {
  const { messages, isLoading, sendMessage, clearChat } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleAction = (action: string, payload?: unknown) => {
    console.log('Action:', action, payload);
    // Handle actions from Generative UI components
    if (action === 'accept_quote') {
      const { quoteType } = payload as { quoteType: string };
      sendMessage(`Accept the ${quoteType} quote option`);
    } else if (action === 'view_job') {
      const { jobNumber } = payload as { jobNumber: string };
      sendMessage(`Show details for job ${jobNumber}`);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Chat Messages Area */}
      <div className="flex-1 overflow-y-auto p-6">
        {messages.length === 0 ? (
          <WelcomeScreen onSuggestionClick={sendMessage} />
        ) : (
          <div className="max-w-4xl mx-auto space-y-6">
            {messages.map((message) => (
              <ChatMessage
                key={message.id}
                role={message.role}
                content={message.content}
                responseType={message.responseType}
                responseData={message.responseData}
                isLoading={message.isLoading}
                onAction={handleAction}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="max-w-4xl mx-auto w-full">
        <ChatInput
          onSend={sendMessage}
          isLoading={isLoading}
          placeholder="Ask about quotes, scheduling, inventory, or jobs..."
        />
      </div>
    </div>
  );
}

function AppContent() {
  const { sendMessage, clearChat } = useChat();

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar
        onNewChat={clearChat}
        onQuickAction={sendMessage}
      />
      <main className="flex-1 flex flex-col overflow-hidden">
        <ChatWindow />
      </main>
    </div>
  );
}

function App() {
  return (
    <ChatProvider>
      <AppContent />
    </ChatProvider>
  );
}

export default App;
