import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { loadStripe, type Stripe } from "@stripe/stripe-js";
import WizardShell from "../components/WizardShell";
import Card from "../components/Card";
import GradientButton from "../components/GradientButton";
import { api, errorMessage } from "../api/client";

const PUBLISHABLE_KEY = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY;

// Lazily resolve the Stripe.js singleton only if/when we need the redirect fallback.
let stripePromise: Promise<Stripe | null> | null = null;
function getStripe(): Promise<Stripe | null> {
  if (!stripePromise) {
    stripePromise = PUBLISHABLE_KEY ? loadStripe(PUBLISHABLE_KEY) : Promise.resolve(null);
  }
  return stripePromise;
}

const PERKS = [
  "A real phone number to text",
  "Your ex's voice, distilled from your chats",
  "Replies that adapt as you talk",
  "Encrypted end-to-end on your own box",
];

export default function Plan() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startCheckout() {
    setError(null);
    setLoading(true);
    try {
      const { url, session_id } = await api.checkout();
      // Primary path: hosted Checkout URL from the backend.
      if (url) {
        window.location.href = url;
        return;
      }
      // Fallback: redirect via stripe-js using the session id.
      if (session_id) {
        const stripe = await getStripe();
        if (!stripe) throw new Error("Payments aren't configured yet.");
        const { error: stripeErr } = await stripe.redirectToCheckout({ sessionId: session_id });
        if (stripeErr) throw stripeErr;
        return;
      }
      throw new Error("Checkout didn't return a session.");
    } catch (err) {
      setError(errorMessage(err, "Couldn't start checkout. Try again in a moment."));
      setLoading(false);
    }
  }

  return (
    <WizardShell
      step={1}
      totalSteps={5}
      onBack={() => navigate("/")}
      title="Choose your plan"
      subtitle="One subscription covers the number and keeps them on the line."
    >
      <Card className="bg-tinder-gradient-135 text-white">
        <div className="flex items-baseline justify-between">
          <h2 className="text-display-md font-extrabold">Reconnect</h2>
          <span className="font-display text-lg font-bold">
            see price at checkout
          </span>
        </div>
        <p className="mt-1 text-sm text-white/85">
          Cancel anytime — your data stays put, the persona just goes dormant.
        </p>
        <ul className="mt-5 space-y-2.5">
          {PERKS.map((perk) => (
            <li key={perk} className="flex items-start gap-2 text-[15px]">
              <span aria-hidden className="mt-0.5">
                ✓
              </span>
              <span>{perk}</span>
            </li>
          ))}
        </ul>
      </Card>

      {error && (
        <p className="mt-4 rounded-2xl bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600">
          {error}
        </p>
      )}

      <div className="mt-auto pt-8">
        <GradientButton fullWidth loading={loading} onClick={startCheckout}>
          Continue to payment 💳
        </GradientButton>
        <p className="mt-3 text-center text-xs text-muted">
          Secured by Stripe. You'll come right back here after paying.
        </p>
      </div>
    </WizardShell>
  );
}
