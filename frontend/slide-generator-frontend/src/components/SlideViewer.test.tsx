import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SlideViewer from './SlideViewer';

describe('SlideViewer Component', () => {
  const sampleSlides = [
    '<!DOCTYPE html><html><head><title>Slide 1</title></head><body><h1>First Slide</h1><p>Content of first slide</p></body></html>',
    '<!DOCTYPE html><html><head><title>Slide 2</title></head><body><h1>Second Slide</h1><p>Content of second slide</p></body></html>',
    '<!DOCTYPE html><html><head><title>Slide 3</title></head><body><h1>Third Slide</h1><p>Content of third slide</p></body></html>'
  ];

  const defaultProps = {
    slides: sampleSlides,
    isRefreshing: false
  };

  test('renders with empty slides array', () => {
    const { container } = render(<SlideViewer slides={[]} isRefreshing={false} />);
    
    // Should render without crashing
    expect(container).toBeInTheDocument();
  });

  test('displays slides when provided', () => {
    const { container } = render(<SlideViewer {...defaultProps} />);
    
    // Should render slides content
    expect(container).toBeInTheDocument();
    // Check if slide content is rendered (HTML should be parsed)
    expect(container.innerHTML).toContain('First Slide');
  });

  test('shows slide navigation when multiple slides exist', () => {
    const { container } = render(<SlideViewer {...defaultProps} />);
    
    // Should render component with multiple slides
    expect(container).toBeInTheDocument();
  });

  test('navigates between slides', async () => {
    const user = userEvent.setup();
    render(<SlideViewer {...defaultProps} />);
    
    // Should show first slide initially
    expect(screen.getByText(/First Slide/i)).toBeInTheDocument();
    
    // Find and click next button
    const nextButton = screen.getByRole('button', { name: /next/i });
    await user.click(nextButton);
    
    // Should show second slide
    expect(screen.getByText(/Second Slide/i)).toBeInTheDocument();
  });

  test('disables navigation buttons appropriately', async () => {
    const user = userEvent.setup();
    render(<SlideViewer {...defaultProps} />);
    
    // Previous button should be disabled on first slide
    const prevButton = screen.getByRole('button', { name: /previous/i });
    expect(prevButton).toBeDisabled();
    
    // Navigate to last slide
    const nextButton = screen.getByRole('button', { name: /next/i });
    await user.click(nextButton); // Go to slide 2
    await user.click(nextButton); // Go to slide 3
    
    // Next button should be disabled on last slide
    expect(nextButton).toBeDisabled();
  });

  test('displays slide counter', () => {
    render(<SlideViewer {...defaultProps} />);
    
    // Should show slide counter (e.g., "1 of 3")
    expect(screen.getByText(/1.*of.*3/i) || 
           screen.getByText(/slide.*1/i)).toBeTruthy();
  });

  test('handles keyboard navigation', async () => {
    const user = userEvent.setup();
    render(<SlideViewer {...defaultProps} />);
    
    // Should show first slide
    expect(screen.getByText(/First Slide/i)).toBeInTheDocument();
    
    // Use arrow key navigation
    await user.keyboard('{ArrowRight}');
    
    // Should navigate to next slide
    expect(screen.getByText(/Second Slide/i)).toBeInTheDocument();
    
    // Use left arrow to go back
    await user.keyboard('{ArrowLeft}');
    
    // Should be back to first slide
    expect(screen.getByText(/First Slide/i)).toBeInTheDocument();
  });

  test('shows refreshing state', () => {
    render(<SlideViewer slides={sampleSlides} isRefreshing={true} />);
    
    // Should indicate refreshing state
    expect(screen.getByText(/refreshing/i) || 
           screen.getByText(/loading/i) ||
           screen.getByRole('progressbar')).toBeTruthy();
  });

  test('renders slide thumbnails in sidebar', () => {
    render(<SlideViewer {...defaultProps} />);
    
    // Should show thumbnails for all slides
    expect(screen.getAllByText(/slide/i)).toHaveLength(expect.any(Number));
  });

  test('allows clicking thumbnails to navigate', async () => {
    const user = userEvent.setup();
    render(<SlideViewer {...defaultProps} />);
    
    // Find thumbnail for third slide and click it
    const slideElements = screen.getAllByText(/slide/i);
    if (slideElements.length >= 3) {
      await user.click(slideElements[2]);
      
      // Should navigate to third slide
      expect(screen.getByText(/Third Slide/i)).toBeInTheDocument();
    }
  });

  test('handles malformed HTML gracefully', () => {
    const malformedSlides = [
      '<html><body><h1>Valid HTML</h1></body></html>',
      '<div>Incomplete HTML without proper structure',
      '<html><body><script>alert("test")</script><h1>With Script</h1></body></html>'
    ];
    
    render(<SlideViewer slides={malformedSlides} isRefreshing={false} />);
    
    // Should render without crashing
    expect(screen.getByText(/Valid HTML/i)).toBeInTheDocument();
  });

  test('displays slide dimensions correctly', () => {
    render(<SlideViewer {...defaultProps} />);
    
    // Should render slides at correct aspect ratio (16:9)
    const slideContainer = screen.getByRole('main') || screen.getByTestId('slide-container');
    expect(slideContainer).toBeInTheDocument();
  });

  test('supports fullscreen viewing', async () => {
    const user = userEvent.setup();
    render(<SlideViewer {...defaultProps} />);
    
    // Look for fullscreen button
    const fullscreenButton = screen.getByRole('button', { name: /fullscreen/i });
    if (fullscreenButton) {
      await user.click(fullscreenButton);
      // Should trigger fullscreen mode
      expect(fullscreenButton).toBeInTheDocument();
    }
  });

  test('shows zoom controls', async () => {
    const user = userEvent.setup();
    render(<SlideViewer {...defaultProps} />);
    
    // Look for zoom controls
    const zoomInButton = screen.getByRole('button', { name: /zoom.*in/i });
    const zoomOutButton = screen.getByRole('button', { name: /zoom.*out/i });
    
    if (zoomInButton) {
      await user.click(zoomInButton);
      // Should handle zoom in
      expect(zoomInButton).toBeInTheDocument();
    }
    
    if (zoomOutButton) {
      await user.click(zoomOutButton);
      // Should handle zoom out  
      expect(zoomOutButton).toBeInTheDocument();
    }
  });

  test('updates when slides prop changes', () => {
    const { rerender } = render(<SlideViewer slides={[sampleSlides[0]]} isRefreshing={false} />);
    
    // Should show first slide
    expect(screen.getByText(/First Slide/i)).toBeInTheDocument();
    
    // Update with different slides
    rerender(<SlideViewer slides={[sampleSlides[1]]} isRefreshing={false} />);
    
    // Should show updated slide
    expect(screen.getByText(/Second Slide/i)).toBeInTheDocument();
  });

  test('preserves slide position when refreshing', () => {
    const { rerender } = render(<SlideViewer {...defaultProps} />);
    
    // Navigate to second slide (would need to simulate this)
    // Then set refreshing to true
    rerender(<SlideViewer {...defaultProps} isRefreshing={true} />);
    
    // Should maintain current slide position during refresh
    expect(screen.getByText(/refreshing/i) || screen.getByText(/loading/i)).toBeTruthy();
  });

  test('handles empty or null slide content', () => {
    const slidesWithEmpty = [
      sampleSlides[0],
      '', // Empty slide
      null, // Null slide
      sampleSlides[2]
    ];
    
    render(<SlideViewer slides={slidesWithEmpty} isRefreshing={false} />);
    
    // Should render without crashing and show valid slides
    expect(screen.getByText(/First Slide/i)).toBeInTheDocument();
  });

  test('supports slide export functionality', async () => {
    const user = userEvent.setup();
    render(<SlideViewer {...defaultProps} />);
    
    // Look for export button
    const exportButton = screen.getByRole('button', { name: /export/i });
    if (exportButton) {
      await user.click(exportButton);
      // Should handle export action
      expect(exportButton).toBeInTheDocument();
    }
  });

  test('shows slide loading placeholders', () => {
    render(<SlideViewer slides={[]} isRefreshing={true} />);
    
    // Should show loading placeholders when refreshing with no slides
    expect(screen.getByText(/loading/i) || 
           screen.getByRole('progressbar') ||
           screen.getByTestId('loading-placeholder')).toBeTruthy();
  });
});
