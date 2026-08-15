/**
 * ClearableInput — a text input with an "X" clear button when non-empty.
 *
 * Drop-in replacement for <input type="text" /> — passes all props through.
 * The clear button appears inside the input on the right side.
 */

import { forwardRef } from "react";

interface ClearableInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  onClear: () => void;
}

export const ClearableInput = forwardRef<HTMLInputElement, ClearableInputProps>(
  function ClearableInput({ onClear, value, className, ...rest }, ref) {
    const hasValue = typeof value === "string" && value.length > 0;
    return (
      <div className="relative">
        <input
          ref={ref}
          type="text"
          value={value}
          className={`${className ?? ""} ${hasValue ? "pr-8" : ""}`}
          {...rest}
        />
        {hasValue && (
          <button
            type="button"
            onClick={onClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 w-5 h-5 flex items-center justify-center rounded-full text-ink-400 hover:text-ink-600 hover:bg-ink-100 transition-colors"
            aria-label="Clear search"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
    );
  }
);
