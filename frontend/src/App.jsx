import { useState, useEffect } from 'react';
import { RefreshCw, ArrowUpRight, DollarSign, Activity, CheckCircle2, Clock, XCircle, Wallet, Lock, ListTodo, FileText, Sparkles, Send, ChevronRight } from 'lucide-react';

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
  const [activeTab, setActiveTab] = useState('payouts');
  
  // Form State
  const [amount, setAmount] = useState('');
  const [mode, setMode] = useState('IMPS');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

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
      setTimeout(() => setPolling(false), 800);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 4000);
    return () => clearInterval(interval);
  }, []);

  const handlePayout = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);
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
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
      fetchData();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'COMPLETED': 
        return <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-medium border border-emerald-500/20"><CheckCircle2 className="w-3 h-3"/> Settled</span>;
      case 'FAILED': 
        return <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-rose-500/10 text-rose-400 text-xs font-medium border border-rose-500/20"><XCircle className="w-3 h-3"/> Failed</span>;
      case 'PROCESSING': 
        return <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-blue-500/10 text-blue-400 text-xs font-medium border border-blue-500/20"><RefreshCw className="w-3 h-3 animate-spin"/> Processing</span>;
      default: 
        return <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-zinc-500/10 text-zinc-400 text-xs font-medium border border-zinc-500/20"><Clock className="w-3 h-3"/> Pending</span>;
    }
  };

  return (
    <div className="min-h-screen bg-black text-white selection:bg-blue-500/30 overflow-hidden relative font-sans">
      
      {/* Background ambient light effects mimicking Apple's dark mode blurs */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-indigo-600/20 blur-[120px] pointer-events-none mix-blend-screen" />
      <div className="absolute bottom-[-10%] right-[-5%] w-[30%] h-[40%] rounded-full bg-blue-600/10 blur-[120px] pointer-events-none mix-blend-screen" />
      
      <div className="max-w-6xl mx-auto p-6 md:p-10 relative z-10">
        <header className="flex items-center justify-between mb-12">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-zinc-800 to-zinc-700 flex items-center justify-center border border-white/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.2)]">
              <Sparkles className="text-white w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-b from-white to-white/70">Playto Pay</h1>
              <p className="text-zinc-500 text-sm font-medium">Merchant Dashboard</p>
            </div>
          </div>
          <button 
            onClick={fetchData} 
            className={`p-2.5 rounded-full bg-white/5 border border-white/10 hover:bg-white/10 transition-all ${polling ? 'animate-spin border-blue-500/50 text-blue-400' : 'text-zinc-400 hover:text-white'}`}
          >
            <RefreshCw className="w-5 h-5" />
          </button>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Left Column: Balance Card & Action Form */}
          <div className="lg:col-span-5 flex flex-col gap-6">
            
            {/* Apple Card Style Balance Widget */}
            <div className="relative overflow-hidden rounded-3xl p-8 bg-gradient-to-br from-zinc-900 to-black border border-white/10 shadow-2xl group">
              <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/noise-pattern-with-subtle-cross-lines.png')] opacity-[0.03] mix-blend-overlay"></div>
              
              <div className="relative z-10 flex flex-col h-full justify-between gap-8">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="flex items-center gap-2 text-zinc-400 mb-2">
                      <Wallet className="w-4 h-4" />
                      <span className="font-medium text-sm tracking-wide">Available Balance</span>
                    </div>
                    <div className="text-5xl font-bold tracking-tighter text-white flex items-baseline gap-1">
                      <span className="text-zinc-500 font-medium text-3xl">₹</span>
                      {loading ? '---' : (balance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>
                
                <div className="pt-5 border-t border-white/10 flex justify-between items-center">
                  <div>
                    <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                      <Lock className="w-3.5 h-3.5" />
                      <span className="font-medium text-xs uppercase tracking-wider">Held Funds</span>
                    </div>
                    <div className="text-xl font-semibold text-zinc-300 flex items-baseline gap-1">
                      <span className="text-zinc-600 text-sm">₹</span>
                      {loading ? '---' : (heldBalance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="h-10 w-10 rounded-full bg-white/5 flex items-center justify-center border border-white/10 group-hover:bg-white/10 transition-colors">
                    <Activity className="w-5 h-5 text-zinc-400" />
                  </div>
                </div>
              </div>
            </div>

            {/* Premium Payout Form */}
            <div className="bg-zinc-900/50 backdrop-blur-xl border border-white/10 rounded-3xl p-7 shadow-xl">
              <h2 className="text-lg font-semibold mb-6 flex items-center gap-2 text-zinc-100">
                <Send className="w-5 h-5 text-blue-400" />
                Send Payout
              </h2>
              
              <form onSubmit={handlePayout} className="space-y-5">
                <div>
                  <label className="block text-sm font-medium text-zinc-400 mb-2">Amount</label>
                  <div className="relative flex items-center">
                    <div className="absolute left-4 text-zinc-500 font-medium">₹</div>
                    <input
                      type="number"
                      step="0.01"
                      min="1"
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                      className="w-full bg-black/50 border border-white/10 rounded-2xl py-3.5 pl-9 pr-4 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all text-lg font-medium"
                      placeholder="0.00"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-zinc-400 mb-2">Network</label>
                  <div className="relative">
                    <select 
                      value={mode} 
                      onChange={(e) => setMode(e.target.value)}
                      className="w-full bg-black/50 border border-white/10 rounded-2xl py-3.5 px-4 text-white appearance-none focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all font-medium"
                    >
                      <option value="IMPS">IMPS (Instant Transfer)</option>
                      <option value="NEFT">NEFT (Standard Batch)</option>
                      <option value="RTGS">RTGS (High Value)</option>
                      <option value="UPI">UPI (Fast Network)</option>
                    </select>
                    <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none">
                      <ChevronRight className="w-5 h-5 text-zinc-500 rotate-90" />
                    </div>
                  </div>
                </div>

                {error && (
                  <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-2xl text-rose-400 text-sm flex items-center gap-2">
                    <XCircle className="w-4 h-4 shrink-0" />
                    {error}
                  </div>
                )}

                {success && (
                  <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl text-emerald-400 text-sm flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                    Payout initiated successfully.
                  </div>
                )}

                <button 
                  type="submit" 
                  disabled={submitting}
                  className="w-full bg-white text-black hover:bg-zinc-200 active:scale-[0.98] transition-all py-3.5 rounded-2xl font-semibold text-[15px] flex items-center justify-center gap-2 disabled:opacity-50 disabled:pointer-events-none shadow-[0_0_20px_rgba(255,255,255,0.1)] mt-2"
                >
                  {submitting ? (
                    <><RefreshCw className="w-5 h-5 animate-spin" /> Authorizing...</>
                  ) : (
                    <>Confirm Payout</>
                  )}
                </button>
              </form>
            </div>
          </div>

          {/* Right Column: History & Ledger Tabs */}
          <div className="lg:col-span-7 flex flex-col h-[700px]">
            <div className="bg-zinc-900/40 backdrop-blur-2xl border border-white/10 rounded-3xl flex flex-col h-full shadow-2xl overflow-hidden">
              
              <div className="flex border-b border-white/10 p-2 gap-2 bg-zinc-950/50">
                <button 
                  onClick={() => setActiveTab('payouts')}
                  className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-medium text-sm transition-all ${activeTab === 'payouts' ? 'bg-zinc-800 text-white shadow-sm border border-white/5' : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/5'}`}
                >
                  <ListTodo className="w-4 h-4" /> Activity
                </button>
                <button 
                  onClick={() => setActiveTab('ledger')}
                  className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-medium text-sm transition-all ${activeTab === 'ledger' ? 'bg-zinc-800 text-white shadow-sm border border-white/5' : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/5'}`}
                >
                  <FileText className="w-4 h-4" /> Statements
                </button>
              </div>
              
              <div className="flex-1 overflow-y-auto p-2 scrollbar-hide">
                {loading ? (
                  <div className="flex items-center justify-center h-full text-zinc-500">
                    <RefreshCw className="w-6 h-6 animate-spin opacity-50" />
                  </div>
                ) : activeTab === 'payouts' ? (
                  payouts.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-zinc-500 gap-3">
                      <div className="w-16 h-16 rounded-full bg-zinc-800/50 flex items-center justify-center border border-white/5">
                        <Activity className="w-8 h-8 opacity-40" />
                      </div>
                      <p className="font-medium">No recent activity</p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      {payouts.map(p => (
                        <div key={p.id} className="p-4 rounded-2xl hover:bg-white/5 transition-colors flex items-center justify-between group cursor-default">
                          <div className="flex items-center gap-4">
                            <div className="w-10 h-10 rounded-full bg-zinc-800 border border-white/10 flex items-center justify-center text-zinc-400">
                              <ArrowUpRight className="w-5 h-5" />
                            </div>
                            <div>
                              <div className="font-medium text-zinc-100">Bank Withdrawal</div>
                              <div className="text-xs text-zinc-500 mt-0.5">
                                {new Date(p.initiated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                              </div>
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-1.5">
                            <div className="font-semibold text-white tracking-tight">
                              -₹{(p.amount / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </div>
                            {getStatusBadge(p.status)}
                          </div>
                        </div>
                      ))}
                    </div>
                  )
                ) : (
                  ledger.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-zinc-500 gap-3">
                      <div className="w-16 h-16 rounded-full bg-zinc-800/50 flex items-center justify-center border border-white/5">
                        <FileText className="w-8 h-8 opacity-40" />
                      </div>
                      <p className="font-medium">No statements available</p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      {ledger.map(entry => (
                        <div key={entry.id} className="p-4 rounded-2xl hover:bg-white/5 transition-colors flex justify-between items-center group cursor-default">
                          <div className="flex items-center gap-4">
                            <div className={`w-2 h-2 rounded-full ${entry.type === 'CREDIT' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]' : 'bg-zinc-600'}`} />
                            <div>
                              <div className="font-medium text-zinc-200 text-sm">{entry.description}</div>
                              <div className="text-xs text-zinc-500 mt-0.5">
                                {new Date(entry.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                              </div>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className={`font-semibold tracking-tight ${entry.type === 'CREDIT' ? 'text-emerald-400' : 'text-white'}`}>
                              {entry.type === 'CREDIT' ? '+' : '-'}₹{(entry.amount / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </div>
                            <div className="text-xs text-zinc-500 mt-0.5">
                              Bal: ₹{(entry.balance_after / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
