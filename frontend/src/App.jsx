import { useState, useEffect } from 'react';
import { RefreshCw, ArrowUpRight, DollarSign, Activity, CheckCircle2, Clock, XCircle, Wallet, Lock, ListTodo, FileText } from 'lucide-react';

const MERCHANT_ID = "00000000-0000-0000-0000-000000000001";
const BANK_ACCOUNT_ID = "00000000-0000-0000-0000-000000000010";

function App() {
  const [balance, setBalance] = useState(0);
  const [heldBalance, setHeldBalance] = useState(0);
  const [payouts, setPayouts] = useState([]);
  const [ledger, setLedger] = useState([]);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  
  // UI State
  const [activeTab, setActiveTab] = useState('payouts'); // 'payouts' or 'ledger'
  
  // Form State
  const [amount, setAmount] = useState('');
  const [mode, setMode] = useState('IMPS');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    try {
      setPolling(true);
      const [balRes, payRes, ledRes] = await Promise.all([
        fetch(`/api/v1/merchants/${MERCHANT_ID}/balance`),
        fetch(`/api/v1/merchants/${MERCHANT_ID}/payouts`),
        fetch(`/api/v1/merchants/${MERCHANT_ID}/ledger`)
      ]);

      if (balRes.ok) {
        const b = await balRes.json();
        setBalance(b.balance);
        setHeldBalance(b.held_balance);
      }
      if (payRes.ok) {
        const p = await payRes.json();
        setPayouts(p);
      }
      if (ledRes.ok) {
        const l = await ledRes.json();
        setLedger(l);
      }
    } catch (err) {
      console.error("Failed to fetch data", err);
    } finally {
      setLoading(false);
      setTimeout(() => setPolling(false), 500);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handlePayout = async (e) => {
    e.preventDefault();
    setError(null);
    if (!amount || amount <= 0) {
      setError("Please enter a valid amount.");
      return;
    }

    setSubmitting(true);
    const idempotencyKey = crypto.randomUUID();

    try {
      const res = await fetch('/api/v1/payouts', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': idempotencyKey
        },
        body: JSON.stringify({
          merchant_id: MERCHANT_ID,
          bank_account_id: BANK_ACCOUNT_ID,
          amount: Math.round(parseFloat(amount) * 100),
          mode: mode
        })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to create payout");
      
      setAmount('');
      fetchData();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'COMPLETED': return <CheckCircle2 className="text-emerald-500 w-5 h-5" />;
      case 'FAILED': return <XCircle className="text-rose-500 w-5 h-5" />;
      case 'PROCESSING': return <RefreshCw className="text-brand-500 w-5 h-5 animate-spin" />;
      default: return <Clock className="text-zinc-400 w-5 h-5" />;
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-6 pt-12">
      <header className="flex items-center justify-between mb-12">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-brand-500/20 flex items-center justify-center border border-brand-500/30">
            <Activity className="text-brand-400 w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Payout Engine</h1>
            <p className="text-zinc-400 text-sm">Dashboard Overview</p>
          </div>
        </div>
        <button 
          onClick={fetchData} 
          className={`p-2 rounded-full hover:bg-zinc-800 transition-colors ${polling ? 'animate-spin text-brand-400' : 'text-zinc-400'}`}
        >
          <RefreshCw className="w-5 h-5" />
        </button>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Column: Actions & Balance */}
        <div className="lg:col-span-1 space-y-6">
          <div className="glass-panel p-6 relative overflow-hidden group">
            <div className="absolute top-0 right-0 p-32 bg-brand-500/10 rounded-full blur-[100px] -mr-16 -mt-16 transition-opacity duration-500 opacity-50 group-hover:opacity-100" />
            <div className="relative z-10 space-y-4">
              <div>
                <div className="flex items-center gap-2 text-zinc-400 mb-1">
                  <Wallet className="w-4 h-4" />
                  <span className="font-medium text-sm">Available Balance</span>
                </div>
                <div className="text-4xl font-bold tracking-tight text-white flex items-baseline gap-1">
                  <span className="text-zinc-500">₹</span>
                  {loading ? '---' : (balance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>
              
              <div className="pt-4 border-t border-zinc-800/50">
                <div className="flex items-center gap-2 text-zinc-500 mb-1">
                  <Lock className="w-3.5 h-3.5" />
                  <span className="font-medium text-xs uppercase tracking-wider">Held Balance (Pending)</span>
                </div>
                <div className="text-lg font-semibold text-zinc-300 flex items-baseline gap-1">
                  <span className="text-zinc-600">₹</span>
                  {loading ? '---' : (heldBalance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>
          </div>

          <div className="glass-panel p-6">
            <h2 className="text-lg font-semibold mb-6 flex items-center gap-2">
              <ArrowUpRight className="w-5 h-5 text-brand-400" />
              Request Payout
            </h2>
            
            <form onSubmit={handlePayout} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-zinc-400 mb-1.5">Amount (₹)</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <DollarSign className="w-4 h-4 text-zinc-500" />
                  </div>
                  <input
                    type="number"
                    step="0.01"
                    min="1"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className="input-field pl-9"
                    placeholder="1000.00"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-400 mb-1.5">Payout Mode</label>
                <select 
                  value={mode} 
                  onChange={(e) => setMode(e.target.value)}
                  className="input-field appearance-none"
                >
                  <option value="IMPS">IMPS (Instant)</option>
                  <option value="NEFT">NEFT (Batch)</option>
                  <option value="RTGS">RTGS (Large Value)</option>
                  <option value="UPI">UPI (Fast)</option>
                </select>
              </div>

              {error && (
                <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-rose-400 text-sm">
                  {error}
                </div>
              )}

              <button 
                type="submit" 
                disabled={submitting}
                className="btn-primary w-full flex items-center justify-center gap-2 mt-4"
              >
                {submitting ? (
                  <><RefreshCw className="w-4 h-4 animate-spin" /> Processing...</>
                ) : (
                  <>Initiate Payout <ArrowUpRight className="w-4 h-4" /></>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* Right Column: History & Ledger */}
        <div className="lg:col-span-2">
          <div className="glass-panel p-0 min-h-[600px] flex flex-col overflow-hidden">
            <div className="flex border-b border-zinc-800/50">
              <button 
                onClick={() => setActiveTab('payouts')}
                className={`flex-1 flex items-center justify-center gap-2 py-4 font-medium transition-colors ${activeTab === 'payouts' ? 'text-brand-400 border-b-2 border-brand-400 bg-brand-500/5' : 'text-zinc-500 hover:text-zinc-300'}`}
              >
                <ListTodo className="w-4 h-4" /> Payouts
              </button>
              <button 
                onClick={() => setActiveTab('ledger')}
                className={`flex-1 flex items-center justify-center gap-2 py-4 font-medium transition-colors ${activeTab === 'ledger' ? 'text-brand-400 border-b-2 border-brand-400 bg-brand-500/5' : 'text-zinc-500 hover:text-zinc-300'}`}
              >
                <FileText className="w-4 h-4" /> Ledger Entries
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {loading ? (
                <div className="flex items-center justify-center h-full text-zinc-500 animate-pulse pt-20">Loading data...</div>
              ) : activeTab === 'payouts' ? (
                payouts.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-zinc-500 flex-col gap-2 pt-20">
                    <Activity className="w-8 h-8 opacity-20" />
                    <p>No payouts found.</p>
                  </div>
                ) : (
                  payouts.map(p => (
                    <div key={p.id} className="p-4 rounded-xl bg-zinc-950/50 border border-zinc-800/50 hover:border-zinc-700 transition-colors flex items-center justify-between group">
                      <div className="flex items-center gap-4">
                        <div className="bg-zinc-900 p-2.5 rounded-lg border border-zinc-800 group-hover:bg-zinc-800 transition-colors">
                          {getStatusIcon(p.status)}
                        </div>
                        <div>
                          <div className="font-medium text-zinc-100 flex items-center gap-2">
                            ₹{(p.amount / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            <span className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700 font-medium">{p.mode}</span>
                          </div>
                          <div className="text-xs text-zinc-500 mt-1 font-mono">
                            {p.id.split('-')[0]} • {new Date(p.initiated_at).toLocaleTimeString()}
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`text-sm font-medium ${p.status === 'COMPLETED' ? 'text-emerald-400' : p.status === 'FAILED' ? 'text-rose-400' : p.status === 'PROCESSING' ? 'text-brand-400' : 'text-zinc-400'}`}>
                          {p.status}
                        </div>
                        {p.reference_id && <div className="text-xs text-zinc-500 mt-1">Ref: {p.reference_id}</div>}
                      </div>
                    </div>
                  ))
                )
              ) : (
                ledger.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-zinc-500 flex-col gap-2 pt-20">
                    <FileText className="w-8 h-8 opacity-20" />
                    <p>No ledger entries found.</p>
                  </div>
                ) : (
                  ledger.map(entry => (
                    <div key={entry.id} className="p-4 rounded-xl bg-zinc-950/50 border border-zinc-800/50 flex flex-col gap-2">
                      <div className="flex justify-between items-start">
                        <div>
                          <div className={`text-sm font-semibold tracking-wider ${entry.type === 'CREDIT' ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {entry.type}
                          </div>
                          <div className="text-zinc-300 text-sm mt-1">{entry.description}</div>
                        </div>
                        <div className="text-right">
                          <div className="font-medium text-zinc-100">₹{(entry.amount / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                          <div className="text-xs text-zinc-500 mt-1">Bal: ₹{(entry.balance_after / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                        </div>
                      </div>
                      <div className="text-xs text-zinc-600 font-mono mt-1">
                        {new Date(entry.created_at).toLocaleString()} • ID: {entry.id.split('-')[0]}
                      </div>
                    </div>
                  ))
                )
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

export default App;
