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
  refreshTick?: number; // external trigger to refresh messages (e.g., after manual slide refresh)
}

const ChatContainer = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
  font-weight: 400;
`;

const MessagesContainer = styled.div`
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
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
  border-radius: 16px;
  background: ${props => props.$isUser ? '#1A9AFA' : '#f3f4f6'};
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
    border-left: 3px solid #1A9AFA;
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
    color: #1A9AFA;
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
  color: #ff3b2e;
  transition: background-color 0.2s;
  outline: none;

  &:focus, &:focus-visible {
    outline: none;
    box-shadow: none;
  }

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
  border-radius: 12px;
  resize: vertical;
  min-height: 100px;
  max-height: 200px;
  font-family: inherit;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
  line-height: 1.5;

  &:focus {
    border-color: #cbd5e1; /* neutral focus */
    box-shadow: none !important; /* remove blue outline glow */
    outline: none !important;
  }

  &:focus-visible {
    outline: none !important;
    box-shadow: none !important;
    border-color: #cbd5e1;
  }

  &::-moz-focus-inner { border: 0; }
  -webkit-tap-highlight-color: transparent;

  &::placeholder {
    color: #9ca3af;
  }
`;

const SendButton = styled.button`
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 9999px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  align-self: flex-end;
  outline: none;
  position: relative;
  background: var(--dbx-primary, #ff3b2e); /* vivid orange-red */
  color: white;
  box-shadow: 0 6px 14px rgba(0,0,0,0.18);
  transition: transform .06s ease-in-out, filter .15s ease-in-out, box-shadow .15s ease-in-out;

  &:hover:not(:disabled) {
    box-shadow: 0 12px 24px rgba(0,0,0,0.26); /* shadow only on hover */
  }

  &:active:not(:disabled) {
    transform: translateY(1px);
    background: var(--dbx-primary, #ff3b2e); /* same color on click */
  }

  /* Remove blue focus ring across browsers */
  &:focus, &:focus-visible {
    outline: none !important;
    box-shadow: 0 6px 14px rgba(0,0,0,0.18);
  }
  &::-moz-focus-inner { border: 0; }
  -webkit-tap-highlight-color: transparent;

  &:disabled {
    opacity: .6;
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

const ChatInterface: React.FC<ChatInterfaceProps> = ({ onSlideUpdate, refreshTick }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('Please provide a pitch deck about you');
  const [isLoading, setIsLoading] = useState(false);
  const [lastMessageCount, setLastMessageCount] = useState(0);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    // While generating, always follow the latest message
    if (isLoading) {
      scrollToBottom();
      return;
    }
    // After completion, only auto-scroll if the user is near the bottom
    const container = messagesEndRef.current?.parentElement;
    const nearBottom = container
      ? (container.scrollHeight - container.scrollTop - container.clientHeight) < 120
      : true;
    if (nearBottom) scrollToBottom();
  }, [messages, isLoading]);

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
        // De-duplicate consecutive identical messages (role + title + content)
        const cleaned: ChatMessage[] = [];
        for (const m of (newMessages as ChatMessage[])) {
          const prev = cleaned[cleaned.length - 1];
          const same = prev && prev.role === m.role && prev.content === m.content && (prev.metadata?.title || '') === (m.metadata?.title || '');
          if (!same) cleaned.push(m);
        }
        setMessages([...cleaned]);
        setLastMessageCount(newMessageCount);
        // Force scroll to bottom right after render to follow live updates
        setTimeout(() => {
          try { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); } catch {}
        }, 0);
        // Refresh slides when ANY new message in this batch is a tool result
        const delta = (newMessages as ChatMessage[]).slice(lastMessageCount);
        const hasToolResult = delta.some(m => !!m?.metadata?.title && /tool result/i.test(m.metadata!.title!));
        if (hasToolResult) onSlideUpdate();
        
        // Stop polling when generation is complete (consider ONLY new messages in this batch)
        const done = delta.some(m => (m.metadata?.title || '').toLowerCase() === 'done' || /all set\b/i.test(m.content || ''));
        if (done && pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        
        setIsLoading(false); // hide spinner once we see progress
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
    pollingRef.current = setInterval(pollForUpdates, 600); // Poll a bit faster to catch staged steps
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

  // One-shot refresh of messages when external refreshTick changes (e.g., user clicked Refresh button)
  useEffect(() => {
    const fetchOnce = async () => {
      try {
        const statusResponse = await axios.get('http://localhost:8000/chat/status/default');
        setMessages([...statusResponse.data.messages]);
        setLastMessageCount(statusResponse.data.message_count);
        setTimeout(() => {
          try { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); } catch {}
        }, 0);
      } catch (err) {
        // ignore
      }
    };
    if (typeof refreshTick === 'number') fetchOnce();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTick]);

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
    let toolGroupId = 0;

    for (let i = 0; i < messages.length; i++) {
      const message = messages[i];
      const isToolMessage = message.metadata?.title && (
        message.metadata.title.includes('Tool') || 
        message.metadata.title.includes('tool')
      );

      if (isToolMessage) {
        // Render each tool message in its own accordion
        groups.push({ id: `tool-group-${toolGroupId++}`, messages: [message], isExpanded: false });
      } else {
        groups.push(message);
      }
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
            <ToolIcon $isExpanded={isExpanded} style={{ color: '#ff3b2e' }}>▶</ToolIcon>
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
            Hi! I'm your AI slide creation assistant. I can create bespoke presentations leveraging our proprietary assets as well as public information from the Internet
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
          placeholder="Please provide a pitch deck about you"
          disabled={isLoading}
        />
        <SendButton onClick={handleSendMessage} disabled={isLoading || !inputValue.trim()} aria-label="Send" className="v-btn v-btn--elevated v-btn--icon bg-primary">
          <span className="v-btn__overlay" />
          <span className="v-btn__underlay" />
          <span className="v-btn__content" data-no-activator="">
            {isLoading ? (
              '⏳'
            ) : (
              <i className="mdi mdi-send v-icon" aria-hidden="true"></i>
            )}
          </span>
        </SendButton>
      </InputContainer>
    </ChatContainer>
  );
};

export default ChatInterface;