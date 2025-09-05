import React from 'react';
import styled from 'styled-components';

interface SlideViewerProps {
  html: string;
  onRefresh: () => void;
  onReset: () => void;
  onExport: () => void;
  isRefreshing: boolean;
}

const ViewerContainer = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
`;

const SlideDisplay = styled.div`
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  margin-bottom: 20px;
  position: relative;
  min-height: 0;
`;

const SlideFrame = styled.div`
  width: 100%;
  max-width: 800px;
  aspect-ratio: 16/9;
  border: 2px solid #d1d5db;
  border-radius: 12px;
  overflow: hidden;
  background: white;
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
  position: relative;
`;

const IFrame = styled.iframe`
  width: 100%;
  height: 100%;
  border: none;
  background: white;
`;

const ButtonContainer = styled.div`
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
`;

const Button = styled.button<{ $variant?: 'primary' | 'secondary' | 'danger' }>`
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
  
  ${props => {
    switch (props.$variant) {
      case 'primary':
        return `
          background: #667eea;
          color: white;
          &:hover:not(:disabled) {
            background: #5a67d8;
          }
        `;
      case 'danger':
        return `
          background: #ef4444;
          color: white;
          &:hover:not(:disabled) {
            background: #dc2626;
          }
        `;
      default:
        return `
          background: #f3f4f6;
          color: #374151;
          border: 1px solid #d1d5db;
          &:hover:not(:disabled) {
            background: #e5e7eb;
          }
        `;
    }
  }}

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
`;

const EmptyState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #9ca3af;
  text-align: center;
  padding: 40px;
`;

const EmptyStateIcon = styled.div`
  font-size: 4rem;
  margin-bottom: 16px;
`;

const EmptyStateText = styled.div`
  font-size: 1.1rem;
  margin-bottom: 8px;
`;

const EmptyStateSubtext = styled.div`
  font-size: 0.9rem;
  color: #6b7280;
`;

const LoadingOverlay = styled.div`
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  color: #667eea;
  border-radius: 12px;
  z-index: 10;
`;

const SlideViewer: React.FC<SlideViewerProps> = ({
  html,
  onRefresh,
  onReset,
  onExport,
  isRefreshing
}) => {
  const hasSlides = html && html.trim().length > 0;


  return (
    <ViewerContainer>
      <SlideDisplay>
        {hasSlides ? (
          <SlideFrame>
            {isRefreshing && (
              <LoadingOverlay>
                🔄 Refreshing slides...
              </LoadingOverlay>
            )}
            <IFrame
              srcDoc={html}
              title="Generated Slides"
              sandbox="allow-scripts allow-same-origin"
            />
          </SlideFrame>
        ) : (
          <EmptyState>
            <EmptyStateIcon>📊</EmptyStateIcon>
            <EmptyStateText>No slides generated yet</EmptyStateText>
            <EmptyStateSubtext>Start a conversation to create your presentation</EmptyStateSubtext>
          </EmptyState>
        )}
      </SlideDisplay>
      
      <ButtonContainer>
        <Button onClick={onRefresh} disabled={isRefreshing}>
          🔄 Refresh Slides
        </Button>
        <Button onClick={onReset}>
          🗑️ Reset Slides
        </Button>
        <Button onClick={onExport} $variant="primary">
          💾 Export Slides
        </Button>
      </ButtonContainer>
    </ViewerContainer>
  );
};

export default SlideViewer;

