import { useEffect } from "react";
import { Link } from "react-router-dom";
import { FlagIcon } from "../components/FlagIcon";

export function NotFound() {
  useEffect(() => {
    document.title = "Page Not Found — League Caddie";
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="bg-white border border-gray-200 rounded-2xl p-10 max-w-md w-full text-center shadow-sm">
        <div className="w-12 h-12 bg-green-50 text-green-700 rounded-xl flex items-center justify-center mx-auto mb-4">
          <FlagIcon className="w-6 h-6" />
        </div>
        <h1 className="text-4xl font-bold text-gray-900 mb-2">404</h1>
        <p className="text-lg font-semibold text-gray-700 mb-2">
          Page not found
        </p>
        <p className="text-sm text-gray-500 mb-6">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <Link
          to="/"
          className="inline-block bg-green-800 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-xl shadow-sm"
        >
          Go to home page
        </Link>
      </div>
    </div>
  );
}
