import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowUpRight, ArrowDownLeft, Clock, CheckCircle2, XCircle, Wallet, Send, TrendingUp, RefreshCw, ChevronDown, Zap, Shield } from 'lucide-react';

const API = '/api/v1';
const MERCHANTS = [
  { id: '00000000-0000-0000-0000-000000000001', name: 'Acme Freelance', bankId: '00000000-0000-0000-0000-000000000010' },
  { id: '00000000-0000-0000-0000-000000000002', name: 'Global Agency India', bankId: '00000000-0000-0000-0000-000000000011' },
  { id: '00000000-0000-0000-0000-000000000003', name: 'Dev Studio Tech', bankId: '00000000-0000-0000-0000-000000000012' },
];

const formatINR = (paise) => (paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const StatusIcon = ({ status }) => {
  switch (status) {
    case 'COMPLETED': return <CheckCircle2 size={14} />;
    case 'FAILED': return <XCircle size={14} />;
    default: return <Clock size={14} />;
  }
};

const statusColors = {
  COMPLETED: { bg: 'rgba(52,211,153,0.12)', border: 'rgba(52,211,153,0.25)', text: '#6ee7b7' },
  FAILED: { bg: 'rgba(251,113,133,0.12)', border: 'rgba(251,113,133,0.25)', text: '#fda4af' },
  PENDING: { bg: 'rgba(251,191,36,0.12)', border: 'rgba(251,191,36,0.25)', text: '#fcd34d' },
  PROCESSING: { bg: 'rgba(147,197,253,0.12)', border: 'rgba(147,197,253,0.25)', text: '#93c5fd' },
};

function App() {
  const [merchantIdx, setMerchantIdx] = useState(0);
  const [balance, setBalance] = useState(0);
  const [heldBalance, setHeldBalance] = useState(0);
  const [payouts, setPayouts] = useState([]);
  const [ledger, setLedger] = useState([]);
  const [loading, setLoading] = useState(true);
  const [amount, setAmount] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState(null);
  const [tab, setTab] = useState('payouts');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const toastTimer = useRef(null);

  const merchant = MERCHANTS[merchantIdx];

  const showToast = (msg, type = 'success') => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ msg, type });
    toastTimer.current = setTimeout(() => setToast(null), 4000);
  };

  const fetchData = async () => {
    try {
      const [balRes, payRes, ledRes] = await Promise.all([
        fetch(`${API}/merchants/${merchant.id}/balance`),
        fetch(`${API}/merchants/${merchant.id}/payouts`),
        fetch(`${API}/merchants/${merchant.id}/ledger`),
      ]);
      if (balRes.ok) { const b = await balRes.json(); setBalance(b.balance); setHeldBalance(b.held_balance); }
      if (payRes.ok) { setPayouts(await payRes.json()); }
      if (ledRes.ok) { setLedger(await ledRes.json()); }
    } catch (err) { console.error('Fetch error', err); }
    finally { setLoading(false); }
  };

  useEffect(() => { setLoading(true); fetchData(); const iv = setInterval(fetchData, 5000); return () => clearInterval(iv); }, [merchantIdx]);

  const handlePayout = async (e) => {
    e.preventDefault();
    const paise = Math.round(parseFloat(amount) * 100);
    if (!paise || paise <= 0) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/payouts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ merchant_id: merchant.id, bank_account_id: merchant.bankId, amount: paise, mode: 'IMPS' }),
      });
      const data = await res.json();
      if (res.ok) { showToast(`Payout of ₹${formatINR(paise)} initiated`); setAmount(''); fetchData(); }
      else { showToast(data.error || 'Payout failed', 'error'); }
    } catch { showToast('Network error', 'error'); }
    finally { setSubmitting(false); }
  };

  const available = balance - heldBalance;

  return (
    <div style={{ minHeight: '100vh', background: '#050508', color: '#e4e4e7', fontFamily: "'Inter', -apple-system, system-ui, sans-serif" }}>
      {/* Ambient glow */}
      <div style={{ position: 'fixed', top: '-30%', left: '20%', width: '60vw', height: '60vw', borderRadius: '50%', background: 'radial-gradient(circle, rgba(99,102,241,0.08) 0%, transparent 70%)', pointerEvents: 'none', zIndex: 0 }} />
      <div style={{ position: 'fixed', bottom: '-20%', right: '10%', width: '40vw', height: '40vw', borderRadius: '50%', background: 'radial-gradient(circle, rgba(168,85,247,0.06) 0%, transparent 70%)', pointerEvents: 'none', zIndex: 0 }} />

      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: -30 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -30 }}
            style={{ position: 'fixed', top: 24, left: '50%', transform: 'translateX(-50%)', zIndex: 100, padding: '12px 24px', borderRadius: 12,
              background: toast.type === 'error' ? 'rgba(239,68,68,0.15)' : 'rgba(52,211,153,0.15)',
              border: `1px solid ${toast.type === 'error' ? 'rgba(239,68,68,0.3)' : 'rgba(52,211,153,0.3)'}`,
              color: toast.type === 'error' ? '#fca5a5' : '#6ee7b7', fontSize: 14, fontWeight: 500, backdropFilter: 'blur(20px)' }}>
            {toast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      <div style={{ maxWidth: 880, margin: '0 auto', padding: '32px 20px', position: 'relative', zIndex: 1 }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 40 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg, #6366f1, #a855f7)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Zap size={18} color="#fff" />
            </div>
            <div>
              <h1 style={{ fontSize: 20, fontWeight: 700, color: '#f4f4f5', margin: 0, letterSpacing: '-0.02em' }}>Playto Pay</h1>
              <p style={{ fontSize: 12, color: '#71717a', margin: 0, fontWeight: 500 }}>Payout Engine</p>
            </div>
          </div>
          {/* Merchant switcher */}
          <div style={{ position: 'relative' }}>
            <button onClick={() => setDropdownOpen(!dropdownOpen)}
              style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderRadius: 10, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', color: '#a1a1aa', fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>
              <Shield size={14} /> {merchant.name} <ChevronDown size={14} />
            </button>
            {dropdownOpen && (
              <div style={{ position: 'absolute', right: 0, top: '110%', background: '#18181b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, overflow: 'hidden', zIndex: 50, minWidth: 200, boxShadow: '0 20px 40px rgba(0,0,0,0.5)' }}>
                {MERCHANTS.map((m, i) => (
                  <button key={m.id} onClick={() => { setMerchantIdx(i); setDropdownOpen(false); }}
                    style={{ display: 'block', width: '100%', textAlign: 'left', padding: '12px 16px', background: i === merchantIdx ? 'rgba(99,102,241,0.1)' : 'transparent', border: 'none', color: i === merchantIdx ? '#818cf8' : '#a1a1aa', fontSize: 13, cursor: 'pointer', fontWeight: i === merchantIdx ? 600 : 400 }}>
                    {m.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Balance cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16, marginBottom: 32 }}>
          <motion.div layout style={{ padding: 28, borderRadius: 16, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', top: -20, right: -20, width: 100, height: 100, borderRadius: '50%', background: 'radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%)' }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Wallet size={16} color="#818cf8" />
              <span style={{ fontSize: 12, color: '#71717a', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Available Balance</span>
            </div>
            <div style={{ fontSize: 32, fontWeight: 800, color: '#f4f4f5', letterSpacing: '-0.03em' }}>
              ₹{loading ? '—' : formatINR(available > 0 ? available : balance)}
            </div>
          </motion.div>

          <motion.div layout style={{ padding: 28, borderRadius: 16, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Clock size={16} color="#fbbf24" />
              <span style={{ fontSize: 12, color: '#71717a', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Held in Escrow</span>
            </div>
            <div style={{ fontSize: 32, fontWeight: 800, color: heldBalance > 0 ? '#fcd34d' : '#3f3f46', letterSpacing: '-0.03em' }}>
              ₹{loading ? '—' : formatINR(heldBalance)}
            </div>
          </motion.div>

          <motion.div layout style={{ padding: 28, borderRadius: 16, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <TrendingUp size={16} color="#34d399" />
              <span style={{ fontSize: 12, color: '#71717a', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total Ledger</span>
            </div>
            <div style={{ fontSize: 32, fontWeight: 800, color: '#f4f4f5', letterSpacing: '-0.03em' }}>
              ₹{loading ? '—' : formatINR(balance)}
            </div>
          </motion.div>
        </div>

        {/* Payout form */}
        <motion.div layout style={{ padding: 24, borderRadius: 16, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', marginBottom: 32 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Send size={16} color="#818cf8" />
            <span style={{ fontSize: 14, fontWeight: 600, color: '#e4e4e7' }}>Request Payout</span>
          </div>
          <form onSubmit={handlePayout} style={{ display: 'flex', gap: 12, alignItems: 'stretch' }}>
            <div style={{ flex: 1, position: 'relative' }}>
              <span style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)', color: '#52525b', fontSize: 18, fontWeight: 700 }}>₹</span>
              <input type="number" step="0.01" min="1" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0.00"
                style={{ width: '100%', boxSizing: 'border-box', padding: '14px 16px 14px 36px', borderRadius: 12, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', color: '#f4f4f5', fontSize: 18, fontWeight: 600, outline: 'none', transition: 'border-color 0.2s' }}
                onFocus={e => e.target.style.borderColor = 'rgba(99,102,241,0.5)'} onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.08)'} />
            </div>
            <button type="submit" disabled={submitting || !amount}
              style={{ padding: '14px 28px', borderRadius: 12, background: submitting ? '#3730a3' : 'linear-gradient(135deg, #6366f1, #7c3aed)', border: 'none', color: '#fff', fontSize: 15, fontWeight: 700, cursor: submitting ? 'wait' : 'pointer', opacity: (!amount || submitting) ? 0.5 : 1, transition: 'all 0.2s', letterSpacing: '-0.01em', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: 8 }}>
              {submitting ? <RefreshCw size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <ArrowUpRight size={16} />}
              {submitting ? 'Processing...' : 'Withdraw'}
            </button>
          </form>
        </motion.div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 20, background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: 4, border: '1px solid rgba(255,255,255,0.06)' }}>
          {['payouts', 'ledger'].map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{ flex: 1, padding: '10px 0', borderRadius: 8, background: tab === t ? 'rgba(99,102,241,0.15)' : 'transparent', border: 'none', color: tab === t ? '#818cf8' : '#52525b', fontSize: 13, fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s', textTransform: 'capitalize' }}>
              {t === 'payouts' ? 'Payout History' : 'Ledger Entries'}
            </button>
          ))}
        </div>

        {/* Transaction list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {loading && payouts.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 48, color: '#3f3f46' }}>Loading...</div>
          ) : tab === 'payouts' ? (
            payouts.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 48, color: '#3f3f46', fontSize: 14 }}>No payouts yet</div>
            ) : payouts.map((p, i) => {
              const sc = statusColors[p.status] || statusColors.PENDING;
              return (
                <motion.div key={p.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderRadius: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', transition: 'background 0.2s' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.04)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    <div style={{ width: 36, height: 36, borderRadius: 10, background: 'rgba(239,68,68,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <ArrowUpRight size={16} color="#f87171" />
                    </div>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600, color: '#e4e4e7' }}>Bank Transfer · {p.mode}</div>
                      <div style={{ fontSize: 12, color: '#52525b', marginTop: 2 }}>
                        {new Date(p.initiated_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#e4e4e7', letterSpacing: '-0.02em' }}>-₹{formatINR(p.amount)}</div>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 10px', borderRadius: 20, background: sc.bg, border: `1px solid ${sc.border}`, color: sc.text, fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      <StatusIcon status={p.status} /> {p.status}
                    </span>
                  </div>
                </motion.div>
              );
            })
          ) : (
            ledger.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 48, color: '#3f3f46', fontSize: 14 }}>No ledger entries</div>
            ) : ledger.map((e, i) => (
              <motion.div key={e.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderRadius: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div style={{ width: 36, height: 36, borderRadius: 10, background: e.type === 'CREDIT' ? 'rgba(52,211,153,0.1)' : 'rgba(239,68,68,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {e.type === 'CREDIT' ? <ArrowDownLeft size={16} color="#34d399" /> : <ArrowUpRight size={16} color="#f87171" />}
                  </div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: '#e4e4e7' }}>{e.description || e.type}</div>
                    <div style={{ fontSize: 12, color: '#52525b', marginTop: 2 }}>
                      {new Date(e.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: e.type === 'CREDIT' ? '#6ee7b7' : '#fca5a5', letterSpacing: '-0.02em' }}>
                    {e.type === 'CREDIT' ? '+' : '-'}₹{formatINR(e.amount)}
                  </div>
                  <div style={{ fontSize: 11, color: '#52525b', marginTop: 2 }}>Bal: ₹{formatINR(e.balance_after)}</div>
                </div>
              </motion.div>
            ))
          )}
        </div>

        {/* Footer */}
        <div style={{ textAlign: 'center', padding: '40px 0 20px', color: '#27272a', fontSize: 12 }}>
          Playto Pay · Payout Engine v1.0 · {new Date().getFullYear()}
        </div>
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        input[type="number"]::-webkit-inner-spin-button, input[type="number"]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
        input[type="number"] { -moz-appearance: textfield; }
        * { box-sizing: border-box; }
        button:hover { filter: brightness(1.1); }
      `}</style>
    </div>
  );
}

export default App;
