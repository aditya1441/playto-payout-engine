import { useState, useEffect } from 'react';
import { RefreshCw, ArrowUpRight, Activity, CheckCircle2, Clock, XCircle, Wallet, Lock, ListTodo, FileText, Sparkles, Send, ChevronRight, IndianRupee, LayoutDashboard, Settings, Bell, Search, CreditCard, ArrowDownLeft } from 'lucide-react';

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
      if (!res.ok) throw new Error(data.error || "Failed to initiate payout");
      
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
        return <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#E8F8EE] text-[#059669] text-xs font-bold tracking-wide uppercase"><CheckCircle2 className="w-3.5 h-3.5"/> Settled</span>;
      case 'FAILED': 
        return <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#FEE2E2] text-[#DC2626] text-xs font-bold tracking-wide uppercase"><XCircle className="w-3.5 h-3.5"/> Failed</span>;
      case 'PROCESSING': 
        return <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#E0E7FF] text-[#4F46E5] text-xs font-bold tracking-wide uppercase"><RefreshCw className="w-3.5 h-3.5 animate-spin"/> Processing</span>;
      default: 
        return <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#F3F4F6] text-[#4B5563] text-xs font-bold tracking-wide uppercase"><Clock className="w-3.5 h-3.5"/> Pending</span>;
    }
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] flex font-sans selection:bg-[#4F46E5]/20">
      
      {/* Sidebar - Desktop */}
      <div className="hidden lg:flex flex-col w-72 bg-white border-r border-[#E2E8F0] px-6 py-8 fixed h-full z-20">
        <div className="flex items-center gap-3 mb-12">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#4F46E5] to-[#8B5CF6] flex items-center justify-center shadow-lg shadow-[#4F46E5]/30">
            <Sparkles className="text-white w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-[#0F172A]">Playto</h1>
            <p className="text-[#64748B] text-xs font-bold tracking-widest uppercase">Business</p>
          </div>
        </div>

        <nav className="space-y-2 flex-1">
          <a href="#" className="flex items-center gap-3 px-4 py-3.5 bg-[#EEF2FF] text-[#4F46E5] rounded-2xl font-semibold transition-all">
            <LayoutDashboard className="w-5 h-5" /> Dashboard
          </a>
          <a href="#" className="flex items-center gap-3 px-4 py-3.5 text-[#64748B] hover:bg-[#F8FAFC] hover:text-[#0F172A] rounded-2xl font-semibold transition-all">
            <ListTodo className="w-5 h-5" /> Transactions
          </a>
          <a href="#" className="flex items-center gap-3 px-4 py-3.5 text-[#64748B] hover:bg-[#F8FAFC] hover:text-[#0F172A] rounded-2xl font-semibold transition-all">
            <FileText className="w-5 h-5" /> Statements
          </a>
          <a href="#" className="flex items-center gap-3 px-4 py-3.5 text-[#64748B] hover:bg-[#F8FAFC] hover:text-[#0F172A] rounded-2xl font-semibold transition-all">
            <Settings className="w-5 h-5" /> Settings
          </a>
        </nav>

        <div className="mt-auto bg-[#F8FAFC] rounded-2xl p-4 border border-[#E2E8F0]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-[#4F46E5] text-white flex items-center justify-center font-bold text-sm">
              AF
            </div>
            <div>
              <p className="text-sm font-bold text-[#0F172A]">Acme Freelance</p>
              <p className="text-xs text-[#64748B] font-medium">Merchant ID: ...0001</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 lg:ml-72 flex flex-col min-h-screen">
        
        {/* Header */}
        <header className="bg-white/80 backdrop-blur-xl border-b border-[#E2E8F0] sticky top-0 z-10 px-8 py-5 flex items-center justify-between">
          <div className="flex items-center gap-4 flex-1">
            <div className="relative w-96 hidden md:block">
              <Search className="w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 text-[#94A3B8]" />
              <input type="text" placeholder="Search transactions, UTRs..." className="w-full bg-[#F1F5F9] border-none rounded-xl py-2.5 pl-10 pr-4 text-[#0F172A] placeholder:text-[#94A3B8] focus:ring-2 focus:ring-[#4F46E5]/20 focus:outline-none font-medium" />
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button className="relative p-2.5 rounded-full hover:bg-[#F1F5F9] transition-colors text-[#64748B]">
              <Bell className="w-6 h-6" />
              <span className="absolute top-2 right-2 w-2.5 h-2.5 bg-[#EF4444] rounded-full border-2 border-white"></span>
            </button>
            <button 
              onClick={fetchData} 
              className={`p-2.5 rounded-full hover:bg-[#F1F5F9] transition-all ${polling ? 'text-[#4F46E5]' : 'text-[#64748B]'}`}
            >
              <RefreshCw className={`w-6 h-6 ${polling ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </header>

        <main className="flex-1 p-8 overflow-y-auto">
          <div className="max-w-6xl mx-auto space-y-8">
            
            {/* Top Cards Row */}
            <div className="grid grid-cols-1 xl:grid-cols-12 gap-8">
              
              {/* Vibrant Wallet Card */}
              <div className="xl:col-span-7">
                <div className="relative overflow-hidden rounded-[2rem] p-8 shadow-2xl shadow-[#4F46E5]/20 h-full flex flex-col justify-between"
                     style={{ background: 'linear-gradient(135deg, #1E1B4B 0%, #4338CA 100%)' }}>
                  
                  {/* Decorative Orbs */}
                  <div className="absolute -top-24 -right-24 w-64 h-64 bg-[#EC4899] rounded-full blur-[80px] opacity-40 mix-blend-screen"></div>
                  <div className="absolute -bottom-24 -left-24 w-64 h-64 bg-[#06B6D4] rounded-full blur-[80px] opacity-40 mix-blend-screen"></div>
                  
                  <div className="relative z-10">
                    <div className="flex justify-between items-start mb-12">
                      <div>
                        <div className="flex items-center gap-2 text-white/70 mb-2">
                          <Wallet className="w-5 h-5" />
                          <span className="font-semibold tracking-wider uppercase text-sm">Main Account Balance</span>
                        </div>
                        <div className="text-5xl md:text-6xl font-black text-white flex items-baseline gap-1 tracking-tight">
                          <span className="text-3xl text-white/60 font-semibold mr-1">₹</span>
                          {loading ? '---' : (balance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </div>
                      </div>
                      <div className="bg-white/10 backdrop-blur-md rounded-2xl p-3 border border-white/20 shadow-xl">
                        <IndianRupee className="w-8 h-8 text-white" />
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-8 pt-6 border-t border-white/20">
                      <div>
                        <p className="text-white/60 text-xs font-bold uppercase tracking-widest mb-1">Held in Escrow</p>
                        <p className="text-white font-bold text-xl flex items-baseline gap-1">
                          <span className="text-white/60 text-sm">₹</span>
                          {loading ? '---' : (heldBalance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </p>
                      </div>
                      <div className="h-10 w-[1px] bg-white/20"></div>
                      <div>
                        <p className="text-white/60 text-xs font-bold uppercase tracking-widest mb-1">Account Status</p>
                        <p className="text-[#34D399] font-bold text-lg flex items-center gap-1.5">
                          <CheckCircle2 className="w-4 h-4" /> Verified
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Action Form */}
              <div className="xl:col-span-5">
                <div className="bg-white rounded-[2rem] p-8 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-[#E2E8F0] h-full relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-full h-2 bg-gradient-to-r from-[#4F46E5] via-[#EC4899] to-[#F59E0B]"></div>
                  
                  <h2 className="text-xl font-extrabold text-[#0F172A] mb-8 flex items-center gap-3">
                    <div className="p-2 bg-[#EEF2FF] text-[#4F46E5] rounded-xl"><Send className="w-5 h-5" /></div>
                    Quick Transfer
                  </h2>
                  
                  <form onSubmit={handlePayout} className="space-y-6">
                    <div>
                      <label className="block text-sm font-bold text-[#475569] mb-2 uppercase tracking-wide">Transfer Amount</label>
                      <div className="relative flex items-center">
                        <div className="absolute left-5 text-[#94A3B8] font-bold text-xl">₹</div>
                        <input
                          type="number"
                          step="0.01"
                          min="1"
                          value={amount}
                          onChange={(e) => setAmount(e.target.value)}
                          className="w-full bg-[#F8FAFC] border-2 border-[#E2E8F0] rounded-2xl py-4 pl-12 pr-4 text-[#0F172A] placeholder:text-[#CBD5E1] focus:outline-none focus:border-[#4F46E5] focus:ring-4 focus:ring-[#4F46E5]/10 transition-all text-2xl font-black"
                          placeholder="0.00"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-bold text-[#475569] mb-2 uppercase tracking-wide">Network Selection</label>
                      <div className="relative">
                        <select 
                          value={mode} 
                          onChange={(e) => setMode(e.target.value)}
                          className="w-full bg-[#F8FAFC] border-2 border-[#E2E8F0] rounded-2xl py-4 px-5 text-[#0F172A] appearance-none focus:outline-none focus:border-[#4F46E5] focus:ring-4 focus:ring-[#4F46E5]/10 transition-all font-bold text-lg cursor-pointer"
                        >
                          <option value="IMPS">IMPS (Instant)</option>
                          <option value="NEFT">NEFT (Batch Processing)</option>
                          <option value="RTGS">RTGS (High Value)</option>
                          <option value="UPI">UPI (Fast Network)</option>
                        </select>
                        <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none bg-white p-1 rounded-md shadow-sm border border-[#E2E8F0]">
                          <ChevronRight className="w-5 h-5 text-[#64748B] rotate-90" />
                        </div>
                      </div>
                    </div>

                    {error && (
                      <div className="p-4 bg-[#FEF2F2] border border-[#FECACA] rounded-2xl text-[#DC2626] text-sm font-bold flex items-center gap-3 animate-in fade-in slide-in-from-top-2">
                        <XCircle className="w-5 h-5 shrink-0" />
                        {error}
                      </div>
                    )}

                    {success && (
                      <div className="p-4 bg-[#F0FDF4] border border-[#BBF7D0] rounded-2xl text-[#16A34A] text-sm font-bold flex items-center gap-3 animate-in fade-in slide-in-from-top-2">
                        <CheckCircle2 className="w-5 h-5 shrink-0" />
                        Transfer initiated successfully!
                      </div>
                    )}

                    <button 
                      type="submit" 
                      disabled={submitting}
                      className="w-full bg-[#0F172A] hover:bg-[#1E293B] text-white active:scale-[0.98] transition-all py-4 rounded-2xl font-bold text-lg flex items-center justify-center gap-3 disabled:opacity-50 disabled:pointer-events-none shadow-xl shadow-[#0F172A]/20 mt-4 group"
                    >
                      {submitting ? (
                        <><RefreshCw className="w-6 h-6 animate-spin" /> Authorizing via Bank...</>
                      ) : (
                        <>Pay Now <ArrowUpRight className="w-6 h-6 group-hover:translate-x-1 group-hover:-translate-y-1 transition-transform" /></>
                      )}
                    </button>
                  </form>
                </div>
              </div>
            </div>

            {/* Bottom Section: Tabs & List */}
            <div className="bg-white rounded-[2rem] shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-[#E2E8F0] overflow-hidden">
              <div className="flex border-b border-[#E2E8F0] bg-[#F8FAFC] p-2 gap-2">
                <button 
                  onClick={() => setActiveTab('payouts')}
                  className={`flex-1 flex items-center justify-center gap-3 py-4 rounded-xl font-bold transition-all ${activeTab === 'payouts' ? 'bg-white text-[#4F46E5] shadow-sm border border-[#E2E8F0]' : 'text-[#64748B] hover:text-[#0F172A] hover:bg-white/50'}`}
                >
                  <ListTodo className="w-5 h-5" /> Recent Activity
                </button>
                <button 
                  onClick={() => setActiveTab('ledger')}
                  className={`flex-1 flex items-center justify-center gap-3 py-4 rounded-xl font-bold transition-all ${activeTab === 'ledger' ? 'bg-white text-[#4F46E5] shadow-sm border border-[#E2E8F0]' : 'text-[#64748B] hover:text-[#0F172A] hover:bg-white/50'}`}
                >
                  <FileText className="w-5 h-5" /> Official Statements
                </button>
              </div>
              
              <div className="p-6">
                {loading ? (
                  <div className="py-20 flex flex-col items-center justify-center text-[#94A3B8] gap-4">
                    <RefreshCw className="w-10 h-10 animate-spin text-[#CBD5E1]" />
                    <p className="font-bold">Syncing with ledger...</p>
                  </div>
                ) : activeTab === 'payouts' ? (
                  payouts.length === 0 ? (
                    <div className="py-24 flex flex-col items-center justify-center text-[#94A3B8] gap-4">
                      <div className="w-20 h-20 rounded-full bg-[#F1F5F9] flex items-center justify-center border-4 border-white shadow-sm">
                        <Activity className="w-10 h-10 text-[#CBD5E1]" />
                      </div>
                      <p className="font-bold text-lg">No transfers yet</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {payouts.map(p => (
                        <div key={p.id} className="p-5 rounded-2xl bg-white border border-[#E2E8F0] hover:shadow-md hover:border-[#CBD5E1] transition-all flex items-center justify-between group">
                          <div className="flex items-center gap-5">
                            <div className="w-12 h-12 rounded-full bg-[#EEF2FF] text-[#4F46E5] flex items-center justify-center font-bold">
                              <ArrowUpRight className="w-6 h-6" />
                            </div>
                            <div>
                              <div className="font-extrabold text-[#0F172A] text-lg">Bank Transfer</div>
                              <div className="text-sm font-bold text-[#64748B] mt-1 flex items-center gap-2">
                                <span>{new Date(p.initiated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                                <span className="w-1 h-1 bg-[#CBD5E1] rounded-full"></span>
                                <span className="px-2 py-0.5 bg-[#F1F5F9] text-[#475569] rounded-md text-xs uppercase tracking-wider">{p.mode}</span>
                              </div>
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-2">
                            <div className="font-black text-[#0F172A] text-xl tracking-tight">
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
                    <div className="py-24 flex flex-col items-center justify-center text-[#94A3B8] gap-4">
                      <div className="w-20 h-20 rounded-full bg-[#F1F5F9] flex items-center justify-center border-4 border-white shadow-sm">
                        <FileText className="w-10 h-10 text-[#CBD5E1]" />
                      </div>
                      <p className="font-bold text-lg">Ledger is empty</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {ledger.map(entry => (
                        <div key={entry.id} className="p-5 rounded-2xl bg-white border border-[#E2E8F0] hover:shadow-md hover:border-[#CBD5E1] transition-all flex items-center justify-between group">
                          <div className="flex items-center gap-5">
                            <div className={`w-12 h-12 rounded-full flex items-center justify-center font-bold ${entry.type === 'CREDIT' ? 'bg-[#E8F8EE] text-[#059669]' : 'bg-[#F1F5F9] text-[#64748B]'}`}>
                              {entry.type === 'CREDIT' ? <ArrowDownLeft className="w-6 h-6" /> : <ArrowUpRight className="w-6 h-6" />}
                            </div>
                            <div>
                              <div className="font-extrabold text-[#0F172A] text-base">{entry.description}</div>
                              <div className="text-sm font-bold text-[#64748B] mt-1">
                                {new Date(entry.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                              </div>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className={`font-black text-xl tracking-tight ${entry.type === 'CREDIT' ? 'text-[#059669]' : 'text-[#0F172A]'}`}>
                              {entry.type === 'CREDIT' ? '+' : '-'}₹{(entry.amount / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </div>
                            <div className="text-xs font-bold text-[#94A3B8] mt-1 uppercase tracking-wider">
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
        </main>
      </div>
    </div>
  );
}

export default App;
