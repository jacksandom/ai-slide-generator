"""FastAPI backend for the slide generator application."""

import html
import json
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional
import re
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn
import time

# Import slide generator modules
import sys
sys.path.append(str(Path(__file__).parent.parent / "src"))

from slide_generator.tools import html_slides, uc_tools
from slide_generator.core import chatbot
from slide_generator.config import config
from databricks.sdk import WorkspaceClient

# Initialize Databricks client and components
# Use explicit profile so local dev can auth with the intended workspace
ws = WorkspaceClient(profile='e2-demo', product='slide-generator')

def get_logo_base64():
    """Load the EY-Parthenon logo and encode it as base64 for embedding in HTML."""
    logo_path = Path(__file__).parent.parent / "src" / "slide_generator" / "assets" / "EY-Parthenon_Logo_2021.svg"
    try:
        with open(logo_path, 'rb') as logo_file:
            logo_data = logo_file.read()
            return base64.b64encode(logo_data).decode('utf-8')
    except FileNotFoundError:
        print(f"Warning: Logo file not found at {logo_path}")
        return ""

# Initialize chatbot and conversation state with EY-Parthenon branding
ey_theme = html_slides.SlideTheme(
    bottom_right_logo_url="data:image/svg+xml;base64," + get_logo_base64(),
    bottom_right_logo_height_px=50,
    bottom_right_logo_margin_px=20
)
html_deck = html_slides.HtmlDeck(theme=ey_theme)
chatbot_instance = chatbot.Chatbot(
    html_deck=html_deck,
    llm_endpoint_name=config.llm_endpoint,
    ws=ws,
    tool_dict=uc_tools.UC_tools
)

# Initialize FastAPI app
app = FastAPI(title="Slide Generator API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global conversation state (in production, use proper session management)
conversations: Dict[str, Dict] = {}

# --- Demo static mode -------------------------------------------------------
# When enabled, any user prompt will render a predefined set of static slides
# without calling the LLM or tools. Useful for controlled demos.
DEMO_STATIC_MODE: bool = True

# Demo slide 1 (scoped CSS, no Tailwind dependency)
DEMO_SLIDES: List[str] = [
    """
    <div class=\"demo-title-slide\">
      <style>
        .demo-title-slide { font-family: Arial, sans-serif; color: #2E2E38; }
        .demo-title-slide .slide-container { width: 1280px; height: 720px; position: relative; overflow: hidden; background: #FFFFFF; }
        .demo-title-slide .accent-blue { color: #1A9AFA; }
        .demo-title-slide .accent-line { background-color: #1A9AFA; height: 6px; width: 100px; }
        .demo-title-slide .logo-container { position: absolute; bottom: 40px; right: 40px; width: 180px; }
        .demo-title-slide .title-container { padding-left: 100px; padding-right: 100px; }
        .demo-title-slide .flex { display: flex; }
        .demo-title-slide .flex-col { flex-direction: column; }
        .demo-title-slide .flex-grow { flex: 1 1 auto; }
        .demo-title-slide .justify-center { justify-content: center; }
        .demo-title-slide .w-full { width: 100%; }
        .demo-title-slide .h-2 { height: 8px; }
        .demo-title-slide .h-12 { height: 48px; }
        .demo-title-slide .absolute { position: absolute; }
        .demo-title-slide .left-0 { left: 0; }
        .demo-title-slide .top-0 { top: 0; }
        .demo-title-slide .bottom-0 { bottom: 0; }
        .demo-title-slide .w-12 { width: 48px; }
        .demo-title-slide .relative { position: relative; }
        .demo-title-slide .mb-2 { margin-bottom: 8px; }
        .demo-title-slide .mb-4 { margin-bottom: 16px; }
        .demo-title-slide .mb-6 { margin-bottom: 24px; }
        .demo-title-slide .mb-10 { margin-bottom: 40px; }
        .demo-title-slide .text-5xl { font-size: 40px; line-height: 1.2; }
        .demo-title-slide .text-xl { font-size: 20px; }
        .demo-title-slide .text-lg { font-size: 18px; }
        .demo-title-slide .font-bold { font-weight: 700; }
        .demo-title-slide .max-w-3xl { max-width: 48rem; }
      </style>
      <div class=\"slide-container flex flex-col\">
        <div class=\"w-full h-2\"></div>
        <div class=\"absolute left-0 top-0 bottom-0 w-12\"></div>
        <div class=\"flex flex-col flex-grow justify-center title-container\">
          <div class=\"mb-2\">
            <div class=\"accent-line mb-6\"></div>
            <h1 class=\"text-5xl font-bold mb-4\">Commercial Due Diligence:</h1>
            <h1 class=\"text-5xl font-bold accent-blue mb-10\">Heineken N.V.</h1>
            <p class=\"text-xl mb-10\">Presented by EY-Parthenon | September 2025</p>
            <p class=\"text-lg max-w-3xl\">A comprehensive commercial due diligence report covering business review, market attractiveness, competitive landscape, and growth outlook.</p>
          </div>
        </div>
        <div class=\"w-full h-12 relative\">
          <div class=\"absolute left-0 bottom-0 h-2\" style=\"width:33.333%; background-color:#1A9AFA;\"></div>
        </div>
        <!-- Logo omitted here to avoid duplication; deck theme already renders bottom-right logo -->
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-toc-slide\">
      <style>
        .demo-toc-slide { font-family: Arial, sans-serif; color: #2E2E38; }
        .demo-toc-slide .slide-container { width: 1280px; height: 720px; position: relative; overflow: hidden; background: #FFFFFF; }
        .demo-toc-slide .accent-line { background-color: #1A9AFA; height: 4px; width: 80px; }
        .demo-toc-slide .toc-container { padding-left: 80px; padding-right: 80px; margin-top: 40px; }
        .demo-toc-slide .grid { display: grid; grid-template-columns: 1fr 1fr; column-gap: 32px; row-gap: 8px; }
        .demo-toc-slide .toc-item { display: flex; align-items: center; margin-bottom: 8px; flex-wrap: nowrap; }
        .demo-toc-slide .toc-number { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background-color: #1A9AFA; color: #fff; font-weight: 700; margin-right: 14px; flex: 0 0 auto; }
        .demo-toc-slide .toc-text { font-size: 17px; white-space: nowrap; flex: 1 1 auto; overflow: visible; }
        .demo-toc-slide .text-4xl { font-size: 32px; line-height: 1.25; }
        .demo-toc-slide .font-bold { font-weight: 700; }
        .demo-toc-slide .mb-2 { margin-bottom: 8px; }
        .demo-toc-slide .mb-6 { margin-bottom: 24px; }
        .demo-toc-slide .mb-8 { margin-bottom: 32px; }
        .demo-toc-slide .w-full { width: 100%; }
        .demo-toc-slide .h-2 { height: 8px; }
        .demo-toc-slide .absolute { position: absolute; }
        .demo-toc-slide .left-0 { left: 0; }
        .demo-toc-slide .top-0 { top: 0; }
        .demo-toc-slide .bottom-0 { bottom: 0; }
        .demo-toc-slide .w-12 { width: 48px; }
        .demo-toc-slide .relative { position: relative; }
        .demo-toc-slide .h-12 { height: 32px; }
      </style>
      <div class=\"slide-container\">
        <div class=\"w-full h-2\"></div>
        <div class=\"absolute left-0 top-0 bottom-0 w-12\"></div>
        <div class=\"toc-container\">
          <div class=\"mb-4\">
            <h1 class=\"text-4xl font-bold mb-2\">Table of Contents</h1>
            <div class=\"accent-line mb-4\"></div>
          </div>
          <div class=\"grid\">
            <div class=\"toc-item\"><div class=\"toc-number\">1</div><span class=\"toc-text\">Executive Summary</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">2</div><span class=\"toc-text\">Business Overview &amp; Model</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">3</div><span class=\"toc-text\">Value Chain Position</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">4</div><span class=\"toc-text\">Market Attractiveness</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">5</div><span class=\"toc-text\">Beer Market Segmentation &amp; Outlook</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">6</div><span class=\"toc-text\">Segments Served vs Competitors</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">7</div><span class=\"toc-text\">Key Growth Drivers &amp; Risks</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">8</div><span class=\"toc-text\">Opportunities &amp; Threats</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">9</div><span class=\"toc-text\">Financial Performance Overview</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">10</div><span class=\"toc-text\">Competitive Landscape</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">11</div><span class=\"toc-text\">Competitor Benchmarking</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">12</div><span class=\"toc-text\">Heineken Competitive Position</span></div>
            <div class=\"toc-item\"><div class=\"toc-number\">13</div><span class=\"toc-text\">Opportunities &amp; Threats</span></div>
          </div>
        </div>
        <div class=\"w-full h-12 relative\"><div class=\"absolute left-0 bottom-0 h-2\" style=\"width:33.333%; background-color:#1A9AFA;\"></div></div>
        <!-- Logo omitted to avoid duplication; theme adds the EY mark -->
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-overview-slide\">
      <style>
        .demo-overview-slide { font-family: Arial, sans-serif; color: #2E2E38; }
        .demo-overview-slide .slide-container { width: 1280px; height: 720px; position: relative; overflow: hidden; background: #FFFFFF; }
        .demo-overview-slide .accent-line { background-color: #1A9AFA; height: 4px; width: 80px; }
        .demo-overview-slide .content-container { padding-left: 100px; padding-right: 100px; }
        .demo-overview-slide .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; }
        .demo-overview-slide .text-4xl { font-size: 32px; line-height: 1.25; }
        .demo-overview-slide .text-2xl { font-size: 24px; }
        .demo-overview-slide .font-bold { font-weight: 700; }
        .demo-overview-slide .font-semibold { font-weight: 600; }
        .demo-overview-slide .accent-blue { color: #1A9AFA; }
        .demo-overview-slide .mb-2 { margin-bottom: 8px; }
        .demo-overview-slide .mb-4 { margin-bottom: 16px; }
        .demo-overview-slide .mb-6 { margin-bottom: 24px; }
        .demo-overview-slide .mb-8 { margin-bottom: 32px; }
        .demo-overview-slide .bullet-point { display: flex; margin-bottom: 14px; }
        .demo-overview-slide .bullet-icon { color: #1A9AFA; margin-right: 12px; flex-shrink: 0; margin-top: 4px; }
        .demo-overview-slide .w-full { width: 100%; }
        .demo-overview-slide .h-2 { height: 8px; }
        .demo-overview-slide .absolute { position: absolute; }
        .demo-overview-slide .left-0 { left: 0; }
        .demo-overview-slide .bottom-0 { bottom: 0; }
        .demo-overview-slide .relative { position: relative; }
        .demo-overview-slide .h-12 { height: 48px; }
      </style>
      <div class=\"slide-container\">
        <div class=\"w-full h-2\"></div>
        <div class=\"content-container\">
          <div class=\"mb-6\">
            <h1 class=\"text-4xl font-bold mb-2\">Business Overview &amp; Model</h1>
            <div class=\"accent-line mb-8\"></div>
          </div>
          <div class=\"grid\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Company Profile</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Founded:</span> 1864 in Amsterdam, Netherlands</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Global Presence:</span> Operations in 190+ countries</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Employees:</span> 88,000+ worldwide</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Production:</span> 181 breweries and production facilities</div></div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\" style=\"margin-top:24px\">Core Business</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>Premium beer brewing and distribution</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>Cider production and marketing</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>Beyond-beer beverages (RTDs, hard seltzers)</div></div>
            </div>
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">EverGreen Strategy</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Premiumization:</span> Focus on premium portfolio led by Heineken®</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Digitalization:</span> eB2B platform, data analytics, AI integration</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Sustainability:</span> Brew a Better World initiatives, carbon reduction</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Innovation:</span> Low &amp; no‑alcohol (LONO) leadership, beyond beer</div></div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\" style=\"margin-top:24px\">Key Brands</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Global:</span> Heineken®, Amstel, Desperados, Sol, Tiger</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Regional Leaders:</span> Birra Moretti, Żywiec, Kingfisher, Larue</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Portfolio:</span> 500+ brands across premium, mainstream, craft, and LONO segments</div></div>
            </div>
          </div>
        </div>
        <div class=\"w-full h-12 relative\"><div class=\"absolute left-0 bottom-0 h-2\" style=\"width:33.333%; background-color:#1A9AFA;\"></div></div>
        <!-- Logo omitted to avoid duplication; theme adds the EY mark -->
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-value-slide\">
      <style>
        .demo-value-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-value-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-value-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-value-slide .content-container{padding-left:0;padding-right:0}
        .demo-value-slide .grid{display:grid;grid-template-columns:1fr 1fr;gap:32px}
        .demo-value-slide .text-4xl{font-size:32px;line-height:1.25}
        .demo-value-slide .text-2xl{font-size:24px}
        .demo-value-slide .font-bold{font-weight:700}
        .demo-value-slide .font-semibold{font-weight:600}
        .demo-value-slide .accent-blue{color:#1A9AFA}
        .demo-value-slide .bullet-point{display:flex;margin-bottom:14px}
        .demo-value-slide .bullet-icon{color:#1A9AFA;margin-right:12px;flex-shrink:0;margin-top:4px}
        .demo-value-slide .value-chain-diagram{display:flex;justify-content:space-between;margin:20px 0;padding:10px 0;position:relative}
        .demo-value-slide .connector{position:absolute;top:30px;left:10%;width:80%;height:2px;background:#C4C4CD;z-index:1}
        .demo-value-slide .value-chain-step{text-align:center;position:relative;width:18%;z-index:2}
        .demo-value-slide .step-icon{background:#1A9AFA;color:#fff;width:60px;height:60px;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 10px;font-weight:700}
      </style>
      <div class=\"slide-container\">
        <div class=\"content-container\">
          <div class=\"mb-6\">
            <h1 class=\"text-4xl font-bold mb-2\">Value Chain Position</h1>
            <div class=\"accent-line mb-8\"></div>
          </div>
          <div class=\"value-chain-diagram mb-6\">
            <div class=\"connector\"></div>
            <div class=\"value-chain-step\"><div class=\"step-icon\">A</div><div class=\"font-semibold\">Agriculture</div></div>
            <div class=\"value-chain-step\"><div class=\"step-icon\">B</div><div class=\"font-semibold\">Brewing</div></div>
            <div class=\"value-chain-step\"><div class=\"step-icon\">P</div><div class=\"font-semibold\">Packaging</div></div>
            <div class=\"value-chain-step\"><div class=\"step-icon\">D</div><div class=\"font-semibold\">Distribution</div></div>
            <div class=\"value-chain-step\"><div class=\"step-icon\">C</div><div class=\"font-semibold\">Consumer</div></div>
          </div>
          <div class=\"grid\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Upstream Activities</h2>
              <h3 class=\"font-semibold mb-2\">Agriculture Sourcing</h3>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>Global sourcing for barley, hops and other raw materials</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>Top-3 user of malted barley; key supply from EU, UK, Egypt, Australia</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>Africa: 150k+ smallholder farmers for cassava, sorghum, rice</div></div>
              <h3 class=\"font-semibold mb-2\" style=\"margin-top:20px\">Brewing Operations</h3>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>181 breweries and production facilities worldwide</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>90 breweries connected to the Connected Brewery program</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>Digital transformation improving efficiency and productivity</div></div>
            </div>
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Downstream Activities</h2>
              <h3 class=\"font-semibold mb-2\">Packaging &amp; Logistics</h3>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>98% of packaging recyclable by design (2024)</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>~4,700 logistics service providers</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>Cloud platforms for transport and warehouse management</div></div>
              <h3 class=\"font-semibold mb-2\" style=\"margin-top:20px\">Customer &amp; Consumer</h3>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>Diversified channels: on‑trade, off‑trade, e‑commerce</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>eazle eB2B platform with 670k+ active customers</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div>Direct retail ownership in select markets</div></div>
            </div>
          </div>
        </div>
        <div class=\"w-full\" style=\"height:48px; position:relative;\"><div style=\"position:absolute;left:0;bottom:0;height:8px;width:33%;background:#1A9AFA;\"></div></div>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-market-slide\">
      <style>
        .demo-market-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-market-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-market-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-market-slide .content-container{padding-left:0;padding-right:0}
        .demo-market-slide .grid{display:grid;grid-template-columns:1fr 1fr;gap:32px}
        .demo-market-slide .text-4xl{font-size:32px;line-height:1.25}
        .demo-market-slide .text-2xl{font-size:24px}
        .demo-market-slide .font-bold{font-weight:700}
        .demo-market-slide .font-semibold{font-weight:600}
        .demo-market-slide .accent-blue{color:#1A9AFA}
        .demo-market-slide .bullet-point{display:flex;margin-bottom:14px}
        .demo-market-slide .bullet-icon{color:#1A9AFA;margin-right:12px;flex-shrink:0;margin-top:4px}
        .demo-market-slide .highlight-box{background:#F5F7FA;border-left:4px solid #1A9AFA;padding:15px;margin:15px 0}
      </style>
      <div class=\"slide-container\">
        <div class=\"content-container\">
          <div class=\"mb-6\">
            <h1 class=\"text-4xl font-bold mb-2\">Market Attractiveness</h1>
            <div class=\"accent-line mb-8\"></div>
          </div>
          <div class=\"grid\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Global Market Overview</h2>
              <div class=\"highlight-box\">
                <p class=\"font-semibold\">Global Beer Market Size (2024)</p>
                <p style=\"font-size:22px\">$839 – $851 Billion</p>
                <p style=\"color:#6b7280\">Expected growth to $1.17T by 2032</p>
              </div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Growth Rate:</span> 2–4% CAGR to 2030</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Volume:</span> 1.6% organic growth in 2024</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Characteristics:</span> Mature in EU/NA; high growth APAC &amp; Africa</div></div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\" style=\"margin-top:24px\">Regional Market Attractiveness</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">APAC:</span> Highest potential (8.0% CAGR); strong in Vietnam, India, China</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Africa &amp; ME:</span> Emerging markets; expansion in Nigeria &amp; South Africa</div></div>
            </div>
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Market Trends &amp; Dynamics</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Premiumization:</span> Premium beer 4.5% CAGR vs mainstream 1.2%</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">LONO Growth:</span> Non‑alcoholic beer +9% p.a.</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Craft Evolution:</span> Craft +9.5% CAGR despite consolidation</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Health Focus:</span> Demand for low‑calorie, functional, wellness options</div></div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\" style=\"margin-top:24px\">Consumer Behavior Shifts</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Generational Gap:</span> Gen Z consumes 20% less alcohol; quality over quantity</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Experiential Value:</span> Preference for premium products with distinct stories</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Digital Engagement:</span> Growing D2C and e‑commerce</div></div>
            </div>
          </div>
        </div>
        <div class=\"w-full\" style=\"height:48px; position:relative;\"><div style=\"position:absolute;left:0;bottom:0;height:8px;width:33%;background:#1A9AFA;\"></div></div>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-segment-slide\">
      <style>
        .demo-segment-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-segment-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-segment-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-segment-slide .content-container{padding-left:0;padding-right;margin-bottom:12px}
        .demo-segment-slide .grid2{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:12px}
        .demo-segment-slide .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:8px}
        .demo-segment-slide .text-4xl{font-size:32px;line-height:1.25}
        .demo-segment-slide .text-2xl{font-size:24px}
        .demo-segment-slide .font-bold{font-weight:700}
        .demo-segment-slide .font-semibold{font-weight:600}
        .demo-segment-slide .accent-blue{color:#1A9AFA}
        .demo-segment-slide .segment-card{border-left:4px solid #1A9AFA;padding:12px;background:#f5f5f7}
        .demo-segment-slide .placeholder{height:250px;border:1px dashed #C4C4CD;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#7A7A7A}
        .demo-segment-slide .chart-container{height:250px;position:relative}
      </style>
      <div class=\"slide-container\">
        <div class=\"content-container\">
          <div class=\"mb-6\">
            <h1 class=\"text-4xl font-bold mb-2\">Beer Market Segmentation &amp; Outlook</h1>
            <div class=\"accent-line mb-6\"></div>
          </div>
          <div class=\"grid2\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Market by Segment (2024)</h2>
              <div class=\"chart-container\"><canvas id=\"seg_pie\"></canvas></div>
              <div style=\"font-size:12px;color:#6b7280;text-align:center;margin-top:4px\">Source: Industry analysis</div>
            </div>
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Projected Growth by Segment (CAGR 2024–2028)</h2>
              <div class=\"chart-container\"><canvas id=\"seg_cagr\"></canvas></div>
              <div style=\"font-size:12px;color:#6b7280;text-align:center;margin-top:4px\">Source: IWSR, EY‑Parthenon analysis</div>
            </div>
          </div>
          <div class=\"grid3\">
            <div class=\"segment-card\"><h3 class=\"font-bold\">By Price Point</h3><div><b>Premium:</b> 26%</div><div><b>Mainstream:</b> 62%</div><div><b>Economy:</b> 12%</div></div>
            <div class=\"segment-card\"><h3 class=\"font-bold\">By Product Type</h3><div><b>Lager:</b> 76%</div><div><b>Ale:</b> 12%</div><div><b>Specialty/Craft:</b> 9%</div><div><b>LONO:</b> 3%</div></div>
            <div class=\"segment-card\"><h3 class=\"font-bold\">By Geography</h3><div><b>APAC:</b> 34%</div><div><b>Europe:</b> 28%</div><div><b>Americas:</b> 26%</div><div><b>Africa &amp; ME:</b> 12%</div></div>
          </div>
        </div>
        <div class=\"w-full\" style=\"height:48px; position:relative;\"><div style=\"position:absolute;left:0;bottom:0;height:8px;width:33%;background:#1A9AFA;\"></div></div>
        <script>
          try {
            // Pie: market share by price point (matches card values below)
            const pieCtx = document.getElementById('seg_pie') && document.getElementById('seg_pie').getContext('2d');
            if (pieCtx && window.Chart) {
              new Chart(pieCtx, {
                type: 'pie',
                data: {
                  labels: ['Premium', 'Mainstream', 'Economy', 'Craft/Specialty'],
                  datasets: [{
                    data: [26, 62, 12, 9],
                    backgroundColor: ['#1A9AFA', '#B4E2FF', '#747480', '#3DB5FF'],
                    borderWidth: 0
                  }]
                },
                options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10, font: { size: 11 } } } }
                }
              });
            }
            // Bar: CAGR by segment
            const barCtx = document.getElementById('seg_cagr') && document.getElementById('seg_cagr').getContext('2d');
            if (barCtx && window.Chart) {
              new Chart(barCtx, {
                type: 'bar',
                data: {
                  labels: ['Premium', 'Craft', 'LONO', 'Mainstream'],
                  datasets: [{
                    label: 'CAGR %',
                    data: [4.5, 9.0, 8.0, 1.2],
                    backgroundColor: ['#1A9AFA', '#3DB5FF', '#7ECCFF', '#B4E2FF'],
                    borderWidth: 0
                  }]
                },
                options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  scales: { y: { beginAtZero: true, max: 10, title: { display: true, text: 'CAGR %' } } },
                  plugins: { legend: { display: false } }
                }
              });
            }
          } catch (e) {}
        </script>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-competitors-slide\">
      <style>
        .demo-competitors-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-competitors-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-competitors-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-competitors-slide .content-container{padding-left:0;padding-right:0;margin-bottom:12px}
        .demo-competitors-slide .text-4xl{font-size:32px;line-height:1.25}
        .demo-competitors-slide .text-2xl{font-size:24px}
        .demo-competitors-slide .font-bold{font-weight:700}
        .demo-competitors-slide .font-semibold{font-weight:600}
        .demo-competitors-slide .accent-blue{color:#1A9AFA}
        .demo-competitors-slide .data-table{width:100%;border-collapse:collapse}
        .demo-competitors-slide .data-table th{background:#f5f5f7;padding:8px;text-align:left;font-weight:700;border-bottom:2px solid #1A9AFA}
        .demo-competitors-slide .data-table td{padding:8px;border-bottom:1px solid #e5e5e5}
        .demo-competitors-slide .coverage-strong{color:#1A9AFA;font-weight:700}
        .demo-competitors-slide .coverage-moderate{color:#3DB5FF}
        .demo-competitors-slide .coverage-limited{color:#B4E2FF}
        .demo-competitors-slide .placeholder{height:250px;border:1px dashed #C4C4CD;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#7A7A7A}
        .demo-competitors-slide .chart-container{height:140px;position:relative}
      </style>
      <div class=\"slide-container\">
        <div class=\"content-container\">
          <div class=\"mb-4\">
            <h1 class=\"text-4xl font-bold mb-2\">Segments Served vs. Competitors</h1>
            <div class=\"accent-line mb-4\"></div>
          </div>
          <div class=\"mb-4\">
            <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Competitive Positioning by Market Segment</h2>
            <table class=\"data-table\">
              <thead>
                <tr><th style=\"width:20%\">Segment</th><th>Heineken</th><th>AB InBev</th><th>Carlsberg</th><th>Molson Coors</th></tr>
              </thead>
              <tbody>
                <tr><td class=\"font-semibold\">Premium</td><td class=\"coverage-strong\">●●● Strong</td><td class=\"coverage-strong\">●●● Strong</td><td class=\"coverage-moderate\">●● Moderate</td><td class=\"coverage-moderate\">●● Moderate</td></tr>
                <tr><td class=\"font-semibold\">Mainstream</td><td class=\"coverage-moderate\">●● Moderate</td><td class=\"coverage-strong\">●●● Strong</td><td class=\"coverage-strong\">●●● Strong</td><td class=\"coverage-strong\">●●● Strong</td></tr>
                <tr><td class=\"font-semibold\">Economy</td><td class=\"coverage-limited\">● Limited</td><td class=\"coverage-strong\">●●● Strong</td><td class=\"coverage-moderate\">●● Moderate</td><td class=\"coverage-moderate\">●● Moderate</td></tr>
                <tr><td class=\"font-semibold\">Craft/Specialty</td><td class=\"coverage-moderate\">●● Moderate</td><td class=\"coverage-strong\">●●● Strong</td><td class=\"coverage-limited\">● Limited</td><td class=\"coverage-moderate\">●● Moderate</td></tr>
                <tr><td class=\"font-semibold\">LONO</td><td class=\"coverage-strong\">●●● Strong</td><td class=\"coverage-moderate\">●● Moderate</td><td class=\"coverage-moderate\">●● Moderate</td><td class=\"coverage-limited\">● Limited</td></tr>
              </tbody>
            </table>
          </div>
          <div>
            <h2 class=\"text-2xl font-semibold accent-blue mb-3\">Regional Market Strength</h2>
            <div class=\"chart-container\"><canvas id=\"seg_strength_radar\"></canvas></div>
            <div style=\"display:flex;justify-content:space-between;align-items:center;margin-top:4px\">
              <div style=\"font-size:12px;color:#6b7280\">Source: Market share data, annual reports, EY‑Parthenon analysis</div>
              <div id=\"chart-legend\" style=\"font-size:10px;color:#6b7280\"></div>
            </div>
          </div>
          <div style=\"margin-top:8px;font-size:14px\"><b>Key Insight:</b> Heineken leads in premium and LONO across Europe and Africa; AB InBev dominates in the Americas; Carlsberg is strong in Asia.</div>
        </div>
        <div class=\"w-full\" style=\"height:48px; position:relative;\"><div style=\"position:absolute;left:0;bottom:0;height:8px;width:33%;background:#1A9AFA;\"></div></div>
        <script>
          try {
            const rctx = document.getElementById('seg_strength_radar') && document.getElementById('seg_strength_radar').getContext('2d');
            if (rctx && window.Chart) {
              new Chart(rctx, {
                type: 'radar',
                data: {
                  labels: ['Europe', 'Americas', 'APAC', 'Africa & ME'],
                  datasets: [
                    { label:'Heineken', data:[9, 7, 8, 8], borderColor:'#1A9AFA', backgroundColor:'rgba(26,154,250,0.15)', pointBackgroundColor:'#1A9AFA' },
                    { label:'AB InBev', data:[8, 10, 8, 7], borderColor:'#3DB5FF', backgroundColor:'rgba(61,181,255,0.12)', pointBackgroundColor:'#3DB5FF' },
                    { label:'Carlsberg', data:[8, 6, 8, 5], borderColor:'#7ECCFF', backgroundColor:'rgba(126,204,255,0.12)', pointBackgroundColor:'#7ECCFF' },
                    { label:'Molson Coors', data:[7, 8, 4, 4], borderColor:'#B4E2FF', backgroundColor:'rgba(180,226,255,0.12)', pointBackgroundColor:'#B4E2FF' }
                  ]
                },
                options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  scales: { r: { suggestedMin: 0, suggestedMax: 10, grid: { color:'#e5e7eb' }, angleLines: { color:'#e5e7eb' }, ticks: { display:false } } },
                  plugins: { legend: { display: false } },
                  onComplete: function() {
                    const legendContainer = document.getElementById('chart-legend');
                    if (legendContainer) {
                      const datasets = this.data.datasets;
                      const legendItems = datasets.map((dataset, index) => {
                        const color = dataset.borderColor;
                        const label = dataset.label;
                        return `<span style=\"color:${color};margin-right:8px\">●</span>${label}`;
                      }).join(' ');
                      legendContainer.innerHTML = legendItems;
                    }
                  }
                }
              });
            }
          } catch (e) {}
        </script>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-growth-slide\">
      <style>
        .demo-growth-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-growth-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-growth-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-growth-slide .content-container{padding-left:0;padding-right:0}
        .demo-growth-slide .grid{display:grid;grid-template-columns:1fr 1fr;gap:32px}
        .demo-growth-slide .text-4xl{font-size:32px;line-height:1.25}
        .demo-growth-slide .text-2xl{font-size:24px}
        .demo-growth-slide .font-bold{font-weight:700}
        .demo-growth-slide .font-semibold{font-weight:600}
        .demo-growth-slide .accent-blue{color:#1A9AFA}
        .demo-growth-slide .bullet-point{display:flex;margin-bottom:14px}
        .demo-growth-slide .bullet-icon{color:#1A9AFA;margin-right:12px;flex-shrink:0;margin-top:4px}
        .demo-growth-slide .bullet-icon.gray{color:#747480}
      </style>
      <div class=\"slide-container\">
        <div class=\"content-container\">
          <div class=\"mb-6\">
            <h1 class=\"text-4xl font-bold mb-2\">Key Growth Drivers &amp; Risks</h1>
            <div class=\"accent-line mb-8\"></div>
          </div>
          <div class=\"grid\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Growth Drivers</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Premiumization</span><div style=\"font-size:15px;color:#747480;margin-left:4px;margin-top:4px\">Consumers trading up to premium and super‑premium beer globally, driving higher margin sales</div></div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Emerging Markets Expansion</span><div style=\"font-size:15px;color:#747480;margin-left:4px;margin-top:4px\">Strong growth potential in Asia‑Pacific (Vietnam, India) and Africa (Nigeria, South Africa)</div></div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">LONO Category Leadership</span><div style=\"font-size:15px;color:#747480;margin-left:4px;margin-top:4px\">Low &amp; No‑Alcohol segment growing ~8% CAGR with Heineken® 0.0 as category leader</div></div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Strong Brand Portfolio</span><div style=\"font-size:15px;color:#747480;margin-left:4px;margin-top:4px\">500+ brands across segments with global distribution and marketing excellence</div></div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><span class=\"font-semibold\">Beyond Beer Innovation</span><div style=\"font-size:15px;color:#747480;margin-left:4px;margin-top:4px\">Expansion into RTDs and hard seltzers aligned to evolving Gen Z preferences</div></div></div>
            </div>
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Risks &amp; Challenges</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon gray\">•</div><div><span class=\"font-semibold\">Regulatory Pressure</span><div style=\"font-size:15px;color:#747480;margin-left:4px;margin-top:4px\">Increasing taxes, marketing restrictions, and health warnings globally</div></div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon gray\">•</div><div><span class=\"font-semibold\">Shifting Consumer Preferences</span><div style=\"font-size:15px;color:#747480;margin-left:4px;margin-top:4px\">Gen Z drinking ~20% less alcohol; greater health consciousness</div></div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon gray\">•</div><div><span class=\"font-semibold\">Supply Chain Volatility</span><div style=\"font-size:15px;color:#747480;margin-left:4px;margin-top:4px\">Raw material inflation (barley, aluminum), energy costs, logistics</div></div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon gray\">•</div><div><span class=\"font-semibold\">Craft &amp; Local Competition</span><div style=\"font-size:15px;color:#747480;margin-left:4px;margin-top:4px\">Fragmented competitors capturing premium niches</div></div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon gray\">•</div><div><span class=\"font-semibold\">Climate Change Impact</span><div style=\"font-size:15px;color:#747480;margin-left:4px;margin-top:4px\">Water scarcity and agricultural yield challenges for barley &amp; hops</div></div></div>
            </div>
          </div>
        </div>
        <div class=\"w-full\" style=\"height:48px; position:relative;\"><div style=\"position:absolute;left:0;bottom:0;height:8px;width:33%;background:#1A9AFA;\"></div></div>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-financial-slide\">
      <style>
        .demo-financial-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-financial-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-financial-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-financial-slide .content-container{padding-left:0;padding-right:0;margin-top:0;margin-bottom:0}
        .demo-financial-slide .text-4xl{font-size:28px;line-height:1.2}
        .demo-financial-slide .text-xl{font-size:18px}
        .demo-financial-slide .font-bold{font-weight:700}
        .demo-financial-slide .font-semibold{font-weight:600}
        .demo-financial-slide .accent-blue{color:#1A9AFA}
        .demo-financial-slide .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px}
        .demo-financial-slide .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:8px}
        .demo-financial-slide .card{border-left:4px solid #1A9AFA;padding:8px;background:#f5f5f7}
        .demo-financial-slide .pos{color:#10B981}
        .demo-financial-slide .neg{color:#EF4444}
        .demo-financial-slide .placeholder{height:160px;border:1px dashed #C4C4CD;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#7A7A7A}
        .demo-financial-slide .chart-container{height:160px;position:relative}
        .demo-financial-slide .data-table{width:100%;border-collapse:collapse}
        .demo-financial-slide .data-table th{background:#f5f5f7;padding:6px;text-align:left;font-weight:700;border-bottom:2px solid #1A9AFA;font-size:12px}
        .demo-financial-slide .data-table td{padding:6px;border-bottom:1px solid #e5e5e5;font-size:12px}
      </style>
      <div class=\"slide-container\">
        <div class=\"content-container\">
          <div class=\"mb-3\">
            <h1 class=\"text-4xl font-bold mb-1\">Financial Performance Overview</h1>
            <div class=\"accent-line mb-3\"></div>
          </div>
          <div class=\"grid3\">
            <div class=\"card\"><h3 class=\"font-bold\" style=\"font-size:14px\">Net Revenue (beia)</h3><div class=\"font-semibold\" style=\"font-size:18px\">€29.96B</div><div class=\"neg\" style=\"font-size:12px\">-1.1% YoY</div><div style=\"font-size:12px;margin-top:2px\">Organic growth: +5.0%</div></div>
            <div class=\"card\"><h3 class=\"font-bold\" style=\"font-size:14px\">Operating Profit (beia)</h3><div class=\"font-semibold\" style=\"font-size:18px\">€4.51B</div><div class=\"pos\" style=\"font-size:12px\">+1.6% YoY</div><div style=\"font-size:12px;margin-top:2px\">Margin: 15.1% (+40bps)</div></div>
            <div class=\"card\"><h3 class=\"font-bold\" style=\"font-size:14px\">Net Profit (beia)</h3><div class=\"font-semibold\" style=\"font-size:18px\">€2.74B</div><div class=\"pos\" style=\"font-size:12px\">+4.1% YoY</div><div style=\"font-size:12px;margin-top:2px\">FCF: €3.06B (+73.8%)</div></div>
          </div>
          <div class=\"grid2\">
            <div>
              <h2 class=\"text-xl font-semibold accent-blue mb-2\">Financial Performance (€B)</h2>
              <div class=\"chart-container\"><canvas id=\"fp_bar\"></canvas></div>
              <div style=\"font-size:10px;color:#6b7280;text-align:center;margin-top:2px\">Source: Heineken Annual Report 2024</div>
            </div>
            <div>
              <h2 class=\"text-xl font-semibold accent-blue mb-2\">Revenue by Region (2024)</h2>
              <div class=\"chart-container\"><canvas id=\"fp_doughnut\"></canvas></div>
              <div style=\"font-size:10px;color:#6b7280;text-align:center;margin-top:2px\">Source: Heineken Annual Report 2024</div>
            </div>
          </div>
          <div>
            <h2 class=\"text-xl font-semibold accent-blue mb-2\">Regional Performance Highlights</h2>
            <table class=\"data-table\">
              <thead>
                <tr><th style=\"width:25%\">Region</th><th style=\"width:25%\">Revenue Growth</th><th style=\"width:25%\">Op. Profit Margin</th><th style=\"width:25%\">Key Markets</th></tr>
              </thead>
              <tbody>
                <tr><td>Europe</td><td class=\"neg\">-2.3%</td><td>12.4%</td><td>UK, Netherlands, Spain</td></tr>
                <tr><td>Americas</td><td class=\"pos\">+3.6%</td><td>16.2%</td><td>Brazil, Mexico, USA</td></tr>
                <tr><td>Asia Pacific</td><td class=\"pos\">+6.8%</td><td>17.3%</td><td>Vietnam, China, India</td></tr>
                <tr><td>Africa &amp; Middle East</td><td class=\"pos\">+8.2%</td><td>14.5%</td><td>Nigeria, South Africa, Ethiopia</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class=\"w-full\" style=\"height:48px; position:relative;\"><div style=\"position:absolute;left:0;bottom:0;height:8px;width:33%;background:#1A9AFA;\"></div></div>
        <script>
          try {
            const barCtx = document.getElementById('fp_bar') && document.getElementById('fp_bar').getContext('2d');
            if (barCtx && window.Chart) {
              new Chart(barCtx, {
                type: 'bar',
                data: {
                  labels: ['Revenue', 'Op Profit', 'Net Profit', 'FCF'],
                  datasets: [
                    { label: '2023', data: [29.0, 4.2, 2.6, 1.76], backgroundColor: '#7ECCFF', borderWidth: 0 },
                    { label: '2024', data: [29.96, 4.51, 2.74, 3.06], backgroundColor: '#1A9AFA', borderWidth: 0 }
                  ]
                },
                options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  scales: { y: { beginAtZero: true, title: { display: false } } },
                  plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10, font: { size: 11 } } } }
                }
              });
            }
            const doughCtx = document.getElementById('fp_doughnut') && document.getElementById('fp_doughnut').getContext('2d');
            if (doughCtx && window.Chart) {
              new Chart(doughCtx, {
                type: 'doughnut',
                data: {
                  labels: ['Europe', 'Americas', 'APAC', 'Africa & ME'],
                  datasets: [{
                    data: [31, 29, 27, 13],
                    backgroundColor: ['#1A9AFA', '#3DB5FF', '#7ECCFF', '#B4E2FF'],
                    borderWidth: 0
                  }]
                },
                options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10, font: { size: 11 } } } }
                }
              });
            }
          } catch (e) {}
        </script>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-competitive-slide\">
      <style>
        .demo-competitive-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-competitive-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-competitive-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-competitive-slide .content-container{padding-left:0;padding-right:0;margin-top:0;margin-bottom:0}
        .demo-competitive-slide .text-4xl{font-size:28px;line-height:1.2}
        .demo-competitive-slide .text-2xl{font-size:20px}
        .demo-competitive-slide .text-xl{font-size:16px}
        .demo-competitive-slide .font-bold{font-weight:700}
        .demo-competitive-slide .font-semibold{font-weight:600}
        .demo-competitive-slide .accent-blue{color:#1A9AFA}
        .demo-competitive-slide .grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
        .demo-competitive-slide .comp-card{border-left:3px solid #1A9AFA;padding-left:12px;margin-bottom:10px}
        .demo-competitive-slide .bar-row{display:flex;align-items:center;margin-bottom:6px}
        .demo-competitive-slide .bar-label{width:25%;font-weight:600;font-size:14px}
        .demo-competitive-slide .bar-wrap{width:75%}
        .demo-competitive-slide .bar{height:20px;background:#1A9AFA;border-radius:4px;display:flex;align-items:center;justify-content:flex-end;padding-right:8px;color:#fff;font-weight:700;font-size:12px}
      </style>
      <div class=\"slide-container\">
        <div class=\"content-container\">
          <div class=\"mb-3\">
            <h1 class=\"text-4xl font-bold mb-1\">Competitive Landscape</h1>
            <div class=\"accent-line mb-3\"></div>
          </div>
          <div class=\"mb-4\">
            <h2 class=\"text-2xl font-semibold accent-blue mb-3\">Global Market Share Distribution 2024</h2>
            <div>
              <div class=\"bar-row\"><div class=\"bar-label\">AB InBev</div><div class=\"bar-wrap\"><div class=\"bar\" style=\"width:26.4%\">26.4%</div></div></div>
              <div class=\"bar-row\"><div class=\"bar-label\">Heineken</div><div class=\"bar-wrap\"><div class=\"bar\" style=\"width:12.1%\">12.1%</div></div></div>
              <div class=\"bar-row\"><div class=\"bar-label\">Carlsberg</div><div class=\"bar-wrap\"><div class=\"bar\" style=\"width:6.9%\">6.9%</div></div></div>
              <div class=\"bar-row\"><div class=\"bar-label\">Molson Coors</div><div class=\"bar-wrap\"><div class=\"bar\" style=\"width:4.3%\">4.3%</div></div></div>
              <div class=\"bar-row\"><div class=\"bar-label\">Other</div><div class=\"bar-wrap\"><div class=\"bar\" style=\"width:50.3%\">50.3%</div></div></div>
            </div>
          </div>
          <div class=\"grid2\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-2\">Key Global Competitors</h2>
              <div class=\"comp-card\"><h3 class=\"text-xl font-semibold\">AB InBev</h3><p style=\"margin-bottom:4px;font-size:13px\"><b>Key Brands:</b> Budweiser, Stella Artois, Corona, Beck's</p><p style=\"font-size:13px\"><b>Regional Strength:</b> Americas, Europe, Asia‑Pacific</p></div>
              <div class=\"comp-card\"><h3 class=\"text-xl font-semibold\">Carlsberg Group</h3><p style=\"margin-bottom:4px;font-size:13px\"><b>Key Brands:</b> Carlsberg, Tuborg, Kronenbourg 1664</p><p style=\"font-size:13px\"><b>Regional Strength:</b> Northern/Eastern Europe, Asia</p></div>
              <div class=\"comp-card\"><h3 class=\"text-xl font-semibold\">Molson Coors</h3><p style=\"margin-bottom:4px;font-size:13px\"><b>Key Brands:</b> Coors Light, Miller Lite, Blue Moon</p><p style=\"font-size:13px\"><b>Regional Strength:</b> North America, UK</p></div>
            </div>
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-2\">Regional Competitors</h2>
              <div class=\"comp-card\"><h3 class=\"text-xl font-semibold\">Asahi Group Holdings</h3><p style=\"margin-bottom:4px;font-size:13px\"><b>Key Brands:</b> Asahi Super Dry, Peroni, Grolsch</p><p style=\"font-size:13px\"><b>Regional Strength:</b> Japan, Oceania, Europe</p></div>
              <div class=\"comp-card\"><h3 class=\"text-xl font-semibold\">Tsingtao Brewery</h3><p style=\"margin-bottom:4px;font-size:13px\"><b>Key Brands:</b> Tsingtao</p><p style=\"font-size:13px\"><b>Regional Strength:</b> China, East Asia</p></div>
              <div class=\"comp-card\"><h3 class=\"text-xl font-semibold\">Constellation Brands</h3><p style=\"margin-bottom:4px;font-size:13px\"><b>Key Brands:</b> Modelo, Corona (US rights), Pacifico</p><p style=\"font-size:13px\"><b>Regional Strength:</b> North America</p></div>
            </div>
          </div>
        </div>
        <div class=\"w-full\" style=\"height:48px; position:relative;\"><div style=\"position:absolute;left:0;bottom:0;height:8px;width:33%;background:#1A9AFA;\"></div></div>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-exec-slide\">
      <style>
        .demo-exec-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-exec-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-exec-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-exec-slide .content-container{padding-left:0;padding-right:0}
        .demo-exec-slide .text-4xl{font-size:32px;line-height:1.25}
        .demo-exec-slide .text-2xl{font-size:24px}
        .demo-exec-slide .font-bold{font-weight:700}
        .demo-exec-slide .font-semibold{font-weight:600}
        .demo-exec-slide .accent-blue{color:#1A9AFA}
        .demo-exec-slide .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
        .demo-exec-slide .bullet-point{display:flex;margin-bottom:10px}
        .demo-exec-slide .bullet-icon{color:#1A9AFA;margin-right:8px;flex-shrink:0;margin-top:4px}
        .demo-exec-slide .highlight-box{background:#F5F5F7;border-left:4px solid #1A9AFA;padding:15px;margin:10px 0}
      </style>
      <div class=\"slide-container\">
        <div class=\"content-container\">
          <div class=\"mb-4\">
            <h1 class=\"text-4xl font-bold mb-2\">Executive Summary</h1>
            <div class=\"accent-line mb-4\"></div>
          </div>
          <div class=\"grid2\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Investment Highlights</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Strong Premium Position:</b> #2 global brewer (~12% share) led by Heineken®</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Market Leadership:</b> Leaders in Vietnam, Brazil, Mexico; expanding in India</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Innovation Pipeline:</b> LONO leadership (Heineken® 0.0) and beyond‑beer expansion</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Financial Strength:</b> 15.1% Op margin, €3.06B FCF (+73.8%), productivity gains</div></div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-3\" style=\"margin-top:16px\">Market Assessment</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Global Market:</b> ~€839B (2024), 2–4% CAGR to 2030, premium‑led growth</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Regional:</b> APAC (6–8%) &amp; Africa (5–7%) offset mature Europe (1–2%)</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Category:</b> Premium 4.5% CAGR, Craft 9%, LONO 8% vs mainstream 1.2%</div></div>
            </div>
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Key Risks &amp; Opportunities</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Risk – Consumption:</b> Gen Z ~20% lower alcohol intake; preference shifts</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Risk – Input Costs:</b> Raw materials &amp; energy volatility</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Risk – Regulation:</b> Stricter marketing, labeling, sustainability compliance</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Opportunity – LONO:</b> Scale leadership position as growth accelerates</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Opportunity – Digital:</b> eB2B scaling (€13B GMV, 670k+ customers)</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Opportunity – APAC:</b> Premiumization in Vietnam, China, India</div></div>
              <div class=\"highlight-box\" style=\"margin-top:16px\">
                <h3 class=\"font-bold\" style=\"margin-bottom:6px\">Commercial Assessment</h3>
                <p style=\"margin-bottom:8px\">Well‑positioned for sustained growth via premium portfolio, innovation, and EM footprint; EverGreen strategy aligns to market trends while lifting efficiency.</p>
                <p class=\"font-semibold\">5‑Year Base Case: ~4% CAGR; margin expansion potential via digitalization and productivity.</p>
              </div>
            </div>
          </div>
        </div>
        <div class=\"w-full\" style=\"height:32px; position:relative;\"><div style=\"position:absolute;left:0;bottom:0;height:8px;width:33%;background:#1A9AFA;\"></div></div>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-benchmark-slide\">
      <style>
        .demo-benchmark-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-benchmark-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-benchmark-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-benchmark-slide .content-container{padding-left:0;padding-right:0;margin-top:0;margin-bottom:0}
        .demo-benchmark-slide .text-4xl{font-size:28px;line-height:1.2}
        .demo-benchmark-slide .text-2xl{font-size:20px}
        .demo-benchmark-slide .font-bold{font-weight:700}
        .demo-benchmark-slide .font-semibold{font-weight:600}
        .demo-benchmark-slide .accent-blue{color:#1A9AFA}
        .demo-benchmark-slide .table{width:100%;border-collapse:collapse}
        .demo-benchmark-slide .table th{background:#f5f5f7;padding:8px;text-align:left;font-weight:700;border-bottom:2px solid #1A9AFA;font-size:12px}
        .demo-benchmark-slide .table td{padding:8px;border-bottom:1px solid #e5e5e5;font-size:12px}
        .demo-benchmark-slide .hl{color:#1A9AFA;font-weight:700}
        .demo-benchmark-slide .hk{background:#f0f8ff}
        .demo-benchmark-slide .placeholder{height:180px;border:1px dashed #C4C4CD;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#7A7A7A}
        .demo-benchmark-slide .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
        .demo-benchmark-slide .card{border-left:4px solid #1A9AFA;padding:8px;background:#f5f5f7}
        .demo-benchmark-slide .chart-container{height:180px;position:relative}
      </style>
      <div class=\"slide-container\">
        <div class=\"content-container\">
          <div class=\"mb-3\">
            <h1 class=\"text-4xl font-bold mb-1\">Competitor Benchmarking</h1>
            <div class=\"accent-line mb-3\"></div>
          </div>
          <div class=\"mb-4\">
            <table class=\"table\">
              <thead>
                <tr>
                  <th style=\"width:20%\">Company</th>
                  <th style=\"width:15%\">2024 Revenue (€B)</th>
                  <th style=\"width:15%\">Operating Margin</th>
                  <th style=\"width:15%\">Global Mkt Share</th>
                  <th style=\"width:20%\">Key Markets</th>
                  <th style=\"width:15%\">LONO Portfolio</th>
                </tr>
              </thead>
              <tbody>
                <tr class=\"hk\"><td class=\"font-bold\">Heineken</td><td>36.0</td><td class=\"hl\">15.1%</td><td>12.0%</td><td>Europe, APAC, Americas</td><td class=\"hl\">Strong</td></tr>
                <tr><td class=\"font-bold\">AB InBev</td><td class=\"hl\">58.3</td><td>14.8%</td><td class=\"hl\">26.4%</td><td>Americas, APAC, Europe</td><td>Medium</td></tr>
                <tr><td class=\"font-bold\">Carlsberg</td><td>12.1</td><td>14.2%</td><td>7.0%</td><td>Europe, Asia</td><td>Medium</td></tr>
                <tr><td class=\"font-bold\">Molson Coors</td><td>10.9</td><td>10.3%</td><td>4.5%</td><td>North America, Europe</td><td>Limited</td></tr>
                <tr><td class=\"font-bold\">Asahi Group</td><td>16.2</td><td>11.7%</td><td>3.1%</td><td>Japan, Europe, Australia</td><td>Limited</td></tr>
              </tbody>
            </table>
          </div>
          <div class=\"grid2\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-2\">Competitive Position Comparison</h2>
              <div class=\"chart-container\"><canvas id=\"bench_radar\"></canvas></div>
              <div style=\"font-size:10px;color:#6b7280;text-align:center;margin-top:4px\">Source: Company reports, industry analysis, EY‑Parthenon analysis (2024–2025)</div>
            </div>
            <div class=\"card\">
              <h3 class=\"font-bold\" style=\"margin-bottom:4px;font-size:14px\">Key Insights</h3>
              <div style=\"font-size:12px\">Heineken maintains strong operating margins and premium positioning; AB InBev leads in revenue and share; Heineken shows momentum in EM and LONO.</div>
            </div>
          </div>
        </div>
        <div style=\"height:48px;position:relative\"><div style=\"position:absolute;left:0;bottom:0;height:8px;width:33%;background:#1A9AFA\"></div></div>
        <script>
          try {
            const radarCtx = document.getElementById('bench_radar') && document.getElementById('bench_radar').getContext('2d');
            if (radarCtx && window.Chart) {
              new Chart(radarCtx, {
                type: 'radar',
                data: {
                  labels: ['Premium Strength', 'Mainstream Scale', 'LONO Portfolio', 'Regional Breadth', 'Profitability'],
                  datasets: [
                    { label: 'Heineken', data: [8, 6, 9, 8, 8], borderColor: '#1A9AFA', backgroundColor: 'rgba(26,154,250,0.15)', pointBackgroundColor: '#1A9AFA' },
                    { label: 'AB InBev', data: [8, 10, 7, 9, 8], borderColor: '#3DB5FF', backgroundColor: 'rgba(61,181,255,0.12)', pointBackgroundColor: '#3DB5FF' },
                    { label: 'Carlsberg', data: [7, 6, 6, 7, 7], borderColor: '#7ECCFF', backgroundColor: 'rgba(126,204,255,0.12)', pointBackgroundColor: '#7ECCFF' }
                  ]
                },
                options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  scales: { r: { suggestedMin: 0, suggestedMax: 10, grid: { color: '#e5e7eb' }, angleLines: { color: '#e5e7eb' }, ticks: { display: false } } },
                  plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10, font: { size: 11 } } } }
                }
              });
            }
          } catch (e) {}
        </script>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-competitive-position-slide\">
      <style>
        .demo-competitive-position-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-competitive-position-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-competitive-position-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-competitive-position-slide .content-container{padding-left:0;padding-right:0}
        .demo-competitive-position-slide .text-4xl{font-size:32px;line-height:1.25}
        .demo-competitive-position-slide .text-2xl{font-size:24px}
        .demo-competitive-position-slide .font-bold{font-weight:700}
        .demo-competitive-position-slide .font-semibold{font-weight:600}
        .demo-competitive-position-slide .accent-blue{color:#1A9AFA}
        .demo-competitive-position-slide .grid2{display:grid;grid-template-columns:1fr 1fr;gap:32px}
        .demo-competitive-position-slide .bullet-point{display:flex;margin-bottom:14px}
        .demo-competitive-position-slide .bullet-icon{color:#1A9AFA;margin-right:12px;flex-shrink:0;margin-top:4px}
        .demo-competitive-position-slide .metric-box{background:#F5F7FA;border-left:4px solid #1A9AFA;padding:16px;margin:10px 0}
        .demo-competitive-position-slide .left-blue{border-left:4px solid #1A9AFA;padding-left:12px}
      </style>
      <div class=\"slide-container\">
        <div class=\"content-container\">
          <div class=\"mb-6\">
            <h1 class=\"text-4xl font-bold mb-2\">Heineken Competitive Position</h1>
            <div class=\"accent-line mb-8\"></div>
          </div>
          <div class=\"grid2\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Strengths</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Global Brand Power:</b> Heineken® in 190+ countries</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Premium Leadership:</b> Heineken®, Birra Moretti, Tiger growing</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>LONO Innovation:</b> Heineken® 0.0 in 117 markets</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Marketing Excellence:</b> F1 and UEFA partnerships</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Digital:</b> eazle eB2B with 670k+ customers, ~€13B GMV</div></div>
              <div class=\"metric-box\">
                <div class=\"font-semibold accent-blue\" style=\"margin-bottom:6px\">Market Position</div>
                <div>World's 2nd largest brewer</div>
                <div style=\"font-size:14px;color:#6b7280\">~12% global market share; 240.7M hl (2024)</div>
              </div>
            </div>
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Challenges</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Scale Gap:</b> ~45% of AB InBev scale</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>European Exposure:</b> Mature/slow‑growth footprint</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Input Cost Volatility:</b> Commodities and energy</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div><b>Gen Z Patterns:</b> Lower alcohol consumption</div></div>
              <h2 class=\"text-2xl font-semibold accent-blue\" style=\"margin:20px 0 12px\">Competitive Advantages</h2>
              <div class=\"left-blue\" style=\"margin-bottom:10px\"><div class=\"font-semibold\" style=\"margin-bottom:4px\">Premium Portfolio Strength</div><div style=\"font-size:14px\">Premium brands outgrew market in 2024</div></div>
              <div class=\"left-blue\" style=\"margin-bottom:10px\"><div class=\"font-semibold\" style=\"margin-bottom:4px\">Sustainability Leadership</div><div style=\"font-size:14px\">34% Scope 1/2 reduction; 84% renewable electricity</div></div>
              <div class=\"left-blue\"><div class=\"font-semibold\" style=\"margin-bottom:4px\">Beyond Beer Innovation</div><div style=\"font-size:14px\">Adjacencies aligned to evolving preferences</div></div>
            </div>
          </div>
        </div>
        <div style=\"height:48px;position:relative\"><div style=\"position:absolute;left:0;bottom:0;height:8px;width:33%;background:#1A9AFA\"></div></div>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-opportunities-threats-slide\">
      <style>
        .demo-opportunities-threats-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-opportunities-threats-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-opportunities-threats-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-opportunities-threats-slide .content-container{padding-left:0;padding-right:0}
        .demo-opportunities-threats-slide .text-4xl{font-size:32px;line-height:1.25}
        .demo-opportunities-threats-slide .text-2xl{font-size:24px}
        .demo-opportunities-threats-slide .font-bold{font-weight:700}
        .demo-opportunities-threats-slide .font-semibold{font-weight:600}
        .demo-opportunities-threats-slide .accent-blue{color:#1A9AFA}
        .demo-opportunities-threats-slide .grid2{display:grid;grid-template-columns:1fr 1fr;gap:32px}
        .demo-opportunities-threats-slide .bullet-point{display:flex;margin-bottom:14px}
        .demo-opportunities-threats-slide .bullet-icon{color:#1A9AFA;margin-right:12px;flex-shrink:0;margin-top:4px}
        .demo-opportunities-threats-slide .opp{border-left:4px solid #1A9AFA;padding:15px;background:#F5F9FE;margin-bottom:10px}
        .demo-opportunities-threats-slide .threat{border-left:4px solid #FF6B6B;padding:15px;background:#FEF5F5;margin-bottom:10px}
      </style>
      <div class=\"slide-container\">
        <div class=\"content-container\">
          <div class=\"mb-6\">
            <h1 class=\"text-4xl font-bold mb-2\">Opportunities &amp; Threats</h1>
            <div class=\"accent-line mb-8\"></div>
          </div>
          <div class=\"grid2\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-6\">Strategic Opportunities</h2>
              <div class=\"opp\"><div class=\"font-semibold\" style=\"margin-bottom:6px\">Premium Growth in Emerging Markets</div><div>Expand premium brands in Vietnam, India, and Africa</div></div>
              <div class=\"opp\"><div class=\"font-semibold\" style=\"margin-bottom:6px\">LONO Segment Acceleration</div><div>Leverage Heineken® 0.0 leadership (~8% CAGR)</div></div>
              <div class=\"opp\"><div class=\"font-semibold\" style=\"margin-bottom:6px\">Digital &amp; D2C</div><div>Scale eazle eB2B to deepen relationships and data</div></div>
              <div class=\"opp\"><div class=\"font-semibold\" style=\"margin-bottom:6px\">Beyond Beer Innovation</div><div>Grow Tiger Soju, STËLZ, and RTDs for Gen Z</div></div>
            </div>
            <div>
              <h2 class=\"text-2xl font-semibold\" style=\"color:#ef4444;margin-bottom:24px\">Market Threats</h2>
              <div class=\"threat\"><div class=\"font-semibold\" style=\"margin-bottom:6px\">Regulatory Pressure</div><div>Tighter rules and taxes in key markets</div></div>
              <div class=\"threat\"><div class=\"font-semibold\" style=\"margin-bottom:6px\">Changing Consumption</div><div>Gen Z ~20% lower alcohol consumption</div></div>
              <div class=\"threat\"><div class=\"font-semibold\" style=\"margin-bottom:6px\">Competitive Intensity</div><div>Craft fragmentation and global rival expansion</div></div>
              <div class=\"threat\"><div class=\"font-semibold\" style=\"margin-bottom:6px\">Macroeconomic Headwinds</div><div>Inflation; input costs (barley, aluminum)</div></div>
            </div>
          </div>
          <div style=\"margin-top:24px;border-top:1px solid #e5e7eb;padding-top:16px\">
            <h3 class=\"text-xl font-semibold\" style=\"margin-bottom:8px\">Strategic Outlook</h3>
            <div>Premium leadership and LONO innovation provide resilience; success hinges on balancing core investments and new offerings aligned to emerging trends.</div>
          </div>
        </div>
        <div style=\"height:48px;position:relative\"><div style=\"position:absolute;left:0;bottom:0;height:8px;width:33%;background:#1A9AFA\"></div></div>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-5yr-forecast-slide\">
      <style>
        .demo-5yr-forecast-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-5yr-forecast-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-5yr-forecast-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-5yr-forecast-slide .content-container{padding-left:0;padding-right:0}
        .demo-5yr-forecast-slide .text-4xl{font-size:32px;line-height:1.25}
        .demo-5yr-forecast-slide .text-2xl{font-size:24px}
        .demo-5yr-forecast-slide .font-bold{font-weight:700}
        .demo-5yr-forecast-slide .font-semibold{font-weight:600}
        .demo-5yr-forecast-slide .accent-blue{color:#1A9AFA}
        .demo-5yr-forecast-slide .grid2{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:12px}
        .demo-5yr-forecast-slide .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:8px}
        .demo-5yr-forecast-slide .segment-card{border-left:4px solid #1A9AFA;padding:12px;background:#f5f5f7}
        .demo-5yr-forecast-slide .chart-container{height:250px;width:100%;position:relative}
      </style>
      <div class=\"slide-container bg-white flex flex-col\">
        <div class=\"w-full h-2 bg-white\"></div>
        <div class=\"absolute left-0 top-0 bottom-0 w-12 bg-white\"></div>
        <div class=\"flex flex-col content-container mt-12 mb-8\">
          <div class=\"mb-6\">
            <h1 class=\"text-4xl font-bold mb-2\">5-Year Segment-Based Growth Forecast</h1>
            <div class=\"accent-line mb-6\"></div>
          </div>
          <div class=\"grid2\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">Growth Projection by Segment (2025-2030)</h2>
              <div class=\"chart-container mb-2\">
                <canvas id=\"segmentChart\"></canvas>
              </div>
              <div style=\"font-size:12px;color:#6b7280;text-align:center\">Source: Industry analysis, EY-Parthenon forecasts</div>
            </div>
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-4\">CAGR by Region (2025-2030)</h2>
              <div class=\"chart-container mb-2\">
                <canvas id=\"regionChart\"></canvas>
              </div>
              <div style=\"font-size:12px;color:#6b7280;text-align:center\">Source: Market forecasts, IWSR data, EY-Parthenon analysis</div>
            </div>
          </div>
          <div class=\"grid3 mt-2\">
            <div class=\"segment-card\">
              <h3 class=\"font-bold mb-1\">Premium Segment</h3>
              <div><span class=\"data-highlight\">Overall CAGR:</span> 4.5%</div>
              <div><span class=\"data-highlight\">Top Market:</span> APAC (6.8%)</div>
              <div><span class=\"data-highlight\">Key Drivers:</span> Premiumization, craft crossover</div>
            </div>
            <div class=\"segment-card\">
              <h3 class=\"font-bold mb-1\">LONO &amp; Specialty</h3>
              <div><span class=\"data-highlight\">LONO CAGR:</span> 8.0%</div>
              <div><span class=\"data-highlight\">Craft CAGR:</span> 9.0%</div>
              <div><span class=\"data-highlight\">Top Region:</span> Europe (10.2%)</div>
            </div>
            <div class=\"segment-card\">
              <h3 class=\"font-bold mb-1\">Mainstream &amp; Economy</h3>
              <div><span class=\"data-highlight\">Mainstream CAGR:</span> 1.2%</div>
              <div><span class=\"data-highlight\">Economy CAGR:</span> 0.8%</div>
              <div><span class=\"data-highlight\">Leading Growth:</span> Africa &amp; ME (2.4%)</div>
            </div>
          </div>
        </div>
        <div class=\"w-full h-12 bg-white mt-auto relative\">
          <div class=\"absolute left-0 bottom-0 h-2\" style=\"width:33.333%; background-color:#1A9AFA;\"></div>
        </div>
      </div>
      <script>
        try {
          const segmentCtx = document.getElementById('segmentChart') && document.getElementById('segmentChart').getContext('2d');
          if (segmentCtx && window.Chart) {
            new Chart(segmentCtx, {
              type: 'line',
              data: { labels: ['2025','2026','2027','2028','2029','2030'], datasets: [
                { label:'Premium', data:[100,105,110,114,119,124], borderColor:'#1A9AFA', backgroundColor:'rgba(26,154,250,0.1)', borderWidth:2, fill:true, tension:0.3 },
                { label:'Craft/Specialty', data:[100,109,119,129,141,154], borderColor:'#3DB5FF', backgroundColor:'rgba(61,181,255,0.1)', borderWidth:2, fill:true, tension:0.3 },
                { label:'LONO', data:[100,108,117,126,136,147], borderColor:'#7ECCFF', backgroundColor:'rgba(126,204,255,0.1)', borderWidth:2, fill:true, tension:0.3 },
                { label:'Mainstream', data:[100,101,102,104,105,106], borderColor:'#B4E2FF', backgroundColor:'rgba(180,226,255,0.1)', borderWidth:2, fill:true, tension:0.3 },
                { label:'Economy', data:[100,101,101,102,103,104], borderColor:'#747480', backgroundColor:'rgba(116,116,128,0.1)', borderWidth:2, fill:true, tension:0.3 }
              ]},
              options: { responsive:true, maintainAspectRatio:false, scales:{ y:{ title:{ display:true, text:'Index (2025=100)' }, min:95 } }, plugins:{ legend:{ position:'bottom', labels:{ boxWidth:12, padding:10, font:{ size:11 } } } } }
            });
          }
          const regionCtx = document.getElementById('regionChart') && document.getElementById('regionChart').getContext('2d');
          if (regionCtx && window.Chart) {
            new Chart(regionCtx, {
              type: 'bar',
              data: { labels:['Europe','Americas','Asia Pacific','Africa & ME'], datasets:[
                { label:'Premium', data:[3.8,4.2,6.8,5.2], backgroundColor:'#1A9AFA', borderWidth:0 },
                { label:'Craft', data:[10.2,8.5,8.8,7.0], backgroundColor:'#3DB5FF', borderWidth:0 },
                { label:'LONO', data:[9.8,7.2,6.5,4.5], backgroundColor:'#7ECCFF', borderWidth:0 },
                { label:'Mainstream', data:[0.8,1.1,1.8,2.4], backgroundColor:'#B4E2FF', borderWidth:0 }
              ]},
              options: { responsive:true, maintainAspectRatio:false, scales:{ y:{ beginAtZero:true, title:{ display:true, text:'CAGR %' }, max:12 }, x:{ stacked:false } }, plugins:{ legend:{ position:'bottom', labels:{ boxWidth:12, padding:10, font:{ size:11 } } } } }
            });
          }
        } catch (e) {}
      </script>
    </div>
    """
    ,
    """
    <div class=\"demo-scenarios-slide\">
      <style>
        .demo-scenarios-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-scenarios-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-scenarios-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-scenarios-slide .content-container{padding-left:0;padding-right:0;margin-top:0;margin-bottom:0}
        .demo-scenarios-slide .text-4xl{font-size:28px;line-height:1.2}
        .demo-scenarios-slide .font-bold{font-weight:700}
        .demo-scenarios-slide .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
        .demo-scenarios-slide .scenario-card{border-left:4px solid #1A9AFA;padding:6px;background:#f5f5f7;height:100%}
        .demo-scenarios-slide .scenario-bull{border-left-color:#00A550}
        .demo-scenarios-slide .scenario-bear{border-left-color:#FF6B6B}
        .demo-scenarios-slide .bull-highlight{color:#00A550;font-weight:700}
        .demo-scenarios-slide .bear-highlight{color:#FF6B6B;font-weight:700}
        .demo-scenarios-slide .base-highlight{color:#1A9AFA;font-weight:700}
        .demo-scenarios-slide .chart-container{height:140px;position:relative}
        .demo-scenarios-slide .data-table{width:100%;border-collapse:collapse}
        .demo-scenarios-slide .data-table th{background:#f5f5f7;padding:4px;text-align:left;font-weight:700;border-bottom:2px solid #1A9AFA;font-size:11px}
        .demo-scenarios-slide .data-table td{padding:4px;border-bottom:1px solid #e5e5e5;font-size:11px}
      </style>
      <div class=\"slide-container bg-white flex flex-col\">
        <div class=\"w-full h-2 bg-white\"></div>
        <div class=\"absolute left-0 top-0 bottom-0 w-12 bg-white\"></div>
        <div class=\"flex flex-col content-container mt-4 mb-2\">
          <div class=\"mb-2\">
            <h1 class=\"text-4xl font-bold mb-1\">Bear, Base, and Bull Case Scenarios</h1>
            <div class=\"accent-line mb-2\"></div>
          </div>
          <div class=\"mb-3\">
            <div class=\"chart-container\" style=\"height:140px\"><canvas id=\"scenarioChart\"></canvas></div>
            <div style=\"font-size:9px;color:#6b7280;text-align:center;margin-top:2px\">Heineken 5-Year Growth Scenarios (CAGR 2025-2030)</div>
          </div>
          <div class=\"grid3 mb-3\">
            <div>
              <div class=\"scenario-card scenario-bear\">
                <h3 class=\"font-bold mb-1\" style=\"font-size:13px\">Bear Case: <span class=\"bear-highlight\">2.1% CAGR</span></h3>
                <ul style=\"margin-left:10px;list-style:disc;font-size:11px\">
                  <li>Increased regulation & taxation</li>
                  <li>Accelerated decline in EU beer consumption</li>
                  <li>Economic pressure in emerging markets</li>
                  <li>Gen Z shift away from alcohol</li>
                </ul>
              </div>
            </div>
            <div>
              <div class=\"scenario-card\">
                <h3 class=\"font-bold mb-1\" style=\"font-size:13px\">Base Case: <span class=\"base-highlight\">4.0% CAGR</span></h3>
                <ul style=\"margin-left:10px;list-style:disc;font-size:11px\">
                  <li>Moderate economic growth globally</li>
                  <li>Premiumization continues</li>
                  <li>Steady LONO expansion</li>
                  <li>Stable share in key regions</li>
                </ul>
              </div>
            </div>
            <div>
              <div class=\"scenario-card scenario-bull\">
                <h3 class=\"font-bold mb-1\" style=\"font-size:13px\">Bull Case: <span class=\"bull-highlight\">6.2% CAGR</span></h3>
                <ul style=\"margin-left:10px;list-style:disc;font-size:11px\">
                  <li>Strong APAC & Africa expansion</li>
                  <li>LONO leadership & market creation</li>
                  <li>Beyond-beer innovations</li>
                  <li>Digital transformation acceleration</li>
                </ul>
              </div>
            </div>
          </div>
          <div>
            <h3 class=\"font-bold mb-1\" style=\"font-size:13px\">CAGR by Segment (2025-2030)</h3>
            <table class=\"data-table\" style=\"width:100%;border-collapse:collapse\">
              <thead>
                <tr>
                  <th>Segment</th>
                  <th style=\"text-align:right\"><span class=\"bear-highlight\">Bear Case</span></th>
                  <th style=\"text-align:right\"><span class=\"base-highlight\">Base Case</span></th>
                  <th style=\"text-align:right\"><span class=\"bull-highlight\">Bull Case</span></th>
                </tr>
              </thead>
              <tbody>
                <tr><td>Premium Beer</td><td style=\"text-align:right\">3.2%</td><td style=\"text-align:right\">4.5%</td><td style=\"text-align:right\">5.8%</td></tr>
                <tr><td>Mainstream Beer</td><td style=\"text-align:right\">0.8%</td><td style=\"text-align:right\">1.2%</td><td style=\"text-align:right\">2.4%</td></tr>
                <tr><td>Craft/Specialty</td><td style=\"text-align:right\">6.5%</td><td style=\"text-align:right\">9.0%</td><td style=\"text-align:right\">12.0%</td></tr>
                <tr><td>LONO (Low/No Alcohol)</td><td style=\"text-align:right\">5.5%</td><td style=\"text-align:right\">8.0%</td><td style=\"text-align:right\">12.5%</td></tr>
                <tr><td>Beyond Beer</td><td style=\"text-align:right\">4.5%</td><td style=\"text-align:right\">7.5%</td><td style=\"text-align:right\">11.0%</td></tr>
                <tr style=\"font-weight:700\"><td>Overall Growth</td><td style=\"text-align:right;color:#FF6B6B\">2.1%</td><td style=\"text-align:right;color:#1A9AFA\">4.0%</td><td style=\"text-align:right;color:#00A550\">6.2%</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class=\"w-full h-12 bg-white mt-auto relative\"><div class=\"absolute left-0 bottom-0 h-2\" style=\"width:33.333%; background-color:#1A9AFA;\"></div></div>
        <script>
          try {
            const sctx = document.getElementById('scenarioChart') && document.getElementById('scenarioChart').getContext('2d');
            if (sctx && window.Chart) {
              new Chart(sctx, {
                type: 'bar',
                data: { labels:['Premium Beer','Mainstream Beer','Craft/Specialty','LONO','Beyond Beer','Overall Growth'], datasets:[
                  { label:'Bear Case', data:[3.2,0.8,6.5,5.5,4.5,2.1], backgroundColor:'#FF6B6B', borderWidth:0 },
                  { label:'Base Case', data:[4.5,1.2,9.0,8.0,7.5,4.0], backgroundColor:'#1A9AFA', borderWidth:0 },
                  { label:'Bull Case', data:[5.8,2.4,12.0,12.5,11.0,6.2], backgroundColor:'#00A550', borderWidth:0 }
                ]},
                options: { responsive:true, maintainAspectRatio:false, scales:{ y:{ beginAtZero:true, max:14, title:{ display:true, text:'CAGR (%)' } } }, plugins:{ legend:{ position:'top', labels:{ boxWidth:12, padding:10, font:{ size:11 } } } } }
              });
            }
          } catch (e) {}
        </script>
      </div>
    </div>
    """
    ,
    """
    <div class=\"demo-conclusion-slide\">
      <style>
        .demo-conclusion-slide{font-family:Arial,sans-serif;color:#2E2E38}
        .demo-conclusion-slide .slide-container{width:1280px;height:720px;position:relative;overflow:hidden;background:#FFFFFF}
        .demo-conclusion-slide .accent-line{background:#1A9AFA;height:4px;width:80px}
        .demo-conclusion-slide .content-container{padding-left:0;padding-right:0;margin-top:0;margin-bottom:0}
        .demo-conclusion-slide .text-4xl{font-size:28px;line-height:1.2}
        .demo-conclusion-slide .text-2xl{font-size:20px}
        .demo-conclusion-slide .font-bold{font-weight:700}
        .demo-conclusion-slide .font-semibold{font-weight:600}
        .demo-conclusion-slide .accent-blue{color:#1A9AFA}
        .demo-conclusion-slide .grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
        .demo-conclusion-slide .bullet-point{display:flex;margin-bottom:6px}
        .demo-conclusion-slide .bullet-icon{color:#1A9AFA;margin-right:6px;flex-shrink:0;margin-top:1px}
        .demo-conclusion-slide .highlight-box{background:#F5F7FA;border-left:4px solid #1A9AFA;padding:8px;margin:6px 0}
      </style>
      <div class=\"slide-container bg-white flex flex-col\">
        <div class=\"w-full h-2 bg-white\"></div>
        <div class=\"absolute left-0 top-0 bottom-0 w-12 bg-white\"></div>
        <div class=\"flex flex-col content-container\">
          <div class=\"mb-3\">
            <h1 class=\"text-4xl font-bold mb-1\">Conclusion &amp; Recommendations</h1>
            <div class=\"accent-line mb-3\"></div>
          </div>
          <div class=\"grid2\">
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-2\">Strategic Assessment</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div style=\"font-size:12px\"><span class=\"font-semibold\">Strong Market Position:</span> World's second-largest brewer with leading premium portfolio</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div style=\"font-size:12px\"><span class=\"font-semibold\">Premium Leader:</span> Dominant position provides pricing power and margin resilience</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div style=\"font-size:12px\"><span class=\"font-semibold\">Innovation Pipeline:</span> Early mover in LONO category with successful growth drivers</div></div>
              <div class=\"highlight-box\">
                <p class=\"font-semibold mb-1\" style=\"font-size:13px\">EY-Parthenon Assessment</p>
                <p style=\"font-size:11px\">Heineken demonstrates strong fundamentals with clear growth strategy and execution capabilities.</p>
              </div>
            </div>
            <div>
              <h2 class=\"text-2xl font-semibold accent-blue mb-2\">Key Recommendations</h2>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div style=\"font-size:12px\"><span class=\"font-semibold\">Accelerate APAC Expansion:</span> Invest in high-growth markets like Vietnam, India</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div style=\"font-size:12px\"><span class=\"font-semibold\">Beyond Beer Portfolio:</span> Expand innovation in adjacent categories</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div style=\"font-size:12px\"><span class=\"font-semibold\">Digital Transformation:</span> Continue investing in eB2B platforms and AI-driven operations</div></div>
              <div class=\"bullet-point\"><div class=\"bullet-icon\">•</div><div style=\"font-size:12px\"><span class=\"font-semibold\">LONO Leadership:</span> Leverage first-mover advantage in non-alcoholic portfolio</div></div>
            </div>
          </div>
          <div class=\"mt-3\">
            <h2 class=\"text-2xl font-semibold accent-blue mb-2\">Investment View</h2>
            <div class=\"grid2\" style=\"gap:12px\">
              <div class=\"highlight-box\" style=\"text-align:center\">
                <div class=\"text-2xl font-bold accent-blue mb-1\">4-8%</div>
                <div class=\"text-sm font-semibold\">Operating Profit Growth (2025)</div>
              </div>
              <div class=\"highlight-box\" style=\"text-align:center\">
                <div class=\"text-2xl font-bold accent-blue mb-1\">15.1%</div>
                <div class=\"text-sm font-semibold\">Operating Margin (2024)</div>
              </div>
            </div>
            <div class=\"highlight-box\" style=\"margin-top:8px;text-align:center\">
              <p class=\"font-semibold mb-1\" style=\"font-size:13px\">EY-Parthenon Investment Recommendation</p>
              <p class=\"font-semibold\" style=\"font-size:16px;color:#1A9AFA\">BUY / HOLD</p>
              <p class=\"mt-1\" style=\"font-size:11px\">Long-term value creation opportunity</p>
            </div>
          </div>
        </div>
        <div class=\"w-full h-12 bg-white mt-auto relative\"><div class=\"absolute left-0 bottom-0 h-2\" style=\"width:33.333%; background-color:#1A9AFA;\"></div></div>
      </div>
    </div>
    """
]

def _append_api_message(session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    conv = get_or_create_conversation(session_id)
    conv["api_conversation"].append(ChatMessage(role=role, content=content, metadata=metadata))

def _build_toc_html_from_deck(deck: html_slides.HtmlDeck) -> str:
    # Extract titles from slides after index 1 (exclude Title and TOC)
    titles: List[str] = []
    for idx, s in enumerate(deck._slides):  # type: ignore[attr-defined]
        if idx <= 1:
            continue
        title_text = getattr(s, "title", "") or ""
        if not title_text:
            content_html = getattr(s, "content", "") or ""
            m = re.search(r"<h[12][^>]*>(.*?)</h[12]>", content_html, re.IGNORECASE | re.DOTALL)
            if m:
                title_text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if title_text:
            titles.append(title_text)

    # Build two-column alternating layout (1 left, 2 right, 3 left ...)
    items_html: List[str] = []
    for i, title in enumerate(titles, start=1):
        number_html = f"<div class=\"toc-number\">{i}</div>"
        text_html = f"<span class=\"toc-text\">{title}</span>"
        items_html.append(f"<div class=\"toc-item\">{number_html}{text_html}</div>")

    # Split into two columns sequentially (1..mid left, mid+1..end right)
    mid = (len(items_html) + 1) // 2
    col_left = items_html[:mid]
    col_right = items_html[mid:]

    left_html = "".join(col_left)
    right_html = "".join(col_right)

    # Emit HTML/CSS matching the user's TOC style exactly (dynamic content only)
    toc_html = f"""
    <div class=\"slide-container bg-white flex flex-col\">
      <style>
        body {{ margin:0; padding:0; background:#FFFFFF; color:#2E2E38; font-family: Arial, sans-serif; }}
        .slide-container {{ width:1280px; height:720px; position:relative; overflow:hidden; }}
        .accent-line {{ background-color:#1A9AFA; height:4px; width:80px; }}
        .toc-container {{ padding-left:0; padding-right:0; }}
        .toc-item {{ display:flex; align-items:center; margin-bottom:12px; }}
        .toc-number {{ width:32px; height:32px; display:flex; align-items:center; justify-content:center; border-radius:50%; background-color:#1A9AFA; color:#fff; font-weight:bold; margin-right:16px; }}
        .toc-text {{ font-size:18px; }}
        .grid {{ display:grid; }}
        .grid-cols-2 {{ grid-template-columns: 1fr 1fr; }}
        .gap-x-12 {{ column-gap:48px; }}
        .gap-y-4 {{ row-gap:16px; }}
        .w-full {{ width:100%; }}
        .h-2 {{ height:8px; }}
        .h-12 {{ height:48px; }}
        .absolute {{ position:absolute; }}
        .relative {{ position:relative; }}
        .left-0 {{ left:0; }}
        .bottom-0 {{ bottom:0; }}
        .mt-4 {{ margin-top:16px; }}
        .mb-2 {{ margin-bottom:8px; }}
        .mb-4 {{ margin-bottom:16px; }}
        .mb-2 {{ margin-bottom:8px; }}
        .text-4xl {{ font-size:32px; font-weight:700; }}
      </style>
      <div class=\"w-full h-2 bg-white\"></div>
      <div class=\"absolute left-0 top-0 bottom-0 w-12 bg-white\"></div>
      <div class=\"flex flex-col toc-container mt-4\">
        <div class=\"mb-2\">
          <h1 class=\"text-4xl mb-2\">Table of Contents</h1>
          <div class=\"accent-line mb-4\"></div>
        </div>
        <div class=\"grid grid-cols-2 gap-x-12 gap-y-4\">
          <div>{left_html}</div>
          <div>{right_html}</div>
        </div>
      </div>
      <div class=\"w-full h-12 bg-white mt-auto relative\">
        <div class=\"absolute left-0 bottom-0 h-2\" style=\"width:33.333%; background-color:#1A9AFA;\"></div>
      </div>
    </div>
    """
    return toc_html

def _rebuild_toc(deck: html_slides.HtmlDeck) -> None:
    try:
        toc_html = _build_toc_html_from_deck(deck)
        # Use header inside custom content; keep slide title empty to avoid duplication
        toc_slide = html_slides.Slide(title="", subtitle="", content=toc_html, slide_type="custom")
        deck.set_slide_at_position(1, toc_slide)
    except Exception:
        pass
def _run_demo_flow(session_id: str) -> None:
    try:
        # Reset deck and attach to chatbot instance
        global html_deck, chatbot_instance
        html_deck = html_slides.HtmlDeck(theme=ey_theme)
        chatbot_instance.html_deck = html_deck

        # Step 1: planning message
        _append_api_message(
            session_id,
            role="assistant",
            content=(
                "I'll create a concise commercial due diligence report on Heineken in EY‑Parthenon style. "
                "Let me outline the plan and set up the presentation."
            ),
        )

        # Step 2: show a tool being used (planning)
        _append_api_message(
            session_id,
            role="assistant",
            content="Planning research scope and slide structure for CDD",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Scope defined: company overview, market attractiveness, competition, financial KPIs, risks, and outlook.",
            metadata={"title": "Agent tool result"}
        )

        # Step 3: more thinking, then generate first slide
        _append_api_message(
            session_id,
            role="assistant",
            content=(
                "Initializing the presentation system and building the title slide."
            ),
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.2)
        html_deck.add_custom_html_slide(DEMO_SLIDES[0], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 1 generated: Title",
            metadata={"title": "Agent tool result"}
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Continuing with table of contents...",
        )
        time.sleep(0.6)
        _append_api_message(
            session_id,
            role="assistant",
            content="Continuing with table of contents...",
        )
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Setting up agenda and slide structure",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        # Build and set TOC dynamically at position 1
        _rebuild_toc(html_deck)
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 2 generated: Table of Contents",
            metadata={"title": "Agent tool result"}
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Executive summary...",
        )
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Drafting executive summary across highlights, market, risks & opportunities",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[10], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 3 generated: Executive Summary",
            metadata={"title": "Agent tool result"}
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Company overview & model...",
        )
        time.sleep(1.0)
        _append_api_message(
            session_id,
            role="assistant",
            content="Compiling company profile, strategy, and brand portfolio",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[2], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 4 generated: Business Overview & Model",
            metadata={"title": "Agent tool result"}
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Value chain position...",
        )
        time.sleep(1.0)
        _append_api_message(
            session_id,
            role="assistant",
            content="Analyzing value chain to map upstream and downstream strengths",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.2)
        html_deck.add_custom_html_slide(DEMO_SLIDES[3], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 5 generated: Value Chain Position",
            metadata={"title": "Agent tool result"}
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Market attractiveness...",
        )
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Synthesizing market size, growth and regional attractiveness",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[4], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 6 generated: Market Attractiveness",
            metadata={"title": "Agent tool result"}
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Segmentation & outlook...",
        )
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Building segmentation charts and growth outlook",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[5], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 7 generated: Beer Market Segmentation & Outlook",
            metadata={"title": "Agent tool result"}
        )
        # Slide 7: Segments Served vs Competitors
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Analyzing market segment coverage against key competitors.",
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Analyzing market segment coverage and competitive positioning",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[6], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 8 generated: Segments Served vs Competitors",
            metadata={"title": "Agent tool result"}
        )

        # Slide 8: Key Growth Drivers & Risks
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Assessing key growth drivers and risks.",
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Evaluating growth drivers and risk factors",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[7], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 9 generated: Key Growth Drivers & Risks",
            metadata={"title": "Agent tool result"}
        )

        # Note: We'll add Opportunities & Threats at the end
        _append_api_message(
            session_id,
            role="assistant",
            content="Noting opportunities and threats for the closing section.",
        )

        # Slide 10 -> 11: Financial Performance Overview
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Summarizing financial performance and regional highlights.",
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Compiling financial KPIs and regional performance",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[8], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 11 generated: Financial Performance Overview",
            metadata={"title": "Agent tool result"}
        )

        # Slide 11 -> 12: Competitive Landscape (global & regional)
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Mapping the broader competitive landscape globally and regionally.",
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Compiling competitive landscape and regional players",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[9], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 12 generated: Competitive Landscape",
            metadata={"title": "Agent tool result"}
        )

        # Slide 12 -> 13: Competitor Benchmarking
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Benchmarking Heineken against peers on KPIs and positioning.",
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Compiling benchmarking table and comparative radar",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[11], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 13 generated: Competitor Benchmarking",
            metadata={"title": "Agent tool result"}
        )

        # Slide 13 -> 14: Heineken Competitive Position
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Summarizing Heineken's competitive position: strengths, challenges, advantages.",
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Drafting competitive position summary",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[12], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 13 generated: Heineken Competitive Position",
            metadata={"title": "Agent tool result"}
        )

        # Final: Opportunities & Threats
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Finally: Evaluating opportunities and threats.",
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Synthesizing opportunities and threats",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[13], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 14 generated: Opportunities & Threats",
            metadata={"title": "Agent tool result"}
        )

        # Slide 15: 5-Year Segment-Based Growth Forecast
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Building 5-year segment-based growth forecast charts.",
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Rendering line and bar charts using EY palette",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[14], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 15 generated: 5-Year Segment-Based Growth Forecast",
            metadata={"title": "Agent tool result"}
        )

        # Slide 16: Scenarios (Bear/Base/Bull)
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Comparing bear, base, and bull case scenarios.",
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Rendering scenario comparison chart and table",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[15], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 16 generated: Bear, Base, and Bull Case Scenarios",
            metadata={"title": "Agent tool result"}
        )

        # Slide 17: Conclusion & Recommendations
        time.sleep(0.8)
        _append_api_message(
            session_id,
            role="assistant",
            content="Next: Drafting conclusion and recommendations.",
        )
        _append_api_message(
            session_id,
            role="assistant",
            content="Summarizing assessment and investment view",
            metadata={"title": "Agent is using a tool"}
        )
        time.sleep(1.0)
        html_deck.add_custom_html_slide(DEMO_SLIDES[16], title="", subtitle="")
        _append_api_message(
            session_id,
            role="assistant",
            content="Slide 17 generated: Conclusion & Recommendations",
            metadata={"title": "Agent tool result"}
        )

        # Regenerate TOC at end to include all slides and correct order
        _rebuild_toc(html_deck)

        # Final summary message (1–10)
        time.sleep(0.6)
        _append_api_message(
            session_id,
            role="assistant",
            content=(
                "All set. Here's your deck outline:\n\n"
                "1) Title – Commercial Due Diligence: Heineken\n"
                "2) Table of Contents – agenda of the sections\n"
                "3) Executive Summary – investment highlights, market view, risks & opportunities\n"
                "4) Business Overview & Model – profile, strategy, brands\n"
                "5) Value Chain Position – upstream/downstream activities\n"
                "6) Market Attractiveness – size, growth, regions, trends\n"
                "7) Beer Market Segmentation & Outlook – mix and CAGR\n"
                "8) Segments Served vs Competitors – coverage by segment and region\n"
                "9) Key Growth Drivers & Risks – drivers, headwinds, and exposures\n"
                "10) Financial Performance Overview – KPIs and regional highlights\n"
                "11) Competitive Landscape – global and regional players\n"
                "12) Competitor Benchmarking – KPIs, market share, and positioning\n"
                "13) Heineken Competitive Position – strengths, challenges, and advantages\n"
                "14) Opportunities & Threats – strategic levers and headwinds\n"
                "15) 5-Year Segment-Based Growth Forecast – projections by segment and region\n"
                "16) Bear, Base, and Bull Case Scenarios – 3-path outlook\n"
                "17) Conclusion & Recommendations – strategic takeaways and investment view\n\n"
                "Tell me what to add or edit next (e.g., benchmarks, risks, KPIs)."
            ),
        )
    except Exception as e:
        _append_api_message(session_id, role="assistant", content=f"Demo flow error: {e}")

# Pydantic models for API requests/responses
class ChatMessage(BaseModel):
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    messages: List[ChatMessage]
    session_id: str

class SlidesResponse(BaseModel):
    html: str

def openai_to_api_message(openai_msg: Dict) -> List[ChatMessage]:
    """Convert OpenAI format message to API ChatMessage format"""
    if openai_msg["role"] == "system":
        return []  # Don't display system messages
    
    elif openai_msg["role"] == "user":
        return [ChatMessage(role="user", content=openai_msg["content"])]
    
    elif openai_msg["role"] == "assistant":
        messages = []
        if "tool_calls" in openai_msg and openai_msg["content"]:
            # Assistant with tool calls
            messages.append(ChatMessage(role="assistant", content=openai_msg["content"]))
            tool_content = f"Calling tool {openai_msg['tool_calls'][0]['function']['name']} with arguments {openai_msg['tool_calls'][0]['function']['arguments']}"
            messages.append(ChatMessage(
                role="assistant",
                content=tool_content,
                metadata={"title": "🔧 Using a tool"}
            ))
        else:
            # Regular assistant message
            messages.append(ChatMessage(role="assistant", content=openai_msg["content"]))
        return messages
    
    elif openai_msg["role"] == "tool":
        # Tool result - display as assistant message with special formatting
        return [ChatMessage(
            role="assistant", 
            content=f"✅ {openai_msg['content']}",
            metadata={"title": "🔧 Tool result"}
        )]
    
    return []

def get_or_create_conversation(session_id: str) -> Dict:
    """Get or create conversation for session"""
    if session_id not in conversations:
        conversations[session_id] = {
            "openai_conversation": [{"role": "system", "content": config.system_prompt}],
            "api_conversation": []
        }
    return conversations[session_id]

def update_conversations_with_openai_message(session_id: str, openai_msg: Dict):
    """Add OpenAI message to both conversation lists"""
    conv = get_or_create_conversation(session_id)
    conv["openai_conversation"].append(openai_msg)
    api_messages = openai_to_api_message(openai_msg)
    conv["api_conversation"].extend(api_messages)

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Slide Generator API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat messages and return conversation history"""
    try:
        session_id = request.session_id
        user_input = request.message.strip()
        
        if not user_input:
            conv = get_or_create_conversation(session_id)
            return ChatResponse(messages=conv["api_conversation"], session_id=session_id)
        
        # Demo static mode: bypass LLM and tools, render predefined slides
        if DEMO_STATIC_MODE:
            # Minimal transcript: add user only, then stream demo steps asynchronously
            update_conversations_with_openai_message(session_id, {"role": "user", "content": user_input})
            import threading
            t = threading.Thread(target=_run_demo_flow, args=(session_id,))
            t.daemon = True
            t.start()
            conv = get_or_create_conversation(session_id)
            return ChatResponse(messages=conv["api_conversation"], session_id=session_id)

        # Normal mode: Add user message and process asynchronously
        user_msg_openai = {"role": "user", "content": user_input}
        update_conversations_with_openai_message(session_id, user_msg_openai)
        import threading
        thread = threading.Thread(target=process_conversation_sync, args=(session_id,))
        thread.daemon = True
        thread.start()
        conv = get_or_create_conversation(session_id)
        return ChatResponse(messages=conv["api_conversation"], session_id=session_id)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat: {str(e)}")

def process_conversation_sync(session_id: str):
    """Process conversation in background thread"""
    try:
        print(f"Starting async processing for session {session_id}")
        conv = get_or_create_conversation(session_id)
        max_iterations = 30
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            print(f"Iteration {iteration} - calling LLM")
            
            # Call LLM with OpenAI format conversation
            assistant_response, stop = chatbot_instance.call_llm(conv["openai_conversation"])
            print(f"LLM response received, stop={stop}")
            
            # Add assistant response to conversations
            update_conversations_with_openai_message(session_id, assistant_response)
            print(f"Added assistant response to conversation")
            
            # If assistant used tools, execute them
            if "tool_calls" in assistant_response:
                print(f"Assistant wants to use {len(assistant_response['tool_calls'])} tools")
                for tool_call in assistant_response["tool_calls"]:
                    print(f"Executing tool: {tool_call['function']['name']}")
                    # Execute the tool
                    tool_result = chatbot_instance.execute_tool_call(tool_call)
                    
                    # Add tool result to conversations
                    update_conversations_with_openai_message(session_id, tool_result)
                    print(f"Added tool result to conversation")
            
            # Check if we're done
            if stop:
                print(f"Conversation complete after {iteration} iterations")
                break
                
            # Safety check
            if iteration >= max_iterations:
                print(f"Reached maximum iterations ({max_iterations})")
                error_msg = {"role": "assistant", "content": "Reached maximum iterations. Please try a simpler request."}
                update_conversations_with_openai_message(session_id, error_msg)
                break
                
        print(f"Async processing complete for session {session_id}")
    except Exception as e:
        print(f"Error in async processing: {e}")
        import traceback
        traceback.print_exc()

@app.get("/chat/status/{session_id}")
async def get_chat_status(session_id: str):
    """Get current conversation status and messages"""
    conv = get_or_create_conversation(session_id)
    return {
        "messages": conv["api_conversation"],
        "session_id": session_id,
        "message_count": len(conv["api_conversation"])
    }

@app.get("/slides/html", response_model=SlidesResponse)
async def get_slides_html():
    """Get current slides as HTML"""
    try:
        current_html = chatbot_instance.get_deck_html()
        return SlidesResponse(html=current_html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting slides: {str(e)}")

@app.post("/slides/refresh")
async def refresh_slides():
    """Refresh slides display"""
    try:
        current_html = chatbot_instance.get_deck_html()
        return {"html": current_html}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error refreshing slides: {str(e)}")

@app.post("/slides/reset")
async def reset_slides():
    """Reset slides to empty deck"""
    try:
        # Create new deck with same theme
        global html_deck, chatbot_instance
        html_deck = html_slides.HtmlDeck(theme=ey_theme)
        chatbot_instance = chatbot.Chatbot(
            html_deck=html_deck,
            llm_endpoint_name=config.llm_endpoint,
            ws=ws,
            tool_dict=uc_tools.UC_tools
        )
        return {"message": "Slides reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting slides: {str(e)}")

@app.post("/slides/export")
async def export_slides():
    """Export slides to file"""
    try:
        output_path = config.get_output_path("exported_slides.html")
        result = chatbot_instance.save_deck(str(output_path))
        return {"message": result, "path": str(output_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting slides: {str(e)}")

@app.get("/slides/export/pptx")
async def export_slides_pptx() -> FileResponse:
    """Export the current deck to a PPTX file and stream it back.

    Uses the HtmlToPptxConverter from tools/html_to_pptx.py (pulled from export-visuals branch).
    """
    try:
        from slide_generator.tools.html_to_pptx import HtmlToPptxConverter
        from slide_generator.config import get_output_path

        # Compose output path (timestamped)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = get_output_path(f"slides_{ts}.pptx")

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert
        converter = HtmlToPptxConverter(html_deck)
        await converter.convert_to_pptx(str(output_path), include_charts=True)

        # Stream file
        return FileResponse(
            path=str(output_path),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=output_path.name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting PPTX: {str(e)}")

@app.get("/conversation/{session_id}")
async def get_conversation(session_id: str):
    """Get conversation history for debugging"""
    conv = get_or_create_conversation(session_id)
    return {
        "openai_conversation": conv["openai_conversation"],
        "api_conversation": conv["api_conversation"]
    }

if __name__ == "__main__":
    print("🚀 Starting Slide Generator FastAPI Backend")
    print(f"📊 Using LLM endpoint: {config.llm_endpoint}")
    print(f"📁 Output directory: {config.output_dir}")
    
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )

