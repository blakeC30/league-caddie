import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { GoogleLogin } from "@react-oauth/google";
import { useAuth } from "../hooks/useAuth";
import { FlagIcon } from "../components/FlagIcon";

export function Login() {
  const { login, loginWithGoogle } = useAuth();
  const [searchParams] = useSearchParams();
  const next = searchParams.get("next");
  const sessionExpired = searchParams.get("session_expired") === "1";
  const [email, setEmail] = useState("");

  useEffect(() => {
    document.title = "Log In — League Caddie";
  }, []);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) {
      setError("Please enter your email address.");
      return;
    }
    if (!password) {
      setError("Please enter your password.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      await login(email, password);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Invalid email or password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-fairway-900 flex flex-col items-center justify-center px-4 relative overflow-hidden">
      {/* Decorative blobs */}
      {/* Back link */}
      <div className="relative w-full max-w-sm mb-6">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-fairway-400 hover:text-white transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
          </svg>
          Back to home
        </Link>
      </div>

      {/* Card */}
      <div className="relative w-full max-w-sm bg-white rounded-sm shadow-raised shadow-black/30 p-8 space-y-6">
        {/* Brand */}
        <div className="text-center space-y-1">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xl font-bold text-fairway-900 hover:text-fairway-700 transition-colors"
          >
            <FlagIcon className="w-5 h-5 flex-shrink-0" />
            League Caddie
          </Link>
          <p className="text-2xl font-bold text-ink-900 pt-1">Welcome back</p>
          <p className="text-sm text-ink-500">Sign in to your account to continue</p>
        </div>

        {sessionExpired && (
          <div className="bg-brass-50 border border-brass-100 text-brass-700 text-sm rounded-xs px-4 py-3 text-center">
            Your session has expired. Please sign in again.
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="email" className="block text-sm font-medium text-ink-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              placeholder="you@example.com"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-ink-300 rounded-xs px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-fairway-600 focus:border-transparent transition-shadow"
            />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="password" className="text-sm font-medium text-ink-700">
                Password
              </label>
              <Link to="/forgot-password" className="text-xs text-fairway-700 hover:text-fairway-900 font-medium transition-colors">
                Forgot your password?
              </Link>
            </div>
            <input
              id="password"
              type="password"
              placeholder="••••••••"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-ink-300 rounded-xs px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-fairway-600 focus:border-transparent transition-shadow"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 bg-flag-50 border border-flag-300 text-flag-700 text-sm px-3.5 py-2.5 rounded-xs">
              <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
              </svg>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-fairway-700 hover:bg-fairway-700 disabled:opacity-50 text-white font-semibold py-3 rounded-xs transition-colors shadow-sheet"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>

        </form>

        {/* Divider */}
        <div className="flex items-center gap-3 text-xs text-ink-400">
          <hr className="flex-1 border-ink-200" />
          or continue with
          <hr className="flex-1 border-ink-200" />
        </div>

        {/* Google */}
        <div className="flex justify-center">
          <GoogleLogin
            onSuccess={(cred) => {
              if (cred.credential) loginWithGoogle(cred.credential).catch(() => setError("Google sign-in failed."));
            }}
            onError={() => setError("Google sign-in failed.")}
            width="100%"
          />
        </div>

        <p className="text-center text-xs text-ink-400 leading-relaxed">
          By signing in, you agree to our{" "}
          <Link to="/terms" target="_blank" className="text-fairway-700 underline hover:text-fairway-600">
            Terms of Service
          </Link>{" "}
          and{" "}
          <Link to="/privacy" target="_blank" className="text-fairway-700 underline hover:text-fairway-600">
            Privacy Policy
          </Link>
        </p>
      </div>

      {/* Footer link */}
      <p className="relative mt-6 text-sm text-fairway-400">
        No account?{" "}
        <Link
          to={next ? `/register?next=${encodeURIComponent(next)}` : "/register"}
          className="text-white font-medium hover:underline"
        >
          Create one
        </Link>
      </p>
    </div>
  );
}
