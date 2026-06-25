import { useNavigate } from "react-router-dom";
import WizardShell from "../components/WizardShell";
import Card from "../components/Card";
import GradientButton from "../components/GradientButton";
import TipJar from "../components/TipJar";

const PERKS = [
  "A real phone number to text",
  "Your ex's voice, distilled from your chats",
  "Replies that adapt as you talk",
  "Encrypted end-to-end on your own box",
];

/**
 * Wizard step 1. The app is free (no Stripe gate — see backend
 * `require_subscription`), so this is the value intro + an optional tip jar,
 * then straight into building the persona.
 */
export default function Plan() {
  const navigate = useNavigate();

  return (
    <WizardShell
      step={1}
      totalSteps={5}
      onBack={() => navigate("/")}
      title="It's on the house"
      subtitle="No card, no catch. Build your ex and start texting — free."
    >
      <Card className="bg-tinder-gradient-135 text-white">
        <div className="flex items-baseline justify-between">
          <h2 className="text-display-md font-extrabold">Reconnect</h2>
          <span className="font-display text-lg font-bold">Free</span>
        </div>
        <p className="mt-1 text-sm text-white/85">
          Yours to keep — your chats stay encrypted on your own machine.
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

      <div className="mt-5">
        <TipJar />
      </div>

      <div className="mt-auto pt-8">
        <GradientButton fullWidth onClick={() => navigate("/intake")}>
          Start — it's free →
        </GradientButton>
        <p className="mt-3 text-center text-xs text-muted">
          No payment, ever. Tips are optional and just say thanks.
        </p>
      </div>
    </WizardShell>
  );
}
