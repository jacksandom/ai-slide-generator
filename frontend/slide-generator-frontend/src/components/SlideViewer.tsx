import React from 'react';
import styled from 'styled-components';

interface SlideViewerProps {
  html: string;
  isRefreshing: boolean;
}

const ViewerContainer = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
  font-weight: 400;
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
  width: 85%;
  max-width: 90%;
  max-height: 80%;
  aspect-ratio: 16/9;
  border: 2px solid #d1d5db;
  border-radius: 12px;
  overflow: hidden;
  background: white;
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
  position: relative;
  
  @media (min-width: 1200px) {
    width: 90%;
    max-height: 75%;
  }
  
  @media (min-width: 1600px) {
    width: 95%;
    max-height: 70%;
  }
  
  @media (max-width: 768px) {
    width: 95%;
    max-height: 85%;
  }
`;

const IFrame = styled.iframe`
  width: 100%;
  height: 100%;
  border: none;
  background: white;
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
  font-weight: 600;
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
    </ViewerContainer>
  );
};

export default SlideViewer;

