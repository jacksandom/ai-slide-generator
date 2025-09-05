import React, { useState, useEffect } from 'react';
import styled from 'styled-components';
import ChatInterface from './components/ChatInterface';
import SlideViewer from './components/SlideViewer';
import './App.css';

const AppContainer = styled.div`
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
`;

const ContentWrapper = styled.div`
  max-width: 1400px;
  margin: 0 auto;
  background: white;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  overflow: hidden;
`;

const Header = styled.div`
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 30px 40px;
  text-align: center;
`;

const Title = styled.h1`
  margin: 0 0 10px 0;
  font-size: 2.5rem;
  font-weight: 700;
`;

const Subtitle = styled.p`
  margin: 0;
  font-size: 1.2rem;
  opacity: 0.9;
`;

const MainContent = styled.div`
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 0;
  min-height: 600px;

  @media (max-width: 1024px) {
    grid-template-columns: 1fr;
  }
`;

const ChatSection = styled.div`
  padding: 30px;
  border-right: 1px solid #e0e7ff;
  background: #fafbff;

  @media (max-width: 1024px) {
    border-right: none;
    border-bottom: 1px solid #e0e7ff;
  }
`;

const SlideSection = styled.div`
  padding: 30px;
  background: #f5f5f5;
  display: flex;
  flex-direction: column;
  align-items: center;
`;

const SectionTitle = styled.h2`
  margin: 0 0 20px 0;
  font-size: 1.5rem;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 10px;
`;

const TipsSection = styled.div`
  margin-top: 30px;
  padding: 20px;
  background: #f0f4ff;
  border-radius: 8px;
  border-left: 4px solid #667eea;
`;

const TipsTitle = styled.h3`
  margin: 0 0 15px 0;
  color: #374151;
  font-size: 1.1rem;
`;

const TipsList = styled.ul`
  margin: 0;
  padding-left: 20px;
  color: #6b7280;
  line-height: 1.6;
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
            
            <TipsSection>
              <TipsTitle>💡 Tips:</TipsTitle>
              <TipsList>
                <li>Ask for specific slide types: title, agenda, content slides</li>
                <li>Specify the number of slides you want</li>
                <li>Request specific topics or themes</li>
                <li>Use natural language - I'll understand what you need!</li>
              </TipsList>
            </TipsSection>
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