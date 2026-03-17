import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { GoogleLogin } from "@react-oauth/google";
import { useAuth } from "../hooks/useAuth";
import { FlagIcon } from "../components/FlagIcon";

export function Login() {
  const { login, loginWithGoogle } = useAuth();
  const [searchParams] = useSearchParams();
  const next = searchParams.get("next");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
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
    <div className="min-h-screen bg-gradient-to-br from-green-950 via-green-900 to-green-800 flex flex-col items-center justify-center px-4 relative overflow-hidden">
      {/* Decorative blobs */}
      <div className="absolute -top-32 -right-32 w-[500px] h-[500px] rounded-full bg-white/5 blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 -left-24 w-80 h-80 rounded-full bg-black/20 blur-3xl pointer-events-none" />

      {/* Back link */}
      <div className="relative w-full max-w-sm mb-6">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-green-400 hover:text-white transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
          </svg>
          Back to home
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
          <p className="text-2xl font-bold text-gray-900 pt-1">Welcome back</p>
          <p className="text-sm text-gray-500">Sign in to your account to continue</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              Email
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
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="password" className="text-sm font-medium text-gray-700">
                Password
              </label>
              <Link to="/forgot-password" className="text-xs text-green-700 hover:text-green-900 font-medium transition-colors">
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
            {loading ? "Signing in…" : "Sign in"}
          </button>

        </form>

        {/* Divider */}
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <hr className="flex-1 border-gray-200" />
          or continue with
          <hr className="flex-1 border-gray-200" />
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
      <p className="relative mt-6 text-sm text-green-400">
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
