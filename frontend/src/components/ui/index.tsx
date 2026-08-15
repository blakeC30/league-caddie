/**
 * Pairings Sheet primitives.
 *
 * The shared vocabulary for the app's surfaces. Every one of these is
 * specified in frontend/DESIGN.md — read §6 before changing one, and add the
 * token there before inventing a value here.
 *
 * The rule these enforce: separation comes from whitespace, the page→sheet
 * background step, and horizontal rules — in that order — before anything
 * gets a box drawn around it.
 */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";

/* ── Button ──────────────────────────────────────────────────────────────── */

type Variant = "primary" | "secondary" | "ghost" | "destructive";
type Size = "sm" | "md";

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-fairway-700 text-white hover:bg-fairway-600 active:bg-fairway-800 disabled:hover:bg-fairway-700",
  secondary:
    "bg-sheet text-ink-900 border border-ink-200 hover:border-ink-400 active:bg-ink-50 disabled:hover:border-ink-200",
  ghost: "text-ink-700 hover:bg-ink-100 active:bg-ink-200",
  destructive: "text-flag-600 hover:bg-flag-100 active:bg-flag-100",
};

const SIZE: Record<Size, string> = {
  sm: "text-small px-3 py-1.5",
  md: "text-ui px-4 py-2.5",
};

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-xs font-medium " +
  "transition-colors duration-[120ms] ease-board " +
  "disabled:opacity-40 disabled:cursor-not-allowed";

function buttonClass(variant: Variant, size: Size, className = "") {
  return `${BUTTON_BASE} ${VARIANT[variant]} ${SIZE[size]} ${className}`;
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...rest
}: ButtonProps) {
  return <button className={buttonClass(variant, size, className)} {...rest} />;
}

/** A Link styled as a Button — same states, correct semantics for navigation. */
export function ButtonLink({
  to,
  variant = "primary",
  size = "md",
  className,
  children,
}: {
  to: string;
  variant?: Variant;
  size?: Size;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link to={to} className={buttonClass(variant, size, className)}>
      {children}
    </Link>
  );
}

/* ── Panel ───────────────────────────────────────────────────────────────── */

/**
 * A sheet lying on the page. Borderless by design — the 4% lightness step
 * between `page` and `sheet` does the separating.
 */
export function Panel({
  children,
  className = "",
  flush = false,
}: {
  children: ReactNode;
  /** Drop the internal padding — for tables and full-bleed content. */
  flush?: boolean;
  className?: string;
}) {
  return (
    <div
      className={`bg-sheet rounded-sm shadow-sheet ${flush ? "" : "p-4 sm:p-6"} ${className}`}
    >
      {children}
    </div>
  );
}

/** Section heading sitting on a rule. Replaces the old icon-badge + kicker pair. */
export function SectionHeading({
  children,
  action,
  className = "",
}: {
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex items-baseline justify-between gap-4 border-b border-ink-200 pb-2 mb-4 ${className}`}
    >
      <h2 className="text-heading text-ink-950">{children}</h2>
      {action}
    </div>
  );
}

/** Page title. One per page — the app's single largest type on a screen. */
export function PageHeader({
  title,
  meta,
  action,
}: {
  title: ReactNode;
  /** A short factual line — dates, member count. Not a marketing subtitle. */
  meta?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="text-title text-ink-950 truncate">{title}</h1>
        {meta && <p className="text-small text-ink-500 mt-1">{meta}</p>}
      </div>
      {action}
    </div>
  );
}

/* ── Board band ──────────────────────────────────────────────────────────── */

/**
 * The painted leaderboard. Square corners, flat colour, white display type.
 * This replaces every gradient header band the app used to carry.
 */
export function Board({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`bg-fairway-900 text-white px-4 py-4 sm:px-6 ${className}`}>
      {children}
    </div>
  );
}

/* ── Chip ────────────────────────────────────────────────────────────────── */

type Tone = "default" | "live" | "multiplier" | "muted" | "onBoard";

const TONE: Record<Tone, string> = {
  default: "border border-ink-300 text-ink-600",
  muted: "border border-ink-200 text-ink-400",
  live: "bg-flag-600 text-white",
  multiplier: "bg-brass-100 text-brass-700",
  onBoard: "border border-white/25 text-white/80",
};

export function Chip({
  children,
  tone = "default",
  className = "",
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-xs px-1.5 py-0.5 text-micro uppercase whitespace-nowrap ${TONE[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/* ── Figure ──────────────────────────────────────────────────────────────── */

/** A headline number with its label. The scoreboard's basic unit. */
export function Figure({
  label,
  value,
  sub,
  tone = "ink",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "ink" | "fairway" | "flag" | "onBoard";
}) {
  const valueTone = {
    ink: "text-ink-950",
    fairway: "text-fairway-700",
    flag: "text-flag-600",
    onBoard: "text-white",
  }[tone];
  const labelTone = tone === "onBoard" ? "text-fairway-400" : "text-ink-500";
  return (
    <div>
      <p className={`text-micro uppercase ${labelTone}`}>{label}</p>
      <p
        className={`font-display text-figure tabular-nums mt-1 ${valueTone}`}
      >
        {value}
      </p>
      {sub && (
        <p className={`text-small mt-0.5 ${labelTone}`}>{sub}</p>
      )}
    </div>
  );
}

/* ── Empty state ─────────────────────────────────────────────────────────── */

/**
 * A rule, a plain sentence, one action. No illustration and no centred icon
 * in a rounded square — DESIGN.md §6.
 */
export function Empty({
  children,
  action,
}: {
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="border-t border-ink-200 py-8">
      <p className="text-body text-ink-500 max-w-prose">{children}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/* ── Field ───────────────────────────────────────────────────────────────── */

const INPUT_CLASS =
  "w-full bg-sheet border border-ink-200 rounded-xs px-3 py-2.5 text-body text-ink-950 " +
  "placeholder:text-ink-400 transition-colors duration-[120ms] ease-board " +
  "hover:border-ink-300 disabled:opacity-40 disabled:cursor-not-allowed";

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-micro uppercase text-ink-500">{label}</span>
      <div className="mt-1.5">{children}</div>
      {/* Error never travels by colour alone. */}
      {error ? (
        <span className="block text-small text-flag-600 mt-1.5">{error}</span>
      ) : (
        hint && <span className="block text-small text-ink-500 mt-1.5">{hint}</span>
      )}
    </label>
  );
}

export function Input({
  className = "",
  invalid = false,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={`${INPUT_CLASS} ${invalid ? "border-flag-600" : ""} ${className}`}
      {...rest}
    />
  );
}

export { INPUT_CLASS };

/* ── Rule ────────────────────────────────────────────────────────────────── */

/** The app's signature separator. A rule divides; it does not enclose. */
export function Rule({ className = "" }: { className?: string }) {
  return <hr className={`border-0 border-t border-ink-200 ${className}`} />;
}
