/**
 * TermsOfService — self-hosted terms of service page.
 *
 * The terms HTML is served from /terms-of-service.html and rendered
 * in a full-height iframe. To update, replace the HTML file in frontend/public/.
 *
 * Route: /terms
 */

import { useEffect } from "react";
import { Link } from "react-router-dom";
import { FlagIcon } from "../components/FlagIcon";

export function TermsOfService() {
  useEffect(() => {
    document.title = "Terms of Service — League Caddie";
  }, []);

  return (
    <div className="min-h-screen bg-ink-50">
      <nav className="bg-white border-b border-ink-200 px-4 py-3">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-fairway-700 font-bold text-lg">
            <FlagIcon className="w-5 h-5" />
            League Caddie
          </Link>
          <Link to="/" className="text-sm text-ink-500 hover:text-ink-700">
            Back to site
          </Link>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-8">
        <iframe
          src="/terms-of-service.html"
          title="Terms of Service"
          className="w-full border-0 rounded-sm bg-white"
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
