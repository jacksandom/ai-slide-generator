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
  const [lastMessageCount, setLastMessageCount] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const pollForUpdates = async () => {
    try {
      console.log('Polling for updates...');
      const response = await axios.get('http://localhost:8000/chat/status/default');
      const newMessages = response.data.messages;
      const newMessageCount = response.data.message_count;
      
      console.log(`Received ${newMessageCount} messages (was ${lastMessageCount})`);
      console.log('Current messages in state:', messages.length);
      
      // Always update if there are new messages
      if (newMessageCount !== lastMessageCount) {
        console.log('Message count changed, updating UI');
        console.log('New messages:', newMessages);
        setMessages([...newMessages]); // Force new array to trigger re-render
        setLastMessageCount(newMessageCount);
        onSlideUpdate(); // Refresh slides when conversation updates
      }
      
      // More relaxed completion detection - only stop if we haven't seen new messages for a while
      const lastMessage = newMessages[newMessages.length - 1];
      let shouldStopPolling = false;
      
      if (newMessages.length > 1 && lastMessage?.role === 'assistant') {
        // Look for a final assistant message that's not a tool message
        const isToolMessage = lastMessage.metadata?.title?.includes('🔧') || 
                             lastMessage.metadata?.title?.includes('tool') ||
                             lastMessage.metadata?.title?.includes('Tool');
        
        console.log(`Last message: role=${lastMessage.role}, hasMetadata=${!!lastMessage.metadata?.title}, isToolMessage=${isToolMessage}`);
        
        // Only stop if it's been a regular assistant message for a few polls
        if (!isToolMessage && !lastMessage.metadata?.title) {
          // Check if message count hasn't changed recently
          if (newMessageCount === lastMessageCount) {
            shouldStopPolling = true;
          }
        }
      }
      
      if (shouldStopPolling) {
        console.log('Conversation appears complete, stopping polling');
        setIsLoading(false);
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      }
    } catch (error: any) {
      console.error('Error polling for updates:', error);
      console.error('Error details:', error.response?.data || error.message);
      // Continue polling on error
    }
  };

  const startPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
    }
    
    // Start polling every 1000ms for real-time feel
    pollingRef.current = setInterval(pollForUpdates, 1000);
    
    // Set a timeout to stop polling after 2 minutes if no completion detected
    setTimeout(() => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
        setIsLoading(false);
      }
    }, 120000); // 2 minutes
  };

  const sendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage = inputValue.trim();
    setInputValue('');
    setIsLoading(true);

    try {
      // Send message to backend
      const response = await axios.post('http://localhost:8000/chat', {
        message: userMessage,
        session_id: 'default'
      });

      // Update with immediate response (should include user message)
      setMessages(response.data.messages);
      setLastMessageCount(response.data.messages.length);
      
      // Start polling for real-time updates
      startPolling();
      
    } catch (error) {
      console.error('Error sending message:', error);
      // Add error message to chat
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, there was an error processing your request. Please try again.',
        metadata: { title: '❌ Error' }
      }]);
      setIsLoading(false);
    }
  };

  // Test function to debug the backend connection
  const testBackendConnection = async () => {
    try {
      console.log('Testing backend connection...');
      const response = await axios.get('http://localhost:8000/health');
      console.log('Backend health check:', response.data);
      
      const statusResponse = await axios.get('http://localhost:8000/chat/status/default');
      console.log('Current conversation status:', statusResponse.data);
      
      // Force update UI with current messages
      setMessages([...statusResponse.data.messages]);
      setLastMessageCount(statusResponse.data.message_count);
    } catch (error: any) {
      console.error('Backend connection test failed:', error);
    }
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

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
            <span>🤔 Processing your request...</span>
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
        <SendButton onClick={testBackendConnection} style={{background: '#10b981'}}>
          Test
        </SendButton>
      </InputContainer>
    </ChatContainer>
  );
};

export default ChatInterface;
