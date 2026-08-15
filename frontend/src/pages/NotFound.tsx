import { useEffect } from "react";
import { Link } from "react-router-dom";
import { FlagIcon } from "../components/FlagIcon";

export function NotFound() {
  useEffect(() => {
    document.title = "Page Not Found — League Caddie";
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-ink-50 px-4">
      <div className="bg-white border border-ink-200 rounded-sm p-10 max-w-md w-full text-center shadow-sheet">
        <div className="w-12 h-12 bg-fairway-50 text-fairway-700 rounded-xs flex items-center justify-center mx-auto mb-4">
          <FlagIcon className="w-6 h-6" />
        </div>
        <h1 className="text-4xl font-bold text-ink-900 mb-2">404</h1>
        <p className="text-lg font-semibold text-ink-700 mb-2">
          Page not found
        </p>
        <p className="text-sm text-ink-500 mb-6">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <Link
          to="/"
          className="inline-block bg-fairway-700 hover:bg-fairway-700 text-white font-semibold py-3 px-6 rounded-xs shadow-sheet"
        >
          Go to home page
        </Link>
      </div>
    </div>
  );
}
