import { useEffect, useState } from "react";
import type { League } from "../../api/endpoints";
import { useUpdateLeague } from "../../hooks/useLeague";
import { SectionIcon } from "./shared";

export interface LeagueSettingsSectionProps {
  league: League | undefined;
  leagueId: string;
}

export function LeagueSettingsSection({ league, leagueId }: LeagueSettingsSectionProps) {
  const updateLeague = useUpdateLeague(leagueId);
  const [settingsEditing, setSettingsEditing] = useState(false);
  const [settingsName, setSettingsName] = useState("");
  const [settingsNoPick, setSettingsNoPick] = useState("50000");
  const [settingsAutoAccept, setSettingsAutoAccept] = useState(false);
  const [autoAcceptError, setAutoAcceptError] = useState("");

  useEffect(() => {
    if (league) {
      setSettingsName(league.name);
      setSettingsNoPick(String(Math.abs(league.no_pick_penalty)));
      setSettingsAutoAccept(league.auto_accept_requests);
    }
  }, [league]);

  function handleCancelSettings() {
    if (league) {
      setSettingsName(league.name);
      setSettingsNoPick(String(Math.abs(league.no_pick_penalty)));
      setSettingsAutoAccept(league.auto_accept_requests);
    }
    setAutoAcceptError("");
    setSettingsEditing(false);
  }

  async function handleSaveSettings() {
    try {
      setAutoAcceptError("");
      await updateLeague.mutateAsync({
        name: settingsName,
        no_pick_penalty: parseInt(settingsNoPick, 10) || 0,
        auto_accept_requests: settingsAutoAccept,
      });
      setSettingsEditing(false);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to save settings";
      setAutoAcceptError(msg);
    }
  }

  return (
    <section className="bg-white rounded-sm border border-ink-200 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <SectionIcon>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
            </svg>
          </SectionIcon>
          <h2 className="text-base font-bold text-ink-900">League Settings</h2>
        </div>
        {!settingsEditing && (
          <button
            onClick={() => setSettingsEditing(true)}
            className="text-sm font-semibold text-fairway-700 hover:text-fairway-900 transition-colors"
          >
            Edit
          </button>
        )}
      </div>
      <div className="bg-ink-50 rounded-xs border border-ink-100 divide-y divide-ink-100">
        {/* Name */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-4 px-4 py-3">
          <span className="text-sm text-ink-500 sm:w-36 sm:flex-shrink-0">Name</span>
          {settingsEditing ? (
            <div className="flex-1">
              <input
                type="text"
                value={settingsName}
                onChange={(e) => setSettingsName(e.target.value)}
                maxLength={50}
                className="w-full text-sm border border-ink-300 rounded-xs px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-fairway-700"
              />
              {settingsName.length >= 40 && <p className="text-[11px] text-ink-400 text-right tabular-nums mt-0.5">{settingsName.length}/50</p>}
            </div>
          ) : (
            <span className="text-sm font-medium text-ink-900 break-words">{league?.name}</span>
          )}
        </div>
        {/* No-pick penalty */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-4 px-4 py-3">
          <span className="text-sm text-ink-500 sm:w-36 sm:flex-shrink-0">No-pick penalty</span>
          {settingsEditing ? (
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-ink-700">{"−"}</span>
              <input
                type="text"
                inputMode="numeric"
                value={settingsNoPick}
                onChange={(e) =>
                  setSettingsNoPick(e.target.value.replace(/[^0-9]/g, ""))
                }
                onBlur={() =>
                  setSettingsNoPick(String(Math.min(500000, parseInt(settingsNoPick, 10) || 0)))
                }
                className="w-36 text-sm border border-ink-300 rounded-xs px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-fairway-700"
              />
              <span className="text-xs text-ink-400">per missed pick · max $500,000</span>
            </div>
          ) : (
            <span className="text-sm font-medium text-ink-900">
              {"−"}{Math.abs(league?.no_pick_penalty ?? 0).toLocaleString()} pts
            </span>
          )}
        </div>
        {/* Auto-accept join requests */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-4 px-4 py-3">
          <span className="text-sm text-ink-500 sm:w-36 sm:flex-shrink-0">Auto-accept requests</span>
          {settingsEditing ? (
            <div className="flex items-center gap-3">
              <button
                type="button"
                role="switch"
                aria-checked={settingsAutoAccept}
                onClick={() => setSettingsAutoAccept(!settingsAutoAccept)}
                className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-fairway-500 focus:ring-offset-2 ${
                  settingsAutoAccept ? "bg-fairway-700" : "bg-ink-200"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    settingsAutoAccept ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
              <span className="text-xs text-ink-400">Automatically accept new members when they request to join</span>
            </div>
          ) : (
            <span className={`text-sm font-medium ${league?.auto_accept_requests ? "text-fairway-700" : "text-ink-400"}`}>
              {league?.auto_accept_requests ? "On" : "Off"}
            </span>
          )}
        </div>
        {autoAcceptError && (
          <p className="text-sm text-flag-600 px-4 pb-2">{autoAcceptError}</p>
        )}
      </div>
      {settingsEditing && (
        <div className="flex items-center gap-3">
          <button
            onClick={handleSaveSettings}
            disabled={updateLeague.isPending}
            className="bg-fairway-700 hover:bg-fairway-700 disabled:opacity-40 text-white font-semibold px-5 py-2 rounded-xs text-sm transition-colors"
          >
            {updateLeague.isPending ? "Saving…" : "Save Settings"}
          </button>
          <button
            onClick={handleCancelSettings}
            className="text-sm text-ink-500 hover:text-ink-700 transition-colors"
          >
            Cancel
          </button>
        </div>
      )}
    </section>
  );
}
