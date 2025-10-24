import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatInterface from './ChatInterface';

// Mock axios for API calls
jest.mock('axios', () => ({
  get: jest.fn(),
  post: jest.fn(),
  create: jest.fn(() => ({
    get: jest.fn(),
    post: jest.fn(),
  })),
}));

import axios from 'axios';
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('ChatInterface Component', () => {
  const defaultProps = {
    onSlideUpdate: jest.fn(),
    refreshTick: 0
  };

  beforeEach(() => {
    jest.clearAllMocks();
    // Mock successful API responses
    mockedAxios.get.mockResolvedValue({ 
      data: { 
        messages: [],
        session_id: 'test_session'
      }
    });
    mockedAxios.post.mockResolvedValue({
      data: {
        messages: [{ role: 'user', content: 'test message' }],
        session_id: 'test_session'
      }
    });
  });

  test('renders message input and send button', () => {
    render(<ChatInterface {...defaultProps} />);
    expect(screen.getByPlaceholderText(/type your message/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
  });

  test('handles message submission', async () => {
    const user = userEvent.setup();
    const onSlideUpdate = jest.fn();
    
    render(<ChatInterface {...defaultProps} onSlideUpdate={onSlideUpdate} />);
    
    const input = screen.getByPlaceholderText(/type your message/i);
    const sendButton = screen.getByRole('button', { name: /send/i });
    
    await user.type(input, 'Test message');
    await user.click(sendButton);
    
    await waitFor(() => {
      expect(mockedAxios.post).toHaveBeenCalledWith(
        expect.stringContaining('/chat'),
        expect.objectContaining({
          message: 'Test message'
        })
      );
    });
    
    // Should call onSlideUpdate after message
    expect(onSlideUpdate).toHaveBeenCalled();
  });

  test('clears input after successful submission', async () => {
    const user = userEvent.setup();
    render(<ChatInterface {...defaultProps} />);
    
    const input = screen.getByPlaceholderText(/type your message/i);
    const sendButton = screen.getByRole('button', { name: /send/i });
    
    await user.type(input, 'Test message');
    expect(input).toHaveValue('Test message');
    
    await user.click(sendButton);
    
    await waitFor(() => {
      expect(input).toHaveValue('');
    });
  });

  test('displays loading state during message submission', async () => {
    // Mock delayed API response
    mockedAxios.post.mockImplementation(() => 
      new Promise(resolve => setTimeout(() => resolve({
        data: { messages: [], session_id: 'test' }
      }), 100))
    );
    
    const user = userEvent.setup();
    render(<ChatInterface {...defaultProps} />);
    
    const input = screen.getByPlaceholderText(/type your message/i);
    const sendButton = screen.getByRole('button', { name: /send/i });
    
    await user.type(input, 'Test message');
    await user.click(sendButton);
    
    // Should show loading state
    expect(sendButton).toBeDisabled();
  });

  test('displays existing messages on load', async () => {
    const existingMessages = [
      { role: 'user', content: 'Hello' },
      { role: 'assistant', content: 'Hi there! How can I help you create slides today?' }
    ];
    
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        messages: existingMessages,
        session_id: 'test_session'
      }
    });
    
    render(<ChatInterface {...defaultProps} />);
    
    await waitFor(() => {
      expect(screen.getByText('Hello')).toBeInTheDocument();
      expect(screen.getByText(/Hi there/i)).toBeInTheDocument();
    });
  });

  test('handles API errors gracefully', async () => {
    mockedAxios.post.mockRejectedValue(new Error('API Error'));
    
    const user = userEvent.setup();
    render(<ChatInterface {...defaultProps} />);
    
    const input = screen.getByPlaceholderText(/type your message/i);
    const sendButton = screen.getByRole('button', { name: /send/i });
    
    await user.type(input, 'Test message');
    await user.click(sendButton);
    
    await waitFor(() => {
      // Should remain functional after error
      expect(sendButton).not.toBeDisabled();
    });
  });

  test('supports keyboard shortcuts for sending messages', async () => {
    const user = userEvent.setup();
    render(<ChatInterface {...defaultProps} />);
    
    const input = screen.getByPlaceholderText(/type your message/i);
    
    await user.type(input, 'Test message');
    await user.keyboard('{Enter}');
    
    await waitFor(() => {
      expect(mockedAxios.post).toHaveBeenCalled();
    });
  });

  test('prevents submission of empty messages', async () => {
    const user = userEvent.setup();
    render(<ChatInterface {...defaultProps} />);
    
    const sendButton = screen.getByRole('button', { name: /send/i });
    
    await user.click(sendButton);
    
    // Should not make API call for empty message
    expect(mockedAxios.post).not.toHaveBeenCalled();
  });

  test('refreshes messages when refreshTick changes', async () => {
    const { rerender } = render(<ChatInterface {...defaultProps} refreshTick={0} />);
    
    // Initial load
    await waitFor(() => {
      expect(mockedAxios.get).toHaveBeenCalledTimes(1);
    });
    
    // Change refreshTick to trigger refresh
    rerender(<ChatInterface {...defaultProps} refreshTick={1} />);
    
    await waitFor(() => {
      expect(mockedAxios.get).toHaveBeenCalledTimes(2);
    });
  });

  test('displays message metadata when available', async () => {
    const messagesWithMetadata = [
      { 
        role: 'assistant', 
        content: 'Here are your slides',
        metadata: { title: 'Slide Generation Complete' }
      }
    ];
    
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        messages: messagesWithMetadata,
        session_id: 'test_session'
      }
    });
    
    render(<ChatInterface {...defaultProps} />);
    
    await waitFor(() => {
      expect(screen.getByText('Slide Generation Complete')).toBeInTheDocument();
    });
  });

  test('handles markdown content in messages', async () => {
    const markdownMessages = [
      { 
        role: 'assistant', 
        content: '**Bold text** and *italic text*'
      }
    ];
    
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        messages: markdownMessages,
        session_id: 'test_session'
      }
    });
    
    render(<ChatInterface {...defaultProps} />);
    
    await waitFor(() => {
      // Should render markdown (bold/italic elements)
      expect(screen.getByText(/Bold text/)).toBeInTheDocument();
      expect(screen.getByText(/italic text/)).toBeInTheDocument();
    });
  });

  test('auto-scrolls to latest message', async () => {
    const manyMessages = Array.from({ length: 20 }, (_, i) => ({
      role: i % 2 === 0 ? 'user' : 'assistant',
      content: `Message ${i + 1}`
    }));
    
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        messages: manyMessages,
        session_id: 'test_session'
      }
    });
    
    render(<ChatInterface {...defaultProps} />);
    
    await waitFor(() => {
      // Should display the latest message
      expect(screen.getByText('Message 20')).toBeInTheDocument();
    });
  });

  test('maintains session consistency across interactions', async () => {
    const user = userEvent.setup();
    render(<ChatInterface {...defaultProps} />);
    
    // First message
    const input = screen.getByPlaceholderText(/type your message/i);
    await user.type(input, 'First message');
    await user.click(screen.getByRole('button', { name: /send/i }));
    
    await waitFor(() => {
      expect(mockedAxios.post).toHaveBeenCalledWith(
        expect.stringContaining('/chat'),
        expect.objectContaining({
          session_id: expect.any(String)
        })
      );
    });
    
    const firstCallSessionId = mockedAxios.post.mock.calls[0][1].session_id;
    
    // Second message should use same session
    await user.type(input, 'Second message');
    await user.click(screen.getByRole('button', { name: /send/i }));
    
    await waitFor(() => {
      expect(mockedAxios.post).toHaveBeenLastCalledWith(
        expect.stringContaining('/chat'),
        expect.objectContaining({
          session_id: firstCallSessionId
        })
      );
    });
  });
});
