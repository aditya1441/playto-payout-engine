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
        return <div className="px-3 py-1 rounded-full bg-[#E8F8EE] text-[#059669] text-xs font-semibold tracking-wide">Settled</div>;
      case 'FAILED': 
        return <div className="px-3 py-1 rounded-full bg-[#FEE2E2] text-[#DC2626] text-xs font-semibold tracking-wide">Failed</div>;
      default: 
        return <div className="px-3 py-1 rounded-full bg-[#F3F4F6] text-[#6B7280] text-xs font-semibold tracking-wide">Pending</div>;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-100 flex justify-center p-6 md:p-10 font-sans text-[#111111] relative overflow-hidden">
      
      {/* Light radial highlight behind the main card */}
      <div className="absolute top-[10%] left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-white/60 blur-[80px] rounded-full pointer-events-none"></div>

      <div className="w-full max-w-2xl space-y-12 relative z-10">
        
        {/* Premium Balance Card */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          whileHover={{ 
            scale: 1.01, 
            boxShadow: '0 20px 40px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04)' 
          }}
          className="bg-gradient-to-b from-white to-gray-50/50 rounded-3xl p-10 shadow-[0_10px_30px_rgba(0,0,0,0.08),0_2px_10px_rgba(0,0,0,0.03)] flex flex-col items-center text-center relative overflow-hidden border border-white/60 transition-shadow duration-300"
        >
          {/* Soft inner highlight for glass feel */}
          <div className="absolute inset-0 bg-gradient-to-b from-white/40 to-transparent pointer-events-none rounded-3xl shadow-[inset_0_1px_1px_rgba(255,255,255,1)]"></div>
          
          <div className="relative z-10">
            <p className="text-[14px] font-semibold text-[#9CA3AF] mb-3 tracking-widest uppercase">Available Balance</p>
            <div className="text-[4rem] md:text-[5rem] leading-none font-semibold tracking-tighter text-[#111111] flex items-baseline justify-center gap-1 mb-4">
              <span className="text-4xl text-[#9CA3AF] font-medium mr-1">₹</span>
              {loading ? '---' : (balance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
            {heldBalance > 0 && (
              <p className="text-[14px] font-medium text-[#6B7280] tracking-tight">
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
          <form onSubmit={handlePayout} className="flex flex-col sm:flex-row gap-4 relative">
            <div className="relative flex-1">
              <div className="absolute left-6 top-1/2 -translate-y-1/2 text-[#9CA3AF] font-medium text-xl">₹</div>
              <input
                type="number"
                step="0.01"
                min="1"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full bg-white/80 backdrop-blur-md rounded-[20px] py-5 pl-12 pr-6 text-xl font-medium text-[#111111] placeholder:text-[#D1D5DB] focus:outline-none focus:ring-2 focus:ring-black/5 shadow-[0_4px_20px_rgba(0,0,0,0.04),inset_0_2px_4px_rgba(255,255,255,0.8)] border border-white/60 transition-all duration-300"
                placeholder="0.00"
              />
            </div>
            <button 
              type="submit" 
              disabled={submitting || !amount}
              className="bg-[#111111] text-white px-8 py-5 rounded-[20px] font-semibold text-lg hover:bg-black hover:shadow-[0_8px_20px_rgba(0,0,0,0.15)] active:scale-[0.98] transition-all duration-300 shadow-[0_4px_14px_rgba(0,0,0,0.1)] disabled:opacity-30 disabled:pointer-events-none whitespace-nowrap"
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
          className="pt-4"
        >
          <h3 className="text-lg font-semibold mb-6 px-4 text-[#111111] tracking-tight">Recent Activity</h3>
          
          {loading && payouts.length === 0 ? (
            <div className="text-center py-10 text-[#9CA3AF] font-medium">Loading...</div>
          ) : payouts.length === 0 ? (
            <div className="text-center py-10 text-[#9CA3AF] font-medium">No recent transactions</div>
          ) : (
            <div className="bg-white/60 backdrop-blur-xl rounded-[24px] p-3 shadow-[0_10px_40px_rgba(0,0,0,0.03)] border border-white/50">
              <AnimatePresence>
                {payouts.map((p, index) => (
                  <motion.div 
                    key={p.id}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    className={`flex items-center justify-between p-4 transition-colors duration-200 hover:bg-white/40 rounded-[16px] ${index !== payouts.length - 1 ? 'mb-1' : ''}`}
                  >
                    <div>
                      <div className="font-semibold text-[16px] text-[#111111] tracking-tight">Bank Transfer</div>
                      <div className="text-[13px] font-medium text-[#9CA3AF] mt-0.5 tracking-tight">
                        {new Date(p.initiated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="font-semibold text-[17px] text-[#111111] tracking-tight">
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
