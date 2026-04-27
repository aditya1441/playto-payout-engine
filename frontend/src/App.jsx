import { useState, useEffect } from 'react';

const MERCHANT_ID = "00000000-0000-0000-0000-000000000001";
const BANK_ACCOUNT_ID = "00000000-0000-0000-0000-000000000010";

function App() {
  const [balance, setBalance] = useState(0);
  const [heldBalance, setHeldBalance] = useState(0);
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  
  const [amount, setAmount] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchData = async () => {
    try {
      const [balRes, payRes] = await Promise.all([
        fetch(`/api/v1/merchants/${MERCHANT_ID}/balance`),
        fetch(`/api/v1/merchants/${MERCHANT_ID}/payouts`)
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
    } catch (err) {
      console.error("Failed to fetch data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 4000);
    return () => clearInterval(interval);
  }, []);

  const handlePayout = async (e) => {
    e.preventDefault();
    if (!amount || amount <= 0) return;

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
          mode: 'IMPS'
        })
      });

      if (!res.ok) throw new Error("Failed to initiate payout");
      setAmount('');
      fetchData();
    } catch (err) {
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusText = (status) => {
    switch (status) {
      case 'COMPLETED': return <span className="text-emerald-400 text-sm font-medium">Settled</span>;
      case 'FAILED': return <span className="text-red-400 text-sm font-medium">Failed</span>;
      default: return <span className="text-zinc-500 text-sm font-medium">Pending</span>;
    }
  };

  return (
    <div className="min-h-screen bg-black flex justify-center py-20 px-6 relative overflow-hidden font-sans text-white">
      
      {/* Dark modern background gradients */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] bg-gradient-to-b from-orange-500/10 to-transparent blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-gradient-to-t from-orange-600/5 to-transparent blur-[100px] pointer-events-none"></div>

      <div className="w-full max-w-xl space-y-16 relative z-10">
        
        {/* Balance Section */}
        <div className="space-y-2 text-center md:text-left flex flex-col items-center md:items-start">
          <p className="text-sm font-medium text-zinc-400 tracking-wider uppercase">Available Balance</p>
          <h1 className="text-6xl md:text-7xl font-bold tracking-tighter bg-gradient-to-br from-orange-300 via-orange-500 to-amber-600 bg-clip-text text-transparent pb-2">
            ₹{loading ? '...' : (balance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </h1>
          {heldBalance > 0 && (
            <p className="text-sm text-zinc-500 font-medium">
              ₹{(heldBalance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })} held in escrow
            </p>
          )}
        </div>

        {/* Action Form */}
        <div className="bg-zinc-900/50 backdrop-blur-xl border border-white/5 rounded-2xl p-6 shadow-2xl">
          <form onSubmit={handlePayout} className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-orange-500 font-bold">₹</span>
              <input
                type="number"
                step="0.01"
                min="1"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full bg-black/50 border border-white/10 rounded-xl py-4 pl-10 pr-4 text-white placeholder:text-zinc-600 focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/50 transition-all font-medium text-lg"
                placeholder="0.00"
              />
            </div>
            <button 
              type="submit" 
              disabled={submitting || !amount}
              className="bg-gradient-to-r from-orange-500 to-amber-600 text-black px-8 py-4 rounded-xl font-bold text-lg hover:from-orange-400 hover:to-amber-500 transition-all shadow-[0_0_20px_rgba(249,115,22,0.3)] hover:shadow-[0_0_30px_rgba(249,115,22,0.5)] disabled:opacity-50 disabled:pointer-events-none"
            >
              {submitting ? 'Processing' : 'Withdraw'}
            </button>
          </form>
        </div>

        {/* Transactions List */}
        <div>
          <h2 className="text-sm font-medium text-zinc-400 mb-6 uppercase tracking-wider">Recent Activity</h2>
          
          {loading && payouts.length === 0 ? (
            <div className="text-zinc-600 text-sm">Loading...</div>
          ) : payouts.length === 0 ? (
            <div className="text-zinc-600 text-sm">No recent transactions</div>
          ) : (
            <div className="space-y-4">
              {payouts.map((p) => (
                <div key={p.id} className="flex justify-between items-center p-5 rounded-xl bg-zinc-900/30 border border-white/5 hover:bg-zinc-900/60 transition-colors">
                  <div>
                    <div className="font-semibold text-zinc-100">Bank Transfer</div>
                    <div className="text-xs text-zinc-500 mt-1 font-medium">
                      {new Date(p.initiated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-bold text-lg text-zinc-100">
                      -₹{(p.amount / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                    {getStatusText(p.status)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

export default App;
