import { useState } from "react";
import { Link } from "react-router-dom";
import { authApi } from "../api/endpoints";
import { FlagIcon } from "../components/FlagIcon";
import { RESET_TOKEN_EXPIRE_HOURS } from "../utils";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authApi.forgotPassword(email);
      setSubmitted(true);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 429) {
        setError("Too many requests. Please wait an hour before trying again.");
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-950 via-green-900 to-green-800 flex flex-col items-center justify-center px-4 relative overflow-hidden">
      {/* Decorative blobs */}
      <div className="absolute -top-32 -right-32 w-[500px] h-[500px] rounded-full bg-white/5 blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 -left-24 w-80 h-80 rounded-full bg-black/20 blur-3xl pointer-events-none" />

      {/* Back link */}
      <div className="relative w-full max-w-sm mb-6">
        <Link
          to="/login"
          className="inline-flex items-center gap-1.5 text-sm text-green-400 hover:text-white transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
          </svg>
          Back to sign in
        </Link>
      </div>

      {/* Card */}
      <div className="relative w-full max-w-sm bg-white rounded-2xl shadow-2xl shadow-black/30 p-8 space-y-6">
        {/* Brand */}
        <div className="text-center space-y-1">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xl font-bold text-green-900 hover:text-green-700 transition-colors"
          >
            <FlagIcon className="w-5 h-5 flex-shrink-0" />
            League Caddie
          </Link>
          <p className="text-2xl font-bold text-gray-900 pt-1">Forgot password?</p>
          <p className="text-sm text-gray-500">Enter your email and we'll send you a reset link.</p>
        </div>

        {submitted ? (
          /* Success state — always shown the same way regardless of whether the email exists */
          <div className="space-y-4">
            <div className="flex items-start gap-3 bg-green-50 border border-green-200 text-green-800 text-sm px-4 py-3.5 rounded-xl">
              <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
              <span>
                If an account with <strong>{email}</strong> exists, we sent a reset link. Check your
                inbox — it may take a minute or two to arrive. The link expires after {RESET_TOKEN_EXPIRE_HOURS} hour{RESET_TOKEN_EXPIRE_HOURS !== 1 ? "s" : ""}.
              </span>
            </div>
            <Link
              to="/login"
              className="block w-full text-center bg-green-800 hover:bg-green-700 text-white font-semibold py-3 rounded-xl transition-colors shadow-sm"
            >
              Back to sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                Email address
              </label>
              <input
                id="email"
                type="email"
                placeholder="you@example.com"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full border border-gray-300 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-transparent transition-shadow"
              />
            </div>

            {error && (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-sm px-3.5 py-2.5 rounded-xl">
                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                </svg>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-green-800 hover:bg-green-700 disabled:opacity-50 text-white font-semibold py-3 rounded-xl transition-colors shadow-sm"
            >
              {loading ? "Sending…" : "Send reset link"}
            </button>
          </form>
        )}
      </div>

      {/* Footer */}
      <p className="relative mt-6 text-sm text-green-400">
        Remember your password?{" "}
        <Link to="/login" className="text-white font-medium hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
