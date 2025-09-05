import React, { useState, useRef, useEffect } from 'react';
import styled from 'styled-components';
import axios from 'axios';

interface ChatMessage {
  role: string;
  content: string;
  metadata?: {
    title?: string;
  };
}

interface ChatInterfaceProps {
  onSlideUpdate: () => void;
}

const ChatContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 500px;
`;

const MessagesContainer = styled.div`
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  background: white;
  margin-bottom: 16px;
  max-height: 400px;
`;

const Message = styled.div<{ $isUser: boolean; $hasMetadata?: boolean }>`
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  align-items: ${props => props.$isUser ? 'flex-end' : 'flex-start'};
`;

const MessageBubble = styled.div<{ $isUser: boolean; $hasMetadata?: boolean }>`
  max-width: 80%;
  padding: 12px 16px;
  border-radius: 18px;
  background: ${props => {
    if (props.$hasMetadata) return '#f3f4f6';
    return props.$isUser ? '#667eea' : '#f3f4f6';
  }};
  color: ${props => {
    if (props.$hasMetadata) return '#374151';
    return props.$isUser ? 'white' : '#374151';
  }};
  word-wrap: break-word;
  line-height: 1.5;
  border: ${props => props.$hasMetadata ? '1px solid #d1d5db' : 'none'};
`;

const MessageMetadata = styled.div`
  font-size: 0.8rem;
  color: #6b7280;
  margin-bottom: 4px;
  font-weight: 600;
`;

const InputContainer = styled.div`
  display: flex;
  gap: 8px;
`;

const TextInput = styled.textarea`
  flex: 1;
  padding: 12px 16px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  resize: vertical;
  min-height: 60px;
  max-height: 120px;
  font-family: inherit;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;

  &:focus {
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }

  &::placeholder {
    color: #9ca3af;
  }
`;

const SendButton = styled.button`
  padding: 12px 24px;
  background: #667eea;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  transition: background-color 0.2s;
  align-self: flex-end;

  &:hover:not(:disabled) {
    background: #5a67d8;
  }

  &:disabled {
    background: #9ca3af;
    cursor: not-allowed;
  }
`;

const LoadingIndicator = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
  font-style: italic;
`;

const PlaceholderMessage = styled.div`
  text-align: center;
  color: #9ca3af;
  font-style: italic;
  padding: 40px 20px;
`;

const ChatInterface: React.FC<ChatInterfaceProps> = ({ onSlideUpdate }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('Generate a succinct report EY Parthenon. Do not generate more than 5 slides. Use the information available in your tools. Use visualisations. Include an overview slide of EY Parthenon. Think about your response.');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage = inputValue.trim();
    setInputValue('');
    setIsLoading(true);

    try {
      const response = await axios.post('http://localhost:8000/chat', {
        message: userMessage,
        session_id: 'default'
      });

      setMessages(response.data.messages);
      onSlideUpdate(); // Refresh slides after chat interaction
    } catch (error) {
      console.error('Error sending message:', error);
      // Add error message to chat
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, there was an error processing your request. Please try again.',
        metadata: { title: '❌ Error' }
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const renderMessage = (message: ChatMessage, index: number) => {
    const isUser = message.role === 'user';
    const hasMetadata = !!message.metadata?.title;

    return (
      <Message key={index} $isUser={isUser} $hasMetadata={hasMetadata}>
        {hasMetadata && (
          <MessageMetadata>{message.metadata?.title}</MessageMetadata>
        )}
        <MessageBubble $isUser={isUser} $hasMetadata={hasMetadata}>
          {message.content}
        </MessageBubble>
      </Message>
    );
  };

  return (
    <ChatContainer>
      <MessagesContainer>
        {messages.length === 0 ? (
          <PlaceholderMessage>
            Start by asking me to create slides! For example: 'Create a 3-slide deck about AI benefits'
          </PlaceholderMessage>
        ) : (
          messages.map(renderMessage)
        )}
        
        {isLoading && (
          <LoadingIndicator>
            <span>🤔 Thinking...</span>
          </LoadingIndicator>
        )}
        
        <div ref={messagesEndRef} />
      </MessagesContainer>
      
      <InputContainer>
        <TextInput
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Enter your slide creation request here..."
          disabled={isLoading}
        />
        <SendButton onClick={sendMessage} disabled={isLoading || !inputValue.trim()}>
          Send
        </SendButton>
      </InputContainer>
    </ChatContainer>
  );
};

export default ChatInterface;
