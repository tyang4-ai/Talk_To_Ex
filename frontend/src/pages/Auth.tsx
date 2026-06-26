import { useState, type FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import WizardShell from "../components/WizardShell";
import Card from "../components/Card";
import GradientButton from "../components/GradientButton";
import { Field } from "../components/Field";
import { api, setToken, errorMessage } from "../api/client";

type Mode = "login" | "register";

export default function Auth() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/plan";

  const [mode, setMode] = useState<Mode>("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res =
        mode === "register"
          ? await api.register(email.trim(), password, phone.trim())
          : await api.login(email.trim(), password);
      setToken(res.token);
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Couldn't sign you in. Check your details and try again."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <WizardShell
      onBack={() => navigate("/")}
      title={mode === "register" ? "Make your account" : "Welcome back"}
      subtitle={
        mode === "register"
          ? "You'll set up the profile and pay — no one else is involved."
          : "Pick up right where you left off."
      }
    >
      <Card>
        <form onSubmit={submit} className="space-y-4">
          <Field
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
          <Field
            label="Password"
            name="password"
            type="password"
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
          />
          {mode === "register" && (
            <div>
              <Field
                label="Your phone number"
                name="phone"
                type="tel"
                autoComplete="tel"
                required
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+1 (555) 123-4567"
              />
              <p className="mt-1 text-xs text-muted">
                Where your ex reaches out first, once they're ready. Stays on your box.
              </p>
            </div>
          )}
          {error && (
            <p className="alert-error">{error}</p>
          )}
          <GradientButton type="submit" fullWidth loading={loading}>
            {mode === "register" ? "Create account" : "Log in"}
          </GradientButton>
        </form>
      </Card>

      <button
        type="button"
        onClick={() => {
          setError(null);
          setMode(mode === "register" ? "login" : "register");
        }}
        className="mx-auto mt-6 text-sm font-semibold text-muted hover:text-ink"
      >
        {mode === "register"
          ? "Already have an account? Log in"
          : "New here? Create an account"}
      </button>
    </WizardShell>
  );
}
