/**
 * PrivacyPolicy — self-hosted privacy policy page.
 *
 * The policy HTML is served from /privacy-policy.html and rendered
 * in a full-height iframe. To update, replace the HTML file in frontend/public/.
 *
 * Route: /privacy
 */

import { useEffect } from "react";
import { Link } from "react-router-dom";
import { FlagIcon } from "../components/FlagIcon";

export function PrivacyPolicy() {
  useEffect(() => {
    document.title = "Privacy Policy — League Caddie";
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-4 py-3">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-green-800 font-bold text-lg">
            <FlagIcon className="w-5 h-5" />
            League Caddie
          </Link>
          <Link to="/" className="text-sm text-gray-500 hover:text-gray-700">
            Back to site
          </Link>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-8">
        <iframe
          src="/privacy-policy.html"
          title="Privacy Policy"
          className="w-full border-0 rounded-2xl bg-white"
          style={{ minHeight: "80vh" }}
          onLoad={(e) => {
            const iframe = e.target as HTMLIFrameElement;
            try {
              const height = iframe.contentDocument?.body.scrollHeight;
              if (height) {
                iframe.style.height = `${height + 40}px`;
              }
            } catch {
              // Cross-origin — keep minHeight fallback
            }
          }}
        />
      </div>
    </div>
  );
}
