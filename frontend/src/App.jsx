import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

const API_URL = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/ask`

// ── intent badge config ───────────────────────────────────────────────────────

const BADGE_STYLES = {
  structured_moves:        { bg: '#FF7C00', color: '#FFF3E0' },
  structured_weakness:     { bg: '#3B4CCA', color: '#E8ECFF' },
  structured_evolution:    { bg: '#74CB48', color: '#1A3300' },
  structured_stats:        { bg: '#E2BF65', color: '#2A1A00' },
  structured_move_info:    { bg: '#9141CB', color: '#F3E8FF' },
  structured_move_learners:{ bg: '#B8A038', color: '#FFF8E1' },
  hybrid_effectiveness:    { bg: '#F95587', color: '#FFF0F3' },
  rag:                     { bg: '#68A090', color: '#E8F4F0' },
  clarification_needed:    { bg: '#6390F0', color: '#E8F0FF' },
}

function IntentBadge({ intent }) {
  const style = BADGE_STYLES[intent] ?? { bg: '#68A090', color: '#E8F4F0' }
  return (
    <span style={{
      display: 'inline-block',
      marginTop: '8px',
      background: style.bg,
      color: style.color,
      fontFamily: "'Roboto Mono', monospace",
      fontSize: '11px',
      fontWeight: 600,
      padding: '3px 10px',
      borderRadius: '12px',
      letterSpacing: '0.04em',
      textTransform: 'uppercase',
    }}>
      {intent}
    </span>
  )
}

// ── message bubbles ───────────────────────────────────────────────────────────

function UserBubble({ text }) {
  return (
    <div style={{ marginBottom: '12px', display: 'flex', justifyContent: 'flex-end' }}>
      <div style={{
        maxWidth: '70%',
        background: 'var(--bg-card)',
        borderLeft: '3px solid var(--accent-yellow)',
        padding: '12px 16px',
        borderRadius: 0,
        color: 'var(--text-user)',
        fontFamily: 'Inter, sans-serif',
        fontSize: '14px',
        lineHeight: '1.5',
      }}>
        {text}
      </div>
    </div>
  )
}

function AssistantBubble({ text, intent, entryNumber, isError }) {
  const paddedNum = String(entryNumber).padStart(3, '0')
  return (
    <div style={{ marginBottom: '4px', display: 'flex', justifyContent: 'flex-start' }}>
      <div style={{ maxWidth: '85%' }}>
        <div style={{
          background: 'var(--bg-card)',
          borderLeft: isError ? '3px solid #E24B4A' : '3px solid var(--accent-blue-light)',
          padding: '12px 16px',
          borderRadius: 0,
          color: isError ? '#F09595' : 'var(--text-screen)',
          fontFamily: 'Inter, sans-serif',
          fontSize: '14px',
          lineHeight: '1.6',
        }}>
          <span style={{
            display: 'block',
            marginBottom: '6px',
            fontFamily: "'Roboto Mono', monospace",
            fontSize: '11px',
            color: isError ? '#F09595' : 'var(--text-secondary)',
          }}>
            {isError ? 'ERROR ▶' : `#${paddedNum} ▶`}
          </span>
          <div className="prose-screen">
            <ReactMarkdown>{text}</ReactMarkdown>
          </div>
        </div>
        {intent && !isError && <IntentBadge intent={intent} />}
      </div>
    </div>
  )
}

function ClarificationBubble({ pokemon, variants, entryNumber, onSelect }) {
  const paddedNum = String(entryNumber).padStart(3, '0')
  return (
    <div style={{ marginBottom: '4px', display: 'flex', justifyContent: 'flex-start' }}>
      <div style={{ maxWidth: '85%' }}>
        <div style={{
          background: 'var(--bg-card)',
          borderLeft: '3px solid var(--accent-blue-light)',
          padding: '12px 16px',
          borderRadius: 0,
          color: 'var(--text-screen)',
          fontFamily: 'Inter, sans-serif',
          fontSize: '14px',
          lineHeight: '1.6',
        }}>
          <span style={{
            display: 'block',
            marginBottom: '6px',
            fontFamily: "'Roboto Mono', monospace",
            fontSize: '11px',
            color: 'var(--text-secondary)',
          }}>
            #{paddedNum} ▶
          </span>
          I found multiple forms of <strong style={{ textTransform: 'capitalize' }}>{pokemon}</strong>. Which one did you mean?
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '12px' }}>
            {variants.map(variant => (
              <VariantPill key={variant} label={variant} onClick={() => onSelect(variant)} />
            ))}
          </div>
        </div>
        <IntentBadge intent="clarification_needed" />
      </div>
    </div>
  )
}

function VariantPill({ label, onClick }) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        border: '1px solid #6390F0',
        background: hovered ? '#6390F0' : 'transparent',
        color: hovered ? '#E8F0FF' : '#6390F0',
        fontFamily: "'Roboto Mono', monospace",
        fontSize: '11px',
        textTransform: 'uppercase',
        padding: '4px 12px',
        borderRadius: '12px',
        cursor: 'pointer',
        transition: 'background 0.15s, color 0.15s',
      }}
    >
      {label}
    </button>
  )
}

function LoadingBubble() {
  const dotBase = {
    fontFamily: "'Roboto Mono', monospace",
    fontSize: '20px',
    color: 'var(--text-screen)',
    animation: 'dotPulse 1.4s ease-in-out infinite',
    display: 'inline-block',
  }
  return (
    <div style={{ marginBottom: '4px', display: 'flex', justifyContent: 'flex-start' }}>
      <div style={{
        background: 'var(--bg-card)',
        borderLeft: '3px solid var(--accent-blue-light)',
        padding: '12px 16px',
        borderRadius: 0,
      }}>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <span style={{ ...dotBase, animationDelay: '0s' }}>·</span>
          <span style={{ ...dotBase, animationDelay: '0.2s' }}>·</span>
          <span style={{ ...dotBase, animationDelay: '0.4s' }}>·</span>
        </div>
        <div style={{
          fontFamily: "'Roboto Mono', monospace",
          fontSize: '11px',
          color: 'var(--text-secondary)',
          letterSpacing: '0.1em',
          marginTop: '6px',
        }}>
          LOADING DATA...
        </div>
      </div>
    </div>
  )
}

// ── api helper ────────────────────────────────────────────────────────────────

async function callAsk(question, selectedVariant = null) {
  const body = { question }
  if (selectedVariant) body.selected_variant = selectedVariant
  const res = await fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// ── main app ──────────────────────────────────────────────────────────────────

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [pendingClarification, setPendingClarification] = useState(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  // Count assistant messages for entry numbering
  const assistantCount = useRef(0)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function sendMessage() {
    const question = input.trim()
    if (!question || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', text: question }])
    setLoading(true)

    try {
      const data = await callAsk(question)

      if (data.needs_clarification) {
        assistantCount.current += 1
        const num = assistantCount.current
        setPendingClarification({ question: data.original_question, pokemon: data.pokemon })
        setMessages(prev => [...prev, {
          role: 'clarification',
          pokemon: data.pokemon,
          variants: data.variants,
          entryNumber: num,
        }])
      } else {
        assistantCount.current += 1
        const num = assistantCount.current
        setMessages(prev => [...prev, {
          role: 'assistant',
          text: data.answer,
          intent: data.intent,
          entryNumber: num,
        }])
      }
    } catch {
      assistantCount.current += 1
      const num = assistantCount.current
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: 'Something went wrong. Try again.',
        intent: null,
        entryNumber: num,
        isError: true,
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  async function handleVariantSelect(variant) {
    if (!pendingClarification || loading) return

    const { question } = pendingClarification
    setPendingClarification(null)

    setMessages(prev => [...prev, { role: 'user', text: variant }])
    setLoading(true)

    try {
      const data = await callAsk(question, variant)
      assistantCount.current += 1
      const num = assistantCount.current
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: data.answer,
        intent: data.intent,
        entryNumber: num,
      }])
    } catch {
      assistantCount.current += 1
      const num = assistantCount.current
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: 'Something went wrong. Try again.',
        intent: null,
        entryNumber: num,
        isError: true,
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: 'var(--bg-screen)',
    }}>

      {/* Header */}
      <header style={{
        flexShrink: 0,
        background: 'var(--bg-device)',
        height: '56px',
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderBottom: '3px solid var(--accent-yellow)',
      }}>
        <span style={{
          fontFamily: "'Press Start 2P', monospace",
          fontSize: '14px',
          color: 'var(--accent-yellow)',
        }}>
          POKÉDEX
        </span>
        <span style={{
          fontFamily: "'Roboto Mono', monospace",
          fontSize: '11px',
          fontWeight: 600,
          color: 'var(--text-on-red)',
          background: 'rgba(0,0,0,0.2)',
          padding: '4px 10px',
          borderRadius: '12px',
        }}>
          GEN I–IX
        </span>
      </header>

      {/* Screen bezel */}
      <div style={{
        flex: 1,
        display: 'flex',
        justifyContent: 'center',
        background: '#0A0A1A',
        padding: '8px',
        minHeight: 0,
      }}>
        {/* Chat container */}
        <div style={{
          maxWidth: '760px',
          width: '100%',
          background: 'var(--bg-screen-inner)',
          display: 'flex',
          flexDirection: 'column',
          flex: 1,
          minHeight: 0,
        }}>

          {/* Message list */}
          <div style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
          }}>

            {messages.length === 0 && (
              <div style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
              }}>
                <div style={{
                  fontFamily: "'Roboto Mono', monospace",
                  fontSize: '13px',
                  color: 'var(--text-screen)',
                }}>
                  <span style={{ animation: 'blink 1s step-end infinite' }}>{'>'}</span>
                  {' POKÉDEX AI — READY.'}
                </div>
                <div style={{
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '13px',
                  color: 'var(--text-secondary)',
                }}>
                  Ask about any Pokémon.
                </div>
              </div>
            )}

            {messages.map((msg, i) => {
              if (msg.role === 'user') {
                return <UserBubble key={i} text={msg.text} />
              }
              if (msg.role === 'clarification') {
                return (
                  <ClarificationBubble
                    key={i}
                    pokemon={msg.pokemon}
                    variants={msg.variants}
                    entryNumber={msg.entryNumber}
                    onSelect={handleVariantSelect}
                  />
                )
              }
              return (
                <AssistantBubble
                  key={i}
                  text={msg.text}
                  intent={msg.intent}
                  entryNumber={msg.entryNumber}
                  isError={msg.isError}
                />
              )
            })}

            {loading && <LoadingBubble />}

            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div style={{
            flexShrink: 0,
            background: 'var(--bg-input)',
            borderTop: '2px solid var(--bg-device)',
            padding: '12px 16px',
            display: 'flex',
            gap: '8px',
          }}>
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              placeholder="Ask about a Pokémon…"
              style={{
                flex: 1,
                background: 'var(--bg-screen-inner)',
                border: '1px solid var(--border-screen)',
                borderRadius: 0,
                color: 'var(--text-screen)',
                fontFamily: 'Inter, sans-serif',
                fontSize: '14px',
                padding: '10px 14px',
                outline: 'none',
                opacity: loading ? 0.5 : 1,
              }}
              onFocus={e => { e.target.style.borderColor = 'var(--accent-yellow)' }}
              onBlur={e => { e.target.style.borderColor = 'var(--border-screen)' }}
            />
            <SendButton onClick={sendMessage} disabled={loading || !input.trim()} />
          </div>

        </div>
      </div>
    </div>
  )
}

function SendButton({ onClick, disabled }) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'var(--accent-yellow)',
        color: '#000000',
        fontFamily: "'Rajdhani', sans-serif",
        fontWeight: 600,
        fontSize: '14px',
        padding: '10px 20px',
        borderRadius: 0,
        border: 'none',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.4 : hovered ? 0.85 : 1,
        transition: 'opacity 0.15s',
        flexShrink: 0,
      }}
    >
      SEND
    </button>
  )
}
