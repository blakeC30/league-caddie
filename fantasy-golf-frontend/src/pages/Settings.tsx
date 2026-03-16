/**
 * Settings — user account settings page.
 *
 * Accessible at /settings (linked from the username pill in the nav).
 * Allows the user to update their display name and leave leagues.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { usersApi, type League } from "../api/endpoints";
import { useAuth } from "../hooks/useAuth";
import { useAuthStore } from "../store/authStore";
import { useMyLeagues, useLeaveLeague, useLeagueMembers } from "../hooks/useLeague";
import { Spinner } from "../components/Spinner";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

// Extracted so each row can call useLeagueMembers independently (hook rules).
function LeagueRow({
  league,
  userId,
  isEditing,
}: {
  league: League;
  userId: string;
  isEditing: boolean;
}) {
  const { data: members } = useLeagueMembers(league.id);
  const isManager = members?.some((m) => m.user_id === userId && m.role === "manager") ?? false;

  const { mutate: leaveLeague, isPending, error, reset } = useLeaveLeague();
  const [confirming, setConfirming] = useState(false);

  // Collapse confirmation when the parent exits edit mode.
  useEffect(() => {
    if (!isEditing) {
      setConfirming(false);
      reset();
    }
  }, [isEditing, reset]);

  if (confirming) {
    return (
      <div className="rounded-xl border border-gray-100 px-4 py-3 space-y-2">
        {error && (
          <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2 rounded-lg">
            <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
            </svg>
            Failed to leave league. Please try again.
          </div>
        )}
        <p className="text-sm text-gray-700">
          Leave <span className="font-semibold">{league.name}</span>? This cannot be undone.
        </p>
        <div className="flex items-center gap-3">
          <button
            onClick={() => leaveLeague(league.id, { onSuccess: () => setConfirming(false) })}
            disabled={isPending}
            className="text-sm font-medium bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white px-3 py-1.5 rounded-lg transition-colors"
          >
            {isPending ? "Leaving…" : "Yes, leave"}
          </button>
          <button
            onClick={() => { setConfirming(false); reset(); }}
            disabled={isPending}
            className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-100 px-4 py-3 flex items-center justify-between gap-3">
      <span className="text-sm font-medium text-gray-800">{league.name}</span>
      <div className="flex items-center gap-2 flex-shrink-0">
        {!isEditing && (
          <Link
            to={`/leagues/${league.id}/rules`}
            className="text-xs text-green-700 hover:text-green-900 border border-green-200 hover:border-green-400 px-2.5 py-1 rounded-lg transition-colors"
          >
            Rules
          </Link>
        )}
        {isEditing && (
          isManager ? (
            <span className="text-xs text-gray-400">Manager</span>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              className="text-xs text-red-500 hover:text-red-700 border border-red-200 hover:border-red-400 px-2.5 py-1 rounded-lg transition-colors"
            >
              Leave
            </button>
          )
        )}
      </div>
    </div>
  );
}

export function Settings() {
  const { user, token } = useAuth();
  const setAuth = useAuthStore((s) => s.setAuth);

  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const [remindersEnabled, setRemindersEnabled] = useState(
    user?.pick_reminders_enabled ?? true
  );
  const [remindersLoading, setRemindersLoading] = useState(false);

  const { data: leagues, isLoading: leaguesLoading } = useMyLeagues();
  const [isEditingLeagues, setIsEditingLeagues] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!displayName.trim()) return;
    setError("");
    setSaved(false);
    setLoading(true);
    try {
      const updated = await usersApi.updateMe({ display_name: displayName.trim() });
      setAuth(updated, token!);
      setSaved(true);
    } catch {
      setError("Failed to save changes. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleReminderToggle(enabled: boolean) {
    setRemindersEnabled(enabled);
    setRemindersLoading(true);
    try {
      const updated = await usersApi.updateMe({ pick_reminders_enabled: enabled });
      setAuth(updated, token!);
    } catch {
      // Revert optimistic update on failure.
      setRemindersEnabled(!enabled);
    } finally {
      setRemindersLoading(false);
    }
  }

  return (
    <div className="space-y-8 max-w-xl mx-auto">
      {/* Page header */}
      <div className="space-y-1">
        <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
          Account
        </p>
        <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
      </div>

      {/* Profile section */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-green-50 text-green-700 rounded-lg flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
            </svg>
          </div>
          <h2 className="text-base font-bold text-gray-900">Profile</h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="displayName" className="block text-sm font-medium text-gray-700">
              Display name
            </label>
            <input
              id="displayName"
              type="text"
              required
              value={displayName}
              onChange={(e) => { setDisplayName(e.target.value); setSaved(false); }}
              maxLength={40}
              className="w-full border border-gray-300 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-transparent transition-shadow"
            />
            <p className="text-xs text-gray-400">
              This is how you appear on leaderboards and pick history.
            </p>
          </div>

          {error && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-sm px-3.5 py-2.5 rounded-xl">
              <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
              </svg>
              {error}
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={loading || !displayName.trim() || displayName.trim() === user?.display_name}
              className="bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold py-2.5 px-5 rounded-xl transition-colors shadow-sm text-sm"
            >
              {loading ? "Saving…" : "Save changes"}
            </button>
            {saved && (
              <span className="inline-flex items-center gap-1.5 text-sm text-green-700 font-medium">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                </svg>
                Saved
              </span>
            )}
          </div>
        </form>
      </div>

      {/* Account info section */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-green-50 text-green-700 rounded-lg flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
            </svg>
          </div>
          <h2 className="text-base font-bold text-gray-900">Account</h2>
        </div>

        <div className="space-y-4">
          <div className="space-y-1">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Email</p>
            <p className="text-sm text-gray-700">{user?.email}</p>
            <p className="text-xs text-gray-400">Email cannot be changed.</p>
          </div>

          <div className="h-px bg-gray-100" />

          <div className="space-y-1">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Member since</p>
            <p className="text-sm text-gray-700">
              {user?.created_at ? formatDate(user.created_at) : "—"}
            </p>
          </div>
        </div>
      </div>

      {/* Email notifications section */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-green-50 text-green-700 rounded-lg flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
            </svg>
          </div>
          <h2 className="text-base font-bold text-gray-900">Email Notifications</h2>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div className="space-y-0.5 flex-1">
            <p className="text-sm font-medium text-gray-800">
              Weekly pick reminders
            </p>
            <p className="text-xs text-gray-400 leading-relaxed">
              Remind me every Wednesday before a tournament to submit my pick.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={remindersEnabled}
            disabled={remindersLoading}
            onClick={() => handleReminderToggle(!remindersEnabled)}
            className={`relative flex-shrink-0 inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-green-600 focus:ring-offset-2 disabled:opacity-50 ${
              remindersEnabled ? "bg-green-700" : "bg-gray-300"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                remindersEnabled ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
        </div>
      </div>

      {/* Leagues section */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-green-50 text-green-700 rounded-lg flex items-center justify-center flex-shrink-0">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z" />
              </svg>
            </div>
            <h2 className="text-base font-bold text-gray-900">My Leagues</h2>
          </div>
          {leagues?.length ? (
            isEditingLeagues ? (
              <button
                onClick={() => setIsEditingLeagues(false)}
                className="text-sm font-medium text-green-700 hover:text-green-900 transition-colors"
              >
                Done
              </button>
            ) : (
              <button
                onClick={() => setIsEditingLeagues(true)}
                className="text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
              >
                Edit
              </button>
            )
          ) : null}
        </div>

        {leaguesLoading ? (
          <div className="flex justify-center py-4"><Spinner /></div>
        ) : !leagues?.length ? (
          <p className="text-sm text-gray-500">You are not a member of any leagues.</p>
        ) : (
          <div className="space-y-2">
            {leagues.map((league) => (
              <LeagueRow
                key={league.id}
                league={league}
                userId={user!.id}
                isEditing={isEditingLeagues}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
