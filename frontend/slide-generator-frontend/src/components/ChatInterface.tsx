import React, { useState, useRef, useEffect } from 'react';
import styled from 'styled-components';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';

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
  flex: 1;
  min-height: 0;
`;

const MessagesContainer = styled.div`
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  background: white;
  margin-bottom: 16px;
  min-height: 0;
`;

const Message = styled.div<{ $isUser: boolean }>`
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  align-items: ${props => props.$isUser ? 'flex-end' : 'flex-start'};
`;

const MessageBubble = styled.div<{ $isUser: boolean }>`
  max-width: 85%;
  padding: 12px 16px;
  border-radius: 18px;
  background: ${props => props.$isUser ? '#667eea' : '#f3f4f6'};
  color: ${props => props.$isUser ? 'white' : '#374151'};
  word-wrap: break-word;
  line-height: 1.5;
  font-size: 14px;
`;

const MarkdownContent = styled.div`
  h1, h2, h3, h4, h5, h6 {
    margin: 0.5em 0 0.3em 0;
    font-weight: 600;
  }
  
  h1 { font-size: 1.3em; }
  h2 { font-size: 1.2em; }
  h3 { font-size: 1.1em; }
  h4 { font-size: 1.05em; }
  
  p {
    margin: 0.5em 0;
    
    &:first-child {
      margin-top: 0;
    }
    
    &:last-child {
      margin-bottom: 0;
    }
  }
  
  ul, ol {
    margin: 0.5em 0;
    padding-left: 1.5em;
  }
  
  li {
    margin: 0.2em 0;
  }
  
  code {
    background: rgba(0, 0, 0, 0.08);
    padding: 2px 4px;
    border-radius: 3px;
    font-family: 'Courier New', monospace;
    font-size: 0.85em;
  }
  
  pre {
    background: rgba(0, 0, 0, 0.08);
    padding: 8px 12px;
    border-radius: 6px;
    overflow-x: auto;
    margin: 0.5em 0;
    
    code {
      background: none;
      padding: 0;
    }
  }
  
  blockquote {
    border-left: 3px solid #667eea;
    margin: 0.5em 0;
    padding-left: 1em;
    font-style: italic;
  }
  
  strong {
    font-weight: 600;
  }
  
  em {
    font-style: italic;
  }
  
  a {
    color: #4f46e5;
    text-decoration: none;
    
    &:hover {
      text-decoration: underline;
    }
  }
`;

const ToolSection = styled.div`
  margin-bottom: 16px;
  width: 100%;
`;

const ToolAccordion = styled.div`
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafbfc;
`;

const ToolHeader = styled.button<{ $isExpanded: boolean }>`
  width: 100%;
  padding: 12px 16px;
  background: #f8fafc;
  border: none;
  border-radius: ${props => props.$isExpanded ? '8px 8px 0 0' : '8px'};
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: #6366f1;
  transition: background-color 0.2s;

  &:hover {
    background: #f1f5f9;
  }
`;

const ToolIcon = styled.span<{ $isExpanded: boolean }>`
  transition: transform 0.2s;
  transform: ${props => props.$isExpanded ? 'rotate(90deg)' : 'rotate(0deg)'};
`;

const ToolContent = styled.div<{ $isExpanded: boolean }>`
  display: ${props => props.$isExpanded ? 'block' : 'none'};
  padding: 16px;
  border-top: 1px solid #e5e7eb;
  background: white;
  border-radius: 0 0 8px 8px;
`;

const ToolMessage = styled.div<{ $isRequest: boolean }>`
  padding: 8px 12px;
  margin-bottom: 8px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.4;
  background: ${props => props.$isRequest ? '#fef3c7' : '#d1fae5'};
  border-left: 3px solid ${props => props.$isRequest ? '#f59e0b' : '#10b981'};
`;

const ToolLabel = styled.div`
  font-weight: 600;
  margin-bottom: 4px;
  color: #374151;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
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
  min-height: 100px;
  max-height: 200px;
  font-family: inherit;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
  line-height: 1.5;

  &:focus {
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }

  &::placeholder {
    color: #9ca3af;
  }
`;

const SendButton = styled.button`
  padding: 14px 16px;
  background: #667eea;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 16px;
  transition: background-color 0.2s;
  align-self: flex-end;
  display: flex;
  align-items: center;
  justify-content: center;

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
  font-size: 13px;
`;

const PlaceholderMessage = styled.div`
  text-align: center;
  color: #9ca3af;
  font-style: italic;
  padding: 40px 20px;
`;

interface ToolGroup {
  id: string;
  messages: ChatMessage[];
  isExpanded: boolean;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({ onSlideUpdate }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('Generate a succinct report EY Parthenon. Do not generate more than 5 slides. Use the information available in your tools. Use visualisations. Include an overview slide of EY Parthenon. Think about your response.');
  const [isLoading, setIsLoading] = useState(false);
  const [lastMessageCount, setLastMessageCount] = useState(0);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const toggleToolExpansion = (toolId: string) => {
    setExpandedTools(prev => {
      const newSet = new Set(prev);
      if (newSet.has(toolId)) {
        newSet.delete(toolId);
      } else {
        newSet.add(toolId);
      }
      return newSet;
    });
  };

  const pollForUpdates = async () => {
    try {
      console.log('Polling for updates...');
      const response = await axios.get('http://localhost:8000/chat/status/default');
      const newMessages = response.data.messages;
      const newMessageCount = response.data.message_count;
      
      console.log(`Current count: ${lastMessageCount}, New count: ${newMessageCount}`);
      
      if (newMessageCount !== lastMessageCount) {
        console.log('Message count changed, updating UI');
        console.log('New messages:', newMessages);
        setMessages([...newMessages]); // Force new array to trigger re-render
        setLastMessageCount(newMessageCount);
        onSlideUpdate(); // Refresh slides when new messages arrive
      }
      
      // Check if conversation is complete
      if (newMessages.length > 0) {
        const lastMessage = newMessages[newMessages.length - 1];
        const lastFewMessages = newMessages.slice(-3); // Look at last 3 messages
        
        // Stop polling if we have a final assistant response (not a tool-related message)
        if (lastMessage?.role === 'assistant') {
          // Look for tool result followed by assistant response pattern
          const hasToolResult = lastFewMessages.some((msg: ChatMessage) => msg.metadata?.title?.includes('Tool result'));
          const hasFollowupResponse = lastMessage && !lastMessage.metadata?.title;
          
          // Or just a regular assistant response without tool usage
          if ((hasToolResult && hasFollowupResponse) || (!hasToolResult && !lastMessage.metadata?.title)) {
            console.log('Conversation appears complete, stopping polling after a few more checks');
            // Give it a few more polls to make sure
            setTimeout(() => {
              if (pollingRef.current) {
                clearInterval(pollingRef.current);
                pollingRef.current = null;
                setIsLoading(false);
                console.log('Polling stopped - conversation complete');
              }
            }, 3000); // Wait 3 seconds to confirm completion
          }
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
    pollingRef.current = setInterval(pollForUpdates, 1000); // Poll every second
  };

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
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

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: inputValue.trim()
    };

    // Add user message immediately
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      // Send message to backend
      await axios.post('http://localhost:8000/chat', {
        message: userMessage.content
      });

      // Start polling for updates
      startPolling();
    } catch (error) {
      console.error('Error sending message:', error);
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Group messages into conversation flows and tool groups
  const groupMessages = (messages: ChatMessage[]) => {
    const groups: (ChatMessage | ToolGroup)[] = [];
    let currentToolGroup: ChatMessage[] = [];
    let toolGroupId = 0;

    for (let i = 0; i < messages.length; i++) {
      const message = messages[i];
      const isToolMessage = message.metadata?.title && (
        message.metadata.title.includes('Tool') || 
        message.metadata.title.includes('tool')
      );

      if (isToolMessage) {
        currentToolGroup.push(message);
      } else {
        // If we have accumulated tool messages, create a tool group
        if (currentToolGroup.length > 0) {
          groups.push({
            id: `tool-group-${toolGroupId++}`,
            messages: [...currentToolGroup],
            isExpanded: false
          });
          currentToolGroup = [];
        }
        
        // Add the regular message
        groups.push(message);
      }
    }

    // Handle any remaining tool messages
    if (currentToolGroup.length > 0) {
      groups.push({
        id: `tool-group-${toolGroupId++}`,
        messages: [...currentToolGroup],
        isExpanded: false
      });
    }

    return groups;
  };

  const isToolGroup = (item: ChatMessage | ToolGroup): item is ToolGroup => {
    return 'id' in item && 'messages' in item;
  };

  const renderToolGroup = (toolGroup: ToolGroup) => {
    const isExpanded = expandedTools.has(toolGroup.id);
    const toolCount = toolGroup.messages.length;
    const hasRequests = toolGroup.messages.some(msg => msg.metadata?.title?.includes('request'));
    const hasResults = toolGroup.messages.some(msg => msg.metadata?.title?.includes('result'));

    return (
      <ToolSection key={toolGroup.id}>
        <ToolAccordion>
          <ToolHeader 
            $isExpanded={isExpanded}
            onClick={() => toggleToolExpansion(toolGroup.id)}
          >
            <span>
              🔧 AI Tools Used ({toolCount} operations)
              {hasRequests && hasResults && ' - Requests & Results'}
            </span>
            <ToolIcon $isExpanded={isExpanded}>▶</ToolIcon>
          </ToolHeader>
          <ToolContent $isExpanded={isExpanded}>
            {toolGroup.messages.map((msg, idx) => {
              const isRequest = !!(msg.metadata?.title?.toLowerCase().includes('request') || 
                               msg.metadata?.title?.toLowerCase().includes('tool call'));
              return (
                <ToolMessage key={idx} $isRequest={isRequest}>
                  <ToolLabel>
                    {isRequest ? '🚀 Tool Request' : '✅ Tool Result'}
                  </ToolLabel>
                  {msg.metadata?.title && (
                    <div style={{ fontWeight: 600, marginBottom: '4px', fontSize: '12px' }}>
                      {msg.metadata.title}
                    </div>
                  )}
                  <div>{msg.content}</div>
                </ToolMessage>
              );
            })}
          </ToolContent>
        </ToolAccordion>
      </ToolSection>
    );
  };

  const groupedMessages = groupMessages(messages);

  return (
    <ChatContainer>
      <MessagesContainer>
        {groupedMessages.length === 0 ? (
          <PlaceholderMessage>
            👋 Hi! I'm your AI slide creation assistant. I can create bespoke presentations leveraging our proprietary assets as well as public information from the Internet
          </PlaceholderMessage>
        ) : (
          groupedMessages.map((item, index) => {
            if (isToolGroup(item)) {
              return renderToolGroup(item);
            } else {
              const message = item;
              return (
                <Message key={index} $isUser={message.role === 'user'}>
                  <MessageBubble $isUser={message.role === 'user'}>
                    {message.role === 'assistant' ? (
                      <MarkdownContent>
                        <ReactMarkdown>{message.content}</ReactMarkdown>
                      </MarkdownContent>
                    ) : (
                      message.content
                    )}
                  </MessageBubble>
                </Message>
              );
            }
          })
        )}
        
        {isLoading && (
          <LoadingIndicator>
            <span>🤖</span>
            <span>AI is thinking and working...</span>
          </LoadingIndicator>
        )}
        
        <div ref={messagesEndRef} />
      </MessagesContainer>
      
      <InputContainer>
        <TextInput
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="👋 Hi! I'm your AI slide creation assistant. I can create bespoke presentations leveraging our proprietary assets as well as public information from the Internet"
          disabled={isLoading}
        />
        <SendButton onClick={handleSendMessage} disabled={isLoading || !inputValue.trim()}>
          {isLoading ? '⏳' : '➤'}
        </SendButton>
      </InputContainer>
    </ChatContainer>
  );
};

export default ChatInterface;