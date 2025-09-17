import React, { useEffect, useMemo, useRef, useState } from 'react';
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

const SlideArea = styled.div`
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
`;

const SlideListPanel = styled.div`
  width: 300px;
  min-width: 280px;
  max-width: 340px;
  background: #FFFFFF;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
`;

const SlideList = styled.div`
  overflow-y: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const SlideListItem = styled.button<{ $active?: boolean }>`
  text-align: left;
  border: 1px solid ${props => (props.$active ? '#1A9AFA' : '#e5e7eb')};
  background: ${props => (props.$active ? 'rgba(26, 154, 250, 0.06)' : '#fafafa')};
  color: #111827;
  border-radius: 12px;
  padding: 10px 10px 12px 10px;
  cursor: pointer;
  transition: background-color .15s, border-color .15s;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  &:hover { background: #f3f4f6; }
`;

const SlideIndex = styled.span`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  font-size: 12px;
  font-weight: 600;
  color: #1F2937;
  background: #E5E7EB;
  border-radius: 6px;
`;

const SlideTitleRow = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const SlideTitle = styled.div`
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ThumbBox = styled.div`
  width: 200px;
  height: 112px; /* 16:9 */
  border-radius: 8px;
  overflow: hidden;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  flex: 0 0 auto;
`;

const ThumbFrame = styled.iframe`
  width: 800px;   /* virtual size before scale */
  height: 450px;  /* 16:9 */
  border: 0;
  transform: scale(0.25); /* 800*0.25=200px, 450*0.25=112.5px */
  transform-origin: top left;
  pointer-events: none; /* preview only */
  background: white;
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
  width: 96%;
  max-width: 98%;
  max-height: 90%;
  aspect-ratio: 16/9;
  border: 2px solid #d1d5db;
  border-radius: 12px;
  overflow: hidden;
  background: white;
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
  position: relative;
  
  @media (min-width: 1200px) {
    width: 97%;
    max-height: 92%;
  }
  
  @media (min-width: 1600px) {
    width: 98%;
    max-height: 94%;
  }
  
  @media (max-width: 768px) {
    width: 95%;
    max-height: 88%;
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

const SlideViewer: React.FC<SlideViewerProps> = ({ html, isRefreshing }) => {
  const hasSlides = html && html.trim().length > 0;

  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);

  const slidesMeta = useMemo(() => {
    if (!hasSlides) return [] as { index: number; title: string }[];
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      const sections = Array.from(doc.querySelectorAll('.reveal .slides section'));
      return sections.map((section, i) => {
        const heading = section.querySelector('h1, h2, h3');
        const title = (heading?.textContent || '').trim() || `Slide ${i + 1}`;
        return { index: i, title };
      });
    } catch {
      return [] as { index: number; title: string }[];
    }
  }, [html, hasSlides]);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      const data = e?.data as any;
      if (!data || typeof data !== 'object') return;
      if (data.type === 'SLIDE_CHANGED') {
        if (typeof data.index === 'number') setActiveIndex(data.index);
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [activeIndex]);

  const gotoSlide = (index: number) => {
    setActiveIndex(index);
    try {
      iframeRef.current?.contentWindow?.postMessage({ type: 'NAVIGATE_TO', index }, '*');
    } catch {}
  };

  // When HTML changes, reset to first slide and try to navigate once the frame is ready
  useEffect(() => {
    if (!hasSlides) return;
    setActiveIndex(0);
    // Slight delay to allow iframe to mount its scripts
    const id = window.setTimeout(() => {
      try {
        iframeRef.current?.contentWindow?.postMessage({ type: 'NAVIGATE_TO', index: 0 }, '*');
      } catch {}
    }, 150);
    return () => window.clearTimeout(id);
  }, [html, hasSlides]);

  return (
    <ViewerContainer>
      {hasSlides ? (
        <SlideArea>
          <SlideListPanel>
            <SlideList>
              {slidesMeta.map(s => (
                <SlideListItem key={s.index} $active={s.index === activeIndex} onClick={() => gotoSlide(s.index)}>
                  <SlideTitleRow>
                    <SlideIndex>{s.index + 1}</SlideIndex>
                    <SlideTitle>{s.title}</SlideTitle>
                  </SlideTitleRow>
                  <ThumbBox>
                    <ThumbFrame
                      srcDoc={`<html><head><style>html,body{margin:0;height:100%;overflow:hidden} .reveal{height:100vh} .reveal .slides{height:100%}</style>
<script>try{location.hash='#/${s.index}';}catch(e){}</script></head><body>${html}
<script>(function(){
  var desired=${s.index};
  function go(){
    try{var d=window.__DECK__; if(d && typeof d.slide==='function'){d.slide(desired,0,0); return true;}}catch(e){}
    return false;
  }
  if(!go()){
    var iv=setInterval(function(){ if(go()) clearInterval(iv); }, 100);
    setTimeout(function(){clearInterval(iv);}, 5000);
  }
})();</script>
</body></html>`}
                      sandbox="allow-scripts allow-same-origin"
                    />
                  </ThumbBox>
                </SlideListItem>
              ))}
            </SlideList>
          </SlideListPanel>
          <SlideDisplay>
            <SlideFrame>
              {isRefreshing && (
                <LoadingOverlay>🔄 Refreshing slides...</LoadingOverlay>
              )}
              <IFrame
                ref={iframeRef}
                srcDoc={html}
                title="Generated Slides"
                sandbox="allow-scripts allow-same-origin"
                onLoad={() => {
                  // Nudge navigation on load in case READY message is missed early
                  try {
                    iframeRef.current?.contentWindow?.postMessage({ type: 'NAVIGATE_TO', index: activeIndex }, '*');
                  } catch {}
                }}
              />
            </SlideFrame>
          </SlideDisplay>
        </SlideArea>
      ) : (
        <SlideDisplay>
          <EmptyState>
            <EmptyStateIcon>📊</EmptyStateIcon>
            <EmptyStateText>No slides generated yet</EmptyStateText>
            <EmptyStateSubtext>Start a conversation to create your presentation</EmptyStateSubtext>
          </EmptyState>
        </SlideDisplay>
      )}
    </ViewerContainer>
  );
};

export default SlideViewer;

