'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { BookOpen, ChevronDown, Command, FileText, FolderOpen, Menu, MessageSquare, Paperclip, Plus, Search, Send, Settings2, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp, UploadCloud, X } from 'lucide-react';
import { parseSseFrame, splitSseFrames } from '../lib/sse.mjs';
import type { StreamEvent } from '../lib/sse.mjs';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
type Doc = { id: string; filename: string; status: string; chunk_count: number; file_type: string };
type Citation = { citation_id: number; chunk_id: string; document_id: string; filename: string; page_number?: number; section_name?: string; snippet: string };
type Message = { id?: string; role: 'user' | 'assistant'; content: string; citations?: Citation[] };

export default function Home() {
  const [token, setToken] = useState('');
  const [docs, setDocs] = useState<Doc[]>([]);
  const [sessions, setSessions] = useState<{id:string;title:string}[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [provider, setProvider] = useState('gemini');
  const [apiKey, setApiKey] = useState('');
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const request = useCallback(async (path: string, options: RequestInit = {}) => {
    const response = await fetch(`${API}${path}`, { ...options, headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers } });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `Request failed (${response.status})`);
    return response;
  }, [token]);
  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const [d, s] = await Promise.all([request('/api/v1/documents/'), request('/api/v1/chat/sessions')]);
      setDocs(await d.json()); setSessions(await s.json());
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not reach the API'); }
  }, [request, token]);
  useEffect(() => { const saved = localStorage.getItem('pra-token'); if (saved) setToken(saved); }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  async function signIn(create: boolean) {
    setError('');
    const email = window.prompt('Email address'); if (!email) return;
    const password = window.prompt(create ? 'Choose a password (8+ characters)' : 'Password'); if (!password) return;
    try {
      let response = await fetch(`${API}/api/v1/auth/${create ? 'register' : 'login'}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(create ? { email, password } : { email, password }) });
      if (!response.ok) throw new Error((await response.json()).detail || 'Sign in failed');
      const result = await response.json();
      const access = result.access_token;
      if (!access) { // registration returns a user; follow with login
        response = await fetch(`${API}/api/v1/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
        if (!response.ok) throw new Error('Account created, but sign in failed');
        const login = await response.json(); setAndPersistToken(login.access_token);
      } else setAndPersistToken(access);
    } catch (e) { setError(e instanceof Error ? e.message : 'Authentication failed'); }
  }
  function setAndPersistToken(value: string) { setToken(value); if (value) localStorage.setItem('pra-token', value); }
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setError('');
    setUploading(true);
    try {
      const form = new FormData(); Array.from(files).forEach(file => form.append('files', file));
      const response = await request('/api/v1/documents/upload', { method: 'POST', body: form });
      const queued: Doc[] = await response.json();
      setDocs(old => [...queued.filter(doc => !old.some(existing => existing.id === doc.id)), ...old]);
      for (let attempt = 0; attempt < 60; attempt++) {
        await new Promise(resolve => window.setTimeout(resolve, 1000));
        const docsResponse = await request('/api/v1/documents/');
        const latest: Doc[] = await docsResponse.json(); setDocs(latest);
        const ids = new Set(queued.map(doc => doc.id));
        if (latest.filter(doc => ids.has(doc.id)).every(doc => !['pending', 'processing'].includes(doc.status))) break;
      }
      await refresh();
    }
    catch (e) { setError(e instanceof Error ? e.message : 'Upload failed'); }
    finally { setUploading(false); }
  }
  async function newChat() {
    try { const response = await request('/api/v1/chat/sessions', { method: 'POST', body: JSON.stringify({ title: 'New Chat' }) }); const session = await response.json(); setSessionId(session.id); setMessages([]); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not create chat'); }
  }
  async function openChat(id: string) {
    try { const response = await request(`/api/v1/chat/sessions/${id}`); const result = await response.json(); setSessionId(id); setMessages(result.messages || []); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not load chat'); }
  }
  async function vote(messageId: string, score: number) {
    try { await request('/api/v1/feedback', { method: 'POST', body: JSON.stringify({ message_id: messageId, score }) }); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not save feedback'); }
  }
  async function send() {
    if (!question.trim() || busy) return;
    if (!token) { setError('Sign in to upload documents and start a private chat.'); return; }
    let currentSession = sessionId;
    if (!currentSession) {
      try { const response = await request('/api/v1/chat/sessions', { method: 'POST', body: JSON.stringify({ title: question.slice(0, 70) }) }); currentSession = (await response.json()).id; setSessionId(currentSession); }
      catch (e) { setError(e instanceof Error ? e.message : 'Could not create chat'); return; }
    }
    const prompt = question.trim(); setQuestion(''); setError(''); setBusy(true);
    setMessages(old => [...old, { role: 'user', content: prompt }, { role: 'assistant', content: '' }]);
    try {
      const response = await request(`/api/v1/chat/sessions/${currentSession}/messages`, { method: 'POST', body: JSON.stringify({ content: prompt, stream: true, llm_provider: provider, llm_api_key: apiKey || undefined }) });
      if (!response.body) throw new Error('Streaming is not supported by this browser');
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
      while (true) {
        const { value, done } = await reader.read(); if (done) break;
        const split = splitSseFrames(buffer, decoder.decode(value, { stream: true })); buffer = split.remainder;
        const events = split.frames;
        for (const event of events) {
          const item = parseSseFrame(event) as StreamEvent | null; if (!item) continue;
          if (item.type === 'token') setMessages(old => { const copy = [...old]; const last = copy[copy.length - 1]; copy[copy.length - 1] = { ...last, content: last.content + item.text }; return copy; });
          if (item.type === 'done') setMessages(old => { const copy = [...old]; copy[copy.length - 1] = { ...copy[copy.length - 1], id: item.message_id, citations: item.citations as Citation[] }; return copy; });
          if (item.type === 'error') throw new Error(item.message);
        }
      }
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'The answer could not be completed'); setMessages(old => old.slice(0, -1)); }
    finally { setBusy(false); }
  }
  function renderAnswer(message: Message) {
    return message.content.split(/(\[\d+\])/g).map((part, index) => {
      const match = /^\[(\d+)\]$/.exec(part);
      const citation = match ? message.citations?.find(item => item.citation_id === Number(match[1])) : undefined;
      return citation ? <button className="inline-citation" key={`${part}-${index}`} onClick={() => setSelectedCitation(citation)}>{part}</button> : part;
    });
  }
  return <main className="app-shell">
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
      <div className="brand"><span className="brand-mark"><BookOpen size={19}/></span><span>mind<span className="brand-light">vault</span></span><button className="icon-button mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={18}/></button></div>
      <button className="new-chat" onClick={newChat}><Plus size={17}/> New chat <span>⌘ K</span></button>
      <div className="nav-label">WORKSPACE</div>
      <button className="nav-item active"><MessageSquare size={17}/> Ask your library</button>
      <button className="nav-item" onClick={() => fileRef.current?.click()}><FolderOpen size={17}/> Documents <span className="nav-count">{docs.length}</span></button>
      <div className="nav-label recent-label">RECENT CHATS <Search size={14}/></div>
      <div className="session-list">{sessions.slice(0, 8).map(s => <button className={`session-item ${s.id === sessionId ? 'selected' : ''}`} key={s.id} onClick={() => openChat(s.id)}>{s.title || 'Untitled chat'}</button>)}</div>
      <div className="sidebar-bottom"><div className="privacy"><ShieldCheck size={16}/><span><b>Your data stays yours</b><small>Private by design</small></span></div>
        <button className="profile" onClick={() => token ? (localStorage.removeItem('pra-token'), setAndPersistToken('')) : void signIn(false)}><span className="avatar">{token ? 'T' : '?'}</span><span><b>{token ? 'Personal workspace' : 'Sign in to sync'}</b><small>{token ? 'Free plan' : 'Account required'}</small></span><ChevronDown size={15}/></button>
      </div>
    </aside>
    {mobileOpen && <button aria-label="Close navigation overlay" className="scrim" onClick={() => setMobileOpen(false)}/>}
    <section className="main-panel">
      <header className="topbar"><div className="top-left"><button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu size={19}/></button><div className="crumb">Workspace <span>/</span> <b>Ask your library</b></div></div><div className="top-actions"><span className="status-dot"/> <span className="status-text">All systems ready</span><button className="settings-button" onClick={() => { const key = window.prompt('Gemini API key (stored in this browser only)', apiKey); if (key !== null) setApiKey(key); }}><Settings2 size={16}/> Settings</button><button className="avatar small-avatar" onClick={() => token ? (localStorage.removeItem('pra-token'), setAndPersistToken('')) : void signIn(true)}>{token ? 'T' : '+'}</button></div></header>
      <div className="content-scroll"><div className="chat-column">
        {messages.length === 0 ? <div className="welcome"><div className="eyebrow"><Sparkles size={14}/> YOUR SECOND BRAIN, ON CALL</div><h1>Good ideas are already<br/><em>in your files.</em></h1><p>Ask a question across your documents. Every answer comes with a source you can check.</p>
          <div className="suggestion-grid"><button onClick={() => setQuestion('What are the key takeaways?')}><span className="suggestion-icon green"><FileText size={17}/></span><span><b>Find the key takeaways</b><small>Get the essential points from your files</small></span><span className="arrow">↗</span></button><button onClick={() => setQuestion('Compare the main themes across my documents')}><span className="suggestion-icon peach"><Command size={17}/></span><span><b>Connect the dots</b><small>Find themes across your library</small></span><span className="arrow">↗</span></button></div>
          <div className="upload-card" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); void upload(e.dataTransfer.files); }}><div className="upload-icon"><UploadCloud size={20}/></div><div><b>Start with a document</b><small>Drop files here, or <button className="text-link" onClick={() => fileRef.current?.click()}>browse files</button></small><small className="formats">PDF, DOCX, TXT, MD, CSV, XLSX, PPTX · up to 50 MB</small></div></div>
        </div> : <div className="messages">{messages.map((m, i) => <div className={`message ${m.role}`} key={m.id || i}><div className="message-avatar">{m.role === 'assistant' ? <BookOpen size={15}/> : 'T'}</div><div className="message-body"><div className="message-meta">{m.role === 'assistant' ? 'MINDVAULT' : 'YOU'} <span>{m.role === 'assistant' && !m.content ? 'THINKING…' : ''}</span></div><div className="message-content">{m.content ? renderAnswer(m) : <span className="typing"><i/><i/><i/></span>}{m.citations?.length ? <div className="citation-row">{m.citations.map(c => <button key={c.citation_id} onClick={() => setSelectedCitation(c)} className="citation-chip"><FileText size={13}/>{c.filename}{c.page_number ? ` · p.${c.page_number}` : ''}</button>)}</div> : null}</div>{m.role === 'assistant' && m.id ? <div className="feedback-row"><button title="Helpful" onClick={() => void vote(m.id!, 1)}><ThumbsUp size={14}/></button><button title="Not helpful" onClick={() => void vote(m.id!, -1)}><ThumbsDown size={14}/></button><span>Grounded in your library</span></div> : null}</div></div>)}<div ref={bottomRef}/></div>}
        {error && <div className="error-box">{error}<button onClick={() => setError('')} aria-label="Dismiss"><X size={14}/></button></div>}
        {docs.length > 0 && <div className="library-strip"><span className="library-icon"><FolderOpen size={14}/></span><span><b>{uploading ? 'Indexing your sources…' : `${docs.filter(d => d.status === 'indexed').length} sources ready`}</b><small>{docs.slice(0, 3).map(d => `${d.filename} · ${d.status}`).join(' · ')}</small></span><button onClick={() => fileRef.current?.click()} aria-label="Add documents"><Plus size={16}/></button></div>}
      </div></div>
      <div className="composer-wrap"><div className="composer"><button className="attach-button" onClick={() => fileRef.current?.click()} aria-label="Attach document"><Paperclip size={18}/></button><textarea value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); } }} placeholder="Ask anything about your documents…" rows={1}/><div className="composer-tools"><label className="model-select"><Sparkles size={13}/><select value={provider} onChange={e => setProvider(e.target.value)}><option value="gemini">Gemini</option><option value="groq">Groq</option><option value="openai">OpenAI</option><option value="ollama">Ollama</option></select><ChevronDown size={12}/></label><button className="send-button" onClick={send} disabled={!question.trim() || busy} aria-label="Send message"><Send size={16}/></button></div></div><div className="composer-note"><ShieldCheck size={12}/> Answers are generated from your sources and may need verification <span>·</span> <kbd>↵</kbd> to send</div></div>
    </section>
    {selectedCitation && <><button className="drawer-scrim" onClick={() => setSelectedCitation(null)} aria-label="Close source"/><aside className="source-drawer"><div className="drawer-header"><div><small>SOURCE</small><h3>{selectedCitation.filename}</h3></div><button className="icon-button" onClick={() => setSelectedCitation(null)} aria-label="Close"><X size={18}/></button></div><div className="source-meta"><span className="source-tag"><FileText size={13}/>{selectedCitation.page_number ? `Page ${selectedCitation.page_number}` : selectedCitation.section_name || 'Text passage'}</span><span>Match {selectedCitation.citation_id}</span></div><div className="source-passage">{selectedCitation.snippet}</div><div className="source-footer"><ShieldCheck size={15}/> Exact excerpt from your uploaded source</div></aside></>}
    <input ref={fileRef} type="file" hidden multiple accept=".pdf,.docx,.doc,.txt,.md,.csv,.xlsx,.xls,.pptx,.ppt" onChange={e => { void upload(e.target.files); e.currentTarget.value = ''; }}/>
    <input aria-label="API key" className="sr-only" value={apiKey} onChange={e => setApiKey(e.target.value)}/>
  </main>;
}
