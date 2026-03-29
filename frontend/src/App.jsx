import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

const API_URL = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/ask`

// ── intent badge config ───────────────────────────────────────────────────────

const INTENT_STYLES = {
  structured_moves:     'bg-blue-100 text-blue-700',
  structured_stats:     'bg-green-100 text-green-700',
  structured_weakness:  'bg-red-100 text-red-700',
  structured_evolution: 'bg-purple-100 text-purple-700',
  rag:                  'bg-orange-100 text-orange-700',
  hybrid:               'bg-teal-100 text-teal-700',
}

function IntentBadge({ intent }) {
  const cls = INTENT_STYLES[intent] ?? 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-block mt-2 px-2 py-0.5 rounded-full text-xs font-mono ${cls}`}>
      {intent}
    </span>
  )
}

// ── message bubbles ───────────────────────────────────────────────────────────

function UserBubble({ text }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] bg-gray-100 text-gray-800 rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed">
        {text}
      </div>
    </div>
  )
}

function AssistantBubble({ text, intent }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%]">
        <div className="bg-white border border-gray-200 text-gray-800 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed shadow-sm prose prose-sm max-w-none">
          <ReactMarkdown>{text}</ReactMarkdown>
        </div>
        {intent && <IntentBadge intent={intent} />}
      </div>
    </div>
  )
}

function ClarificationBubble({ pokemon, variants, onSelect }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%]">
        <div className="bg-white border border-gray-200 text-gray-800 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed shadow-sm">
          I found multiple forms of <span className="font-medium capitalize">{pokemon}</span>.
          Which one did you mean?
        </div>
        <div className="flex flex-wrap gap-2 mt-2">
          {variants.map(variant => (
            <button
              key={variant}
              onClick={() => onSelect(variant)}
              className="px-3 py-1 rounded-full border border-gray-400 text-gray-700 text-xs font-medium hover:bg-gray-200 active:bg-gray-300 transition"
            >
              {variant}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
        <div className="flex gap-1 items-center h-4">
          {[0, 1, 2].map(i => (
            <span
              key={i}
              className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
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
  // { question, pokemon } stored while waiting for the user to pick a variant
  const [pendingClarification, setPendingClarification] = useState(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

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
        setPendingClarification({
          question: data.original_question,
          pokemon: data.pokemon,
        })
        setMessages(prev => [
          ...prev,
          {
            role: 'clarification',
            pokemon: data.pokemon,
            variants: data.variants,
          },
        ])
      } else {
        setMessages(prev => [
          ...prev,
          { role: 'assistant', text: data.answer, intent: data.intent },
        ])
      }
    } catch {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', text: 'Something went wrong, try again.', intent: null },
      ])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  async function handleVariantSelect(variant) {
    if (!pendingClarification || loading) return

    const { question } = pendingClarification
    setPendingClarification(null)

    // Show the user's implicit choice in the thread
    setMessages(prev => [...prev, { role: 'user', text: variant }])
    setLoading(true)

    try {
      const data = await callAsk(question, variant)
      setMessages(prev => [
        ...prev,
        { role: 'assistant', text: data.answer, intent: data.intent },
      ])
    } catch {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', text: 'Something went wrong, try again.', intent: null },
      ])
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
    <div className="flex flex-col h-full bg-gray-50">

      {/* Header */}
      <header className="flex-none flex items-center justify-center h-14 border-b border-gray-200 bg-white shadow-sm">
        <h1 className="text-lg font-semibold text-gray-800 tracking-tight">Pokédex AI</h1>
      </header>

      {/* Message history */}
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[700px] px-4 py-6 flex flex-col gap-4">

          {messages.length === 0 && (
            <p className="text-center text-gray-400 text-sm mt-16 select-none">
              Ask anything about Pokémon — moves, weaknesses, evolutions, lore…
            </p>
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
                  onSelect={handleVariantSelect}
                />
              )
            }
            return <AssistantBubble key={i} text={msg.text} intent={msg.intent} />
          })}

          {loading && <TypingIndicator />}

          <div ref={bottomRef} />
        </div>
      </main>

      {/* Input bar */}
      <footer className="flex-none border-t border-gray-200 bg-white px-4 py-3">
        <div className="mx-auto max-w-[700px] flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            placeholder="Ask about a Pokémon…"
            className="flex-1 rounded-xl border border-gray-300 bg-gray-50 px-4 py-2.5 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent disabled:opacity-50 transition"
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="rounded-xl bg-blue-500 hover:bg-blue-600 active:bg-blue-700 disabled:bg-blue-300 text-white text-sm font-medium px-5 py-2.5 transition disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
      </footer>

    </div>
  )
}
