import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { GoogleLogin } from "@react-oauth/google";
import { useAuth } from "../hooks/useAuth";
import { FlagIcon } from "../components/FlagIcon";

export function Register() {
  const { register, loginWithGoogle } = useAuth();
  const [searchParams] = useSearchParams();
  const next = searchParams.get("next");
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");

  useEffect(() => {
    document.title = "Sign Up — League Caddie";
  }, []);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!firstName.trim()) {
      setError("Please enter your first name.");
      return;
    }
    if (!lastName.trim()) {
      setError("Please enter your last name.");
      return;
    }
    if (!displayName.trim()) {
      setError("Please enter a display name.");
      return;
    }
    if (!email.trim()) {
      setError("Please enter your email address.");
      return;
    }
    if (!password) {
      setError("Please enter a password.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      await register(email, password, displayName, firstName, lastName);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-fairway-900 flex flex-col items-center justify-center px-4 py-12 relative overflow-hidden">
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
          <p className="text-2xl font-bold text-ink-900 pt-1">Create your account</p>
          <p className="text-sm text-ink-500">Takes 2 minutes to set up</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label htmlFor="firstName" className="block text-sm font-medium text-ink-700">
                First name
              </label>
              <input
                id="firstName"
                type="text"
                placeholder="First name"
                required
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                maxLength={50}
                className="w-full border border-ink-300 rounded-xs px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-fairway-600 focus:border-transparent transition-shadow"
              />
              {firstName.length >= 40 && <p className="text-[11px] text-ink-400 text-right tabular-nums">{firstName.length}/50</p>}
            </div>
            <div className="space-y-1.5">
              <label htmlFor="lastName" className="block text-sm font-medium text-ink-700">
                Last name
              </label>
              <input
                id="lastName"
                type="text"
                placeholder="Last name"
                required
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                maxLength={50}
                className="w-full border border-ink-300 rounded-xs px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-fairway-600 focus:border-transparent transition-shadow"
              />
              {lastName.length >= 40 && <p className="text-[11px] text-ink-400 text-right tabular-nums">{lastName.length}/50</p>}
            </div>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="displayName" className="block text-sm font-medium text-ink-700">
              Display name
            </label>
            <input
              id="displayName"
              type="text"
              placeholder="How you'll appear in leagues"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              maxLength={50}
              className="w-full border border-ink-300 rounded-xs px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-fairway-600 focus:border-transparent transition-shadow"
            />
            {displayName.length >= 40 && <p className="text-[11px] text-ink-400 text-right tabular-nums">{displayName.length}/50</p>}
          </div>
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
            <label htmlFor="password" className="block text-sm font-medium text-ink-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              placeholder="At least 8 characters"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-ink-300 rounded-xs px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-fairway-600 focus:border-transparent transition-shadow"
            />
            {password.length > 0 && password.length < 8 && (
              <p className="text-xs text-brass-600 mt-1">{8 - password.length} more character{8 - password.length !== 1 ? "s" : ""} needed</p>
            )}
          </div>
          <div className="space-y-1.5">
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-ink-700">
              Confirm password
            </label>
            <input
              id="confirmPassword"
              type="password"
              placeholder="Re-enter your password"
              required
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
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
            {loading ? "Creating account…" : "Create account"}
          </button>

          <p className="text-center text-xs text-ink-400 leading-relaxed">
            By creating an account, you agree to our{" "}
            <Link to="/terms" target="_blank" className="text-fairway-700 underline hover:text-fairway-600">
              Terms of Service
            </Link>{" "}
            and{" "}
            <Link to="/privacy" target="_blank" className="text-fairway-700 underline hover:text-fairway-600">
              Privacy Policy
            </Link>
          </p>
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
      </div>

      {/* Footer link */}
      <p className="relative mt-6 text-sm text-fairway-400">
        Already have an account?{" "}
        <Link
          to={next ? `/login?next=${encodeURIComponent(next)}` : "/login"}
          className="text-white font-medium hover:underline"
        >
          Sign in
        </Link>
      </p>
    </div>
  );
}
