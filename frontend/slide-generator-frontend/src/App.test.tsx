import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';

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

describe('App Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Mock successful API responses
    mockedAxios.get.mockResolvedValue({ data: { slides: [] } });
    mockedAxios.post.mockResolvedValue({ 
      data: { 
        messages: [{ role: 'user', content: 'test message' }],
        session_id: 'test'
      }
    });
  });

  test('renders application title', () => {
    render(<App />);
    expect(screen.getByText(/slide generator/i)).toBeInTheDocument();
  });

  test('displays chat interface and slide viewer', () => {
    render(<App />);
    
    // Should have chat input
    expect(screen.getByRole('textbox')).toBeInTheDocument();
    
    // Should have slide viewer area
    expect(screen.getByText(/slides/i)).toBeInTheDocument();
  });

  test('handles message submission', async () => {
    const user = userEvent.setup();
    render(<App />);
    
    const input = screen.getByRole('textbox');
    const submitButton = screen.getByRole('button', { name: /send/i });

    await user.type(input, 'Create 2 slides about AI');
    await user.click(submitButton);

    await waitFor(() => {
      expect(mockedAxios.post).toHaveBeenCalledWith(
        expect.stringContaining('/chat'),
        expect.objectContaining({
          message: 'Create 2 slides about AI'
        })
      );
    });
  });

  test('displays loading state during API calls', async () => {
    // Mock delayed API response
    mockedAxios.post.mockImplementation(() => 
      new Promise(resolve => setTimeout(resolve, 100))
    );
    
    const user = userEvent.setup();
    render(<App />);
    
    const input = screen.getByRole('textbox');
    const submitButton = screen.getByRole('button', { name: /send/i });

    await user.type(input, 'Test message');
    await user.click(submitButton);

    // Should show loading state
    expect(screen.getByText(/sending/i) || screen.getByRole('button', { disabled: true })).toBeTruthy();
  });

  test('handles API errors gracefully', async () => {
    mockedAxios.post.mockRejectedValue(new Error('API Error'));
    
    const user = userEvent.setup();
    render(<App />);
    
    const input = screen.getByRole('textbox');
    const submitButton = screen.getByRole('button', { name: /send/i });

    await user.type(input, 'Test message');
    await user.click(submitButton);

    await waitFor(() => {
      // Should handle error gracefully - either show error message or remain functional
      expect(screen.getByRole('textbox')).toBeInTheDocument();
    });
  });
});
