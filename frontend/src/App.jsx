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
      case 'COMPLETED': return <span className="text-gray-500 text-sm">settled</span>;
      case 'FAILED': return <span className="text-gray-500 text-sm">failed</span>;
      default: return <span className="text-gray-500 text-sm">pending</span>;
    }
  };

  return (
    <div className="min-h-screen bg-white text-black font-sans flex justify-center py-20 px-6">
      <div className="w-full max-w-xl space-y-16">
        
        {/* Balance Section */}
        <div className="space-y-1">
          <p className="text-sm text-gray-500">Available balance</p>
          <h1 className="text-6xl font-medium tracking-tight">
            ₹{loading ? '...' : (balance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </h1>
          {heldBalance > 0 && (
            <p className="text-sm text-gray-400 pt-1">
              ₹{(heldBalance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })} held
            </p>
          )}
        </div>

        {/* Action Form */}
        <div>
          <form onSubmit={handlePayout} className="flex gap-3">
            <input
              type="number"
              step="0.01"
              min="1"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="flex-1 bg-transparent border border-gray-200 rounded-lg py-3 px-4 text-black placeholder:text-gray-400 focus:outline-none focus:border-gray-400 transition-colors"
              placeholder="Amount"
            />
            <button 
              type="submit" 
              disabled={submitting || !amount}
              className="bg-black text-white px-6 py-3 rounded-lg font-medium hover:bg-gray-800 transition-colors disabled:opacity-50"
            >
              {submitting ? 'Sending' : 'Withdraw'}
            </button>
          </form>
        </div>

        {/* Transactions List */}
        <div>
          <h2 className="text-sm text-gray-500 mb-6">Recent Activity</h2>
          
          {loading && payouts.length === 0 ? (
            <div className="text-gray-400 text-sm">Loading...</div>
          ) : payouts.length === 0 ? (
            <div className="text-gray-400 text-sm">No recent transactions</div>
          ) : (
            <div className="space-y-6">
              {payouts.map((p) => (
                <div key={p.id} className="flex justify-between items-center group">
                  <div>
                    <div className="font-medium">Bank Transfer</div>
                    <div className="text-sm text-gray-500 mt-0.5">
                      {new Date(p.initiated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-medium">
                      ₹{(p.amount / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
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
