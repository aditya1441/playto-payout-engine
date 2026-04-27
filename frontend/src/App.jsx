import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

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

  const getStatusPill = (status) => {
    switch (status) {
      case 'COMPLETED': 
        return <div className="w-2.5 h-2.5 rounded-full bg-[#34C759]" title="Settled"></div>;
      case 'FAILED': 
        return <div className="w-2.5 h-2.5 rounded-full bg-[#FF3B30]" title="Failed"></div>;
      default: 
        return <div className="w-2.5 h-2.5 rounded-full bg-[#E5E5EA]" title="Pending"></div>;
    }
  };

  return (
    <div className="min-h-screen bg-[#F9F9F9] flex justify-center p-6 md:p-10 font-sans text-[#111111]">
      <div className="w-full max-w-2xl space-y-10">
        
        {/* Apple Wallet Style Balance Card */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          whileHover={{ scale: 1.01 }}
          className="bg-white rounded-3xl p-10 shadow-[0_10px_30px_rgba(0,0,0,0.06)] flex flex-col items-center text-center relative overflow-hidden"
        >
          {/* Subtle gradient overlay */}
          <div className="absolute inset-0 bg-gradient-to-b from-black/[0.02] to-transparent pointer-events-none"></div>
          
          <div className="relative z-10">
            <p className="text-[15px] font-medium text-[#8E8E93] mb-2 tracking-tight">Available Balance</p>
            <div className="text-6xl font-semibold tracking-tighter text-black flex items-baseline justify-center gap-1 mb-3">
              <span className="text-4xl text-[#8E8E93] font-medium mr-1">₹</span>
              {loading ? '---' : (balance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
            {heldBalance > 0 && (
              <p className="text-[13px] font-medium text-[#8E8E93]">
                ₹{(heldBalance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })} held
              </p>
            )}
          </div>
        </motion.div>

        {/* Minimal Action Form */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
        >
          <form onSubmit={handlePayout} className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <div className="absolute left-6 top-1/2 -translate-y-1/2 text-[#8E8E93] font-medium text-xl">₹</div>
              <input
                type="number"
                step="0.01"
                min="1"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full bg-white rounded-[20px] py-5 pl-12 pr-6 text-xl font-medium text-black placeholder:text-[#C7C7CC] focus:outline-none focus:ring-2 focus:ring-black/5 shadow-[0_4px_14px_rgba(0,0,0,0.03)] transition-all"
                placeholder="0.00"
              />
            </div>
            <button 
              type="submit" 
              disabled={submitting || !amount}
              className="bg-black text-white px-8 py-5 rounded-[20px] font-semibold text-lg hover:bg-[#1C1C1E] active:scale-95 transition-all shadow-[0_4px_14px_rgba(0,0,0,0.1)] disabled:opacity-30 disabled:pointer-events-none whitespace-nowrap"
            >
              {submitting ? 'Sending...' : 'Pay'}
            </button>
          </form>
        </motion.div>

        {/* Minimal Recent Activity */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
        >
          <h3 className="text-xl font-semibold mb-6 px-2 text-black tracking-tight">Recent Activity</h3>
          
          {loading && payouts.length === 0 ? (
            <div className="text-center py-10 text-[#8E8E93] font-medium">Loading...</div>
          ) : payouts.length === 0 ? (
            <div className="text-center py-10 text-[#8E8E93] font-medium">No recent transactions</div>
          ) : (
            <div className="bg-white rounded-[24px] p-2 shadow-[0_10px_30px_rgba(0,0,0,0.04)]">
              <AnimatePresence>
                {payouts.map((p, index) => (
                  <motion.div 
                    key={p.id}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    className={`flex items-center justify-between p-4 ${index !== payouts.length - 1 ? 'border-b border-[#F2F2F7]' : ''}`}
                  >
                    <div>
                      <div className="font-semibold text-[16px] text-black tracking-tight">Bank Transfer</div>
                      <div className="text-[13px] font-medium text-[#8E8E93] mt-0.5">
                        {new Date(p.initiated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="font-semibold text-[17px] text-black tracking-tight">
                        -₹{(p.amount / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </div>
                      {getStatusPill(p.status)}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}

export default App;
