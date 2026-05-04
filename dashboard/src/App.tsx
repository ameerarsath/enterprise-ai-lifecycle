import React, { useEffect, useState, useRef } from 'react';
import { Activity, Brain, Server, Shield, MessageSquare, Terminal, Database, Code, CheckCircle, AlertTriangle } from 'lucide-react';
import './index.css';

// Types
type AgentState = 'idle' | 'thinking' | 'acting' | 'blocked' | 'finished';

interface AgentInfo {
  name: string;
  state: AgentState;
  details: string;
  icon: React.ReactNode;
}

interface Message {
  id: string;
  from_agent: string;
  to_agent: string;
  type: string;
  content: string;
  timestamp: string;
}

interface TokenUsage {
  used: number;
  budget: number;
  percent: number;
}

const WS_URL = 'ws://localhost:8000/ws/demo_project';

const App = () => {
  const [agents, setAgents] = useState<Record<string, AgentInfo>>({
    orchestrator: { name: 'Orchestrator', state: 'idle', details: 'Waiting to start...', icon: <Server size={18} /> },
    manager: { name: 'Manager', state: 'idle', details: 'Standing by', icon: <Activity size={18} /> },
    business_analyst: { name: 'BA Agent', state: 'idle', details: 'Standing by', icon: <MessageSquare size={18} /> },
    frontend: { name: 'Frontend Agent', state: 'idle', details: 'Standing by', icon: <Code size={18} /> },
    backend: { name: 'Backend Agent', state: 'idle', details: 'Standing by', icon: <Terminal size={18} /> },
    database: { name: 'DB Agent', state: 'idle', details: 'Standing by', icon: <Database size={18} /> },
    security: { name: 'Security Agent', state: 'idle', details: 'Standing by', icon: <Shield size={18} /> },
  });

  const [messages, setMessages] = useState<Message[]>([]);
  const [thinkingLog, setThinkingLog] = useState<string>('');
  const [budget, setBudget] = useState<TokenUsage>({ used: 0, budget: 2000000, percent: 0 });
  const [userInput, setUserInput] = useState('');
  const [error, setError] = useState<{ message: string; agent: string; fatal: boolean } | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [apiKeys, setApiKeys] = useState({
    anthropic: '',
    openai: '',
    gemini: '',
    nvidia: '',
    openrouter: '',
    tavily: '',
  });
  
  const ws = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Connect to WebSocket
    ws.current = new WebSocket(WS_URL);

    ws.current.onopen = () => {
      console.log('Connected to Enterprise Orchestrator');
      // Mock initial state
      addMessage({
        id: '1', from_agent: 'system', to_agent: 'all', type: 'system',
        content: 'WebSocket connected to AI Orchestrator', timestamp: new Date().toISOString()
      });
    };

    ws.current.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      handleEvent(payload);
    };

    ws.current.onclose = () => {
      console.log('Disconnected');
    };

    return () => {
      ws.current?.close();
    };
  }, []);

  useEffect(() => {
    // Auto-scroll messages
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, thinkingLog]);

  const handleEvent = (payload: any) => {
    switch (payload.type) {
      case 'agent_state_changed':
        setAgents(prev => ({
          ...prev,
          [payload.data.agent]: {
            ...prev[payload.data.agent],
            state: payload.data.state,
            details: payload.data.details
          }
        }));
        break;
        
      case 'agent_thinking':
        setThinkingLog(prev => prev + payload.data.chunk);
        break;

      case 'message_bus_event':
        addMessage(payload.data);
        break;

      case 'budget_update':
        setBudget({
          used: payload.data.used,
          budget: payload.data.budget,
          percent: payload.data.percent_used
        });
        break;

      case 'system_error':
        setError({
          message: payload.data.message,
          agent: payload.data.agent,
          fatal: payload.data.fatal
        });
        // Auto-clear non-fatal errors after 5s
        if (!payload.data.fatal) {
          setTimeout(() => setError(null), 5000);
        }
        break;
        
      default:
        console.log('Unknown event:', payload);
    }
  };

  const addMessage = (msg: Message) => {
    setMessages(prev => [...prev, msg].slice(-50)); // Keep last 50
  };

  const handleSendMessage = () => {
    if (!userInput.trim() || !ws.current) return;
    
    // Send to backend via WebSocket
    ws.current.send(userInput);
    
    // Add to local message list immediately
    addMessage({
      id: Math.random().toString(),
      from_agent: 'Human',
      to_agent: 'Orchestrator',
      type: 'user_chat',
      content: userInput,
      timestamp: new Date().toISOString()
    });
    
    setUserInput('');
  };

  const handleSaveKeys = async () => {
    try {
      const response = await fetch('http://localhost:8000/settings/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(apiKeys),
      });
      if (response.ok) {
        alert('API Keys updated successfully');
        setShowSettings(false);
      }
    } catch (e) {
      console.error('Failed to save keys', e);
    }
  };

  // Mock simulate execution for the demo
  const triggerDemo = () => {
    setAgents(prev => ({
      ...prev,
      orchestrator: { ...prev.orchestrator, state: 'acting', details: 'Analyzing client brief' }
    }));
    
    setTimeout(() => {
      setThinkingLog('{\n  "analysis": "Client needs a scalable web app",\n  "approach": "Microservices with React frontend",\n  "complexity": "high"\n}\n\n[GuardRail] Complexity too high. Simplifying to monolithic backend.\n');
      setAgents(prev => ({
        ...prev,
        orchestrator: { ...prev.orchestrator, state: 'idle', details: 'Delegated to Manager' },
        manager: { ...prev.manager, state: 'thinking', details: 'Planning sprint...' }
      }));
      setBudget({ used: 45000, budget: 2000000, percent: 2.25 });
    }, 2000);
    
    setTimeout(() => {
      addMessage({
        id: '2', from_agent: 'manager', to_agent: 'frontend', type: 'request',
        content: 'Build React UI for login component', timestamp: new Date().toISOString()
      });
      setAgents(prev => ({
        ...prev,
        manager: { ...prev.manager, state: 'idle', details: 'Sprint planned' },
        frontend: { ...prev.frontend, state: 'acting', details: 'Writing TSX components' },
        backend: { ...prev.backend, state: 'acting', details: 'Writing FastAPI routes' }
      }));
      setBudget({ used: 120000, budget: 2000000, percent: 6.0 });
    }, 5000);
  };

  return (
    <div className="app-container">
      {/* GLOBAL ERROR BANNER */}
      {error && (
        <div className={`error-banner ${error.fatal ? 'fatal' : ''} animate-slide-in`}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <AlertTriangle size={24} />
            <div>
              <strong>Error in {error.agent}:</strong> {error.message}
            </div>
          </div>
          <button onClick={() => setError(null)} style={{ background: 'transparent', border: 'none', color: 'white', cursor: 'pointer' }}>✕</button>
        </div>
      )}

      {/* LEFT PANEL: Agent Monitor */}
      <div className="glass-panel">
        <div className="header-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Server size={20} />
            <h2>Agent Monitor</h2>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={() => setShowSettings(!showSettings)} className="icon-btn">
              <Server size={18} />
            </button>
            <div className="status-badge active">Live</div>
          </div>
        </div>
        
        <div className="scroll-area agent-list">
          {Object.entries(agents).map(([key, agent]) => (
            <div key={key} className={`agent-node ${agent.state === 'thinking' ? 'thinking' : agent.state === 'acting' ? 'acting' : ''}`}>
              <div className="agent-header">
                <div className="agent-name">
                  {agent.icon}
                  {agent.name}
                </div>
                <div className="agent-state">
                  {agent.state === 'thinking' ? <Brain size={14} className="inline mr-1" /> : null}
                  {agent.state}
                </div>
              </div>
              <div className="agent-details">
                {agent.details}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* CENTER PANEL: Dashboard & Thinking Engine */}
      <div className="glass-panel" style={{ gridColumn: '2' }}>
        <div className="header-bar">
          <h2>Enterprise AI Lifecycle</h2>
          <button 
            onClick={triggerDemo}
            style={{ padding: '0.5rem 1rem', background: 'var(--primary)', color: '#000', border: 'none', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer' }}
          >
            Run Demo Pipeline
          </button>
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div>
            <h3>Thinking Engine Log</h3>
            <div className="thinking-box" style={{ height: '200px' }}>
              {thinkingLog || <span style={{ opacity: 0.5 }}>Waiting for chain of thought...</span>}
            </div>
          </div>

          <div>
            <h3>System Health & Guards</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '0.5rem' }}>
              <div style={{ background: 'rgba(255,255,255,0.05)', padding: '1rem', borderRadius: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <Shield size={16} color="var(--primary)" />
                  <strong>GuardRails Active</strong>
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  ✓ Secret scanning<br/>
                  ✓ Prompt injection defense<br/>
                  ✓ Complexity gates
                </div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.05)', padding: '1rem', borderRadius: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <CheckCircle size={16} color="var(--primary)" />
                  <strong>Contract Registry</strong>
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  0 API mismatches<br/>
                  0 Schema drifts<br/>
                  Sync: 100%
                </div>
              </div>
            </div>
          </div>

          <div className="budget-meter">
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <h3>Token Budget</h3>
              <span style={{ fontSize: '0.85rem' }}>{budget.used.toLocaleString()} / {budget.budget.toLocaleString()}</span>
            </div>
            <div className="meter-bg">
              <div 
                className={`meter-fill ${budget.percent > 80 ? 'warning' : ''}`} 
                style={{ width: `${Math.max(1, budget.percent)}%` }}
              ></div>
            </div>
          </div>
        </div>
      </div>

      {/* RIGHT PANEL: Message Bus */}
      <div className="glass-panel" style={{ gridColumn: '3' }}>
        <div className="header-bar">
          <h2>Message Bus</h2>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Redis Streams</div>
        </div>

        <div className="scroll-area" ref={scrollRef}>
          <div className="message-stream">
            {messages.length === 0 && (
              <div style={{ textAlign: 'center', opacity: 0.5, marginTop: '2rem' }}>
                No messages yet
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`message-item ${msg.type} animate-slide-in`} style={msg.from_agent === 'Human' ? { borderLeftColor: 'var(--primary)', background: 'rgba(74, 222, 128, 0.05)' } : {}}>
                <div className="message-meta">
                  <span><strong>{msg.from_agent}</strong> → {msg.to_agent}</span>
                  <span>{new Date(msg.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'})}</span>
                </div>
                <div className="message-content">
                  {msg.content}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Chat Input */}
        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', background: 'rgba(0,0,0,0.2)', padding: '0.5rem', borderRadius: '8px' }}>
          <input 
            type="text" 
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
            placeholder="Talk to the system..."
            style={{ flex: 1, background: 'transparent', border: 'none', color: 'white', padding: '0.5rem', outline: 'none' }}
          />
          <button 
            onClick={handleSendMessage}
            style={{ background: 'var(--primary)', color: 'black', border: 'none', padding: '0.5rem 1rem', borderRadius: '4px', cursor: 'pointer' }}
          >
            Send
          </button>
        </div>
      </div>

      {/* SETTINGS MODAL OVERLAY */}
      {showSettings && (
        <div className="modal-overlay animate-slide-in">
          <div className="glass-panel modal-content">
            <div className="header-bar">
              <h2>Enterprise API Management</h2>
              <button onClick={() => setShowSettings(false)} className="close-btn">✕</button>
            </div>
            
            <div className="scroll-area" style={{ padding: '1rem' }}>
              <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
                Configure global API keys for high-performance agent execution.
              </p>
              
              <div className="settings-grid">
                {[
                  { id: 'anthropic', label: 'Anthropic (Claude)', icon: <Brain size={16} /> },
                  { id: 'openai', label: 'OpenAI (GPT-4)', icon: <Activity size={16} /> },
                  { id: 'gemini', label: 'Google (Gemini)', icon: <CheckCircle size={16} /> },
                  { id: 'nvidia', label: 'Nvidia NIM', icon: <Server size={16} /> },
                  { id: 'openrouter', label: 'OpenRouter', icon: <Terminal size={16} /> },
                  { id: 'tavily', label: 'Tavily (Search)', icon: <Database size={16} /> },
                ].map((provider) => (
                  <div key={provider.id} className="settings-item">
                    <label>
                      {provider.icon}
                      {provider.label}
                    </label>
                    <input 
                      type="password" 
                      value={(apiKeys as any)[provider.id]} 
                      onChange={(e) => setApiKeys({...apiKeys, [provider.id]: e.target.value})}
                      placeholder="sk-..."
                    />
                  </div>
                ))}
              </div>
            </div>
            
            <div className="modal-footer">
              <button onClick={() => setShowSettings(false)} className="btn-secondary">Cancel</button>
              <button onClick={handleSaveKeys} className="btn-primary">Save Infrastructure</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
