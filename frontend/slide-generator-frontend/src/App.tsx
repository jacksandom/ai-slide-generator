import React, { useState, useEffect } from 'react';
import styled from 'styled-components';
import ChatInterface from './components/ChatInterface';
import SlideViewer from './components/SlideViewer';
import './App.css';

const AppContainer = styled.div`
  height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 10px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`;

const ContentWrapper = styled.div`
  flex: 1;
  background: white;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
`;

const Header = styled.div`
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 20px 30px;
  text-align: center;
  flex-shrink: 0;
`;

const Title = styled.h1`
  margin: 0 0 8px 0;
  font-size: 2rem;
  font-weight: 700;
`;

const Subtitle = styled.p`
  margin: 0;
  font-size: 1rem;
  opacity: 0.9;
`;

const MainContent = styled.div`
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 0;
  flex: 1;
  overflow: hidden;

  @media (max-width: 1024px) {
    grid-template-columns: 1fr;
  }
`;

const ChatSection = styled.div`
  padding: 20px;
  border-right: 1px solid #e0e7ff;
  background: #fafbff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;

  @media (max-width: 1024px) {
    border-right: none;
    border-bottom: 1px solid #e0e7ff;
  }
`;

const SlideSection = styled.div`
  padding: 20px;
  background: #f5f5f5;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
`;

const SectionTitle = styled.h2`
  margin: 0 0 15px 0;
  font-size: 1.2rem;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
`;


const App: React.FC = () => {
  const [slidesHtml, setSlidesHtml] = useState<string>('');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const refreshSlides = async () => {
    setIsRefreshing(true);
    try {
      const response = await fetch('http://localhost:8000/slides/html');
      const data = await response.json();
      setSlidesHtml(data.html);
    } catch (error) {
      console.error('Error refreshing slides:', error);
    } finally {
      setIsRefreshing(false);
    }
  };

  const resetSlides = async () => {
    try {
      await fetch('http://localhost:8000/slides/reset', { method: 'POST' });
      await refreshSlides();
    } catch (error) {
      console.error('Error resetting slides:', error);
    }
  };

  const exportSlides = async () => {
    try {
      const response = await fetch('http://localhost:8000/slides/export', { method: 'POST' });
      const data = await response.json();
      alert(data.message);
    } catch (error) {
      console.error('Error exporting slides:', error);
    }
  };

  useEffect(() => {
    refreshSlides();
  }, []);

  return (
    <AppContainer>
      <ContentWrapper>
        <Header>
          <Title>🎨 EY Slide Generator</Title>
          <Subtitle>Create professional slide decks using natural language with AI assistance</Subtitle>
        </Header>
        
        <MainContent>
          <ChatSection>
            <SectionTitle>💬 Slide Creation Assistant</SectionTitle>
            <ChatInterface onSlideUpdate={refreshSlides} />
          </ChatSection>
          
          <SlideSection>
            <SectionTitle>🎯 Generated Slides</SectionTitle>
            <SlideViewer 
              html={slidesHtml} 
              onRefresh={refreshSlides}
              onReset={resetSlides}
              onExport={exportSlides}
              isRefreshing={isRefreshing}
            />
          </SlideSection>
        </MainContent>
      </ContentWrapper>
    </AppContainer>
  );
};

export default App;