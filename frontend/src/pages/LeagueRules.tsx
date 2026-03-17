/**
 * LeagueRules — read-only rules and league configuration page.
 *
 * Two sections:
 *   1. "League Settings" — the manager's specific choices for this league
 *      (no-pick penalty, playoff size, draft style, picks per round). Read-only
 *      for all members; managers can change these in Manage League.
 *   2. "How It Works" — the general game rules that apply to every league.
 *      Playoff rules are only shown when playoffs are enabled for this league.
 */

import { useParams } from "react-router-dom";
import { useLeague } from "../hooks/useLeague";
import { usePlayoffConfig } from "../hooks/usePlayoff";

// ---------------------------------------------------------------------------
// Presentational helpers
// ---------------------------------------------------------------------------

function SettingCard({
  label,
  value,
  note,
}: {
  label: string;
  value: React.ReactNode;
  note?: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5">
      <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-2">{label}</p>
      <div className="text-lg font-bold text-gray-900">{value}</div>
      {note && <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">{note}</p>}
    </div>
  );
}

function PlayoffDetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between items-start gap-4 py-2.5 border-t border-gray-100 first:border-t-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className="text-sm font-semibold text-gray-900 text-right">{value}</span>
    </div>
  );
}

function RuleSection({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <div className="w-8 h-8 rounded-xl bg-green-100 text-green-700 flex items-center justify-center flex-shrink-0">
          {icon}
        </div>
        <h3 className="font-bold text-gray-900">{title}</h3>
      </div>
      <ul className="space-y-2.5 pl-11">{children}</ul>
    </div>
  );
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-2.5">
      <span className="mt-2 w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
      <span className="text-sm text-gray-600 leading-relaxed">{children}</span>
    </li>
  );
}

function InfoBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-4 flex gap-3">
      <svg className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
      </svg>
      <p className="text-sm text-amber-800">{children}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

function fmtPenalty(penalty: number): string {
  const abs = Math.abs(Math.round(penalty));
  return `-$${abs.toLocaleString()}`;
}

function fmtDraftStyle(style: string): string {
  if (style === "snake") return "Snake draft";
  if (style === "linear") return "Linear draft";
  if (style === "top_seed_priority") return "Top seed priority";
  return style;
}

function fmtPicksPerRound(arr: number[]): string {
  if (arr.length === 0) return "—";
  const all = arr.every((v) => v === arr[0]);
  if (all) return `${arr[0]} pick${arr[0] === 1 ? "" : "s"} per round`;
  return arr.map((v, i) => `Round ${i + 1}: ${v}`).join(", ");
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function LeagueRules() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { data: league } = useLeague(leagueId!);
  const { data: playoffConfig } = usePlayoffConfig(leagueId!);

  const playoffsEnabled =
    playoffConfig && playoffConfig.is_enabled && playoffConfig.playoff_size > 0;

  return (
    <div className="space-y-10 pb-4">
      {/* Page header */}
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700 mb-1">
          League Rules
        </p>
        <h1 className="text-3xl font-bold text-gray-900">{league?.name ?? "…"}</h1>
        <p className="text-sm text-gray-500 mt-1">
          How this league is configured and how the game works.
        </p>
      </div>

      {/* ── Section 1: League Settings ─────────────────────────────────── */}
      <div>
        <h2 className="text-lg font-bold text-gray-900 mb-4">League Settings</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {/* No-pick penalty */}
          <SettingCard
            label="No-pick penalty"
            value={league ? fmtPenalty(league.no_pick_penalty) : "…"}
            note="Applied to your total when the pick window closes for a tournament and you have no pick on record."
          />

          {/* Playoffs */}
          {playoffsEnabled ? (
            <div className="bg-white rounded-2xl border border-gray-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400">Playoffs</p>
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-green-700 bg-green-50 px-2 py-0.5 rounded-full border border-green-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                  Enabled
                </span>
              </div>
              <PlayoffDetailRow
                label="Qualifier spots"
                value={`Top ${playoffConfig.playoff_size} players`}
              />
              <PlayoffDetailRow
                label="Draft style"
                value={fmtDraftStyle(playoffConfig.draft_style)}
              />
              <PlayoffDetailRow
                label="Picks per round"
                value={fmtPicksPerRound(playoffConfig.picks_per_round)}
              />
            </div>
          ) : (
            <SettingCard
              label="Playoffs"
              value={<span className="text-gray-400 text-base">Disabled</span>}
              note="The league manager can enable playoffs from the Manage League page."
            />
          )}
        </div>
      </div>

      {/* ── Section 2: General Rules ───────────────────────────────────── */}
      <div>
        <h2 className="text-lg font-bold text-gray-900 mb-6">How It Works</h2>
        <div className="space-y-8">

          <RuleSection
            title="Scoring"
            icon={
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
            }
          >
            <Bullet>
              <strong>Points = golfer's tournament earnings × tournament multiplier.</strong>{" "}
              Your score for a week is exactly how much money your picked golfer earned at that tournament, multiplied by any bonus the manager applied.
            </Bullet>
            <Bullet>
              The multiplier is <strong>1×</strong> by default. Featured events may be set to <strong>1.5×</strong> or <strong>2×</strong> — a badge on each tournament card shows the active multiplier.
            </Bullet>
            <Bullet>
              Points accumulate across every tournament in the season. The player with the <strong>most total points at season end wins</strong>.
            </Bullet>
            <Bullet>
              <strong>Tie-breaking</strong> (applied in order when totals are equal): first by <strong>most picks submitted</strong> that season; then by <strong>highest single-tournament score</strong>; finally by <strong>earliest league join date</strong>.
            </Bullet>
          </RuleSection>

          <RuleSection
            title="Weekly Picks"
            icon={
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
              </svg>
            }
          >
            <Bullet>
              Each week you pick <strong>one golfer</strong> competing in that week's tournament. Points are awarded when the tournament completes, based on the scoring formula above.
            </Bullet>
            <Bullet>
              <strong>No-repeat rule:</strong> once you use a golfer during the regular season, that golfer is unavailable to you for the rest of the season. Plan ahead — saving elite golfers for high-value tournaments is part of the strategy.
            </Bullet>
            <Bullet>
              <strong>Field eligibility:</strong> once the official tournament field is published, you can only pick golfers entered in that week's field. Before the field is released, any golfer on tour can be selected — giving early pickers more flexibility, but also more uncertainty about who's actually playing.
            </Bullet>
            <Bullet>
              The pick window for a tournament <strong>opens after the current week's tournament ends and official earnings are confirmed</strong>. Picks for next week are not accepted while a tournament is in progress.
            </Bullet>
          </RuleSection>

          <RuleSection
            title="Team Tournaments"
            icon={
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z" />
              </svg>
            }
          >
            <Bullet>
              Some PGA Tour events — like the Zurich Classic — are played in a <strong>two-person team format</strong>. These are marked with a <strong>Teams</strong> badge in the app.
            </Bullet>
            <Bullet>
              <strong>Earnings are the team's full prize money.</strong> Points for your pick are calculated on the team's total earnings (× tournament multiplier) — the same as any individual event.
            </Bullet>
            <Bullet>
              You pick <strong>one individual golfer</strong> from the field — you do not pick a team. Either partner from a team can be selected independently, and they will each score based on the team's total earnings.
            </Bullet>
            <Bullet>
              <strong>The no-repeat rule applies to team events.</strong> If you use a golfer who played in a team tournament, that golfer is unavailable to you for the rest of the regular season — the same as any individual event.
            </Bullet>
          </RuleSection>

          <RuleSection
            title="Pick Deadline & Locking"
            icon={
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
              </svg>
            }
          >
            <Bullet>
              Your pick <strong>locks when your chosen golfer's Round 1 tee time passes</strong>. Once they tee off, you cannot change your pick — even if they withdraw mid-round. If tee times haven't been announced yet, your pick locks at the tournament's <strong>start date</strong> — don't wait for tee times to be published if the event is approaching.
            </Bullet>
            <Bullet>
              <strong>Late scratch protection:</strong> if your golfer withdraws before teeing off, the lock does not trigger at their scheduled tee time. You can switch to any golfer who hasn't teed off yet.
            </Bullet>
            <Bullet>
              <strong>Missed the deadline?</strong> You can still pick a golfer whose Round 1 tee time hasn't passed — even after the tournament has started. Once every golfer in the field has teed off, the pick window closes permanently.
            </Bullet>
            <Bullet>
              No picks or changes are accepted for completed tournaments under any circumstances.
            </Bullet>
          </RuleSection>

          <RuleSection
            title="No-Pick Penalty"
            icon={
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
              </svg>
            }
          >
            <Bullet>
              If the pick window closes and you have no pick on record, a penalty of{" "}
              <strong>{league ? fmtPenalty(league.no_pick_penalty) : "…"}</strong> is added to your total.
            </Bullet>
            <Bullet>
              Submitting a late pick (after the tournament starts but before the last Round 1 tee time) avoids the penalty entirely.
            </Bullet>
            <Bullet>
              The penalty only appears in standings once the tournament completes — it is not shown while a tournament is in progress.
            </Bullet>
          </RuleSection>

          <RuleSection
            title="Pick Visibility"
            icon={
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.964-7.178Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
              </svg>
            }
          >
            <Bullet>
              <strong>Your own pick is always visible</strong> to you immediately after submitting.
            </Bullet>
            <Bullet>
              <strong>Other members' picks are hidden</strong> until every golfer in the field has teed off on Round 1. This prevents copying — picks only become public once the window is permanently closed.
            </Bullet>
          </RuleSection>

        </div>
      </div>

      {/* ── Section 3: Playoffs (only when enabled) ────────────────────── */}
      {playoffsEnabled && (
        <div>
          <h2 className="text-lg font-bold text-gray-900 mb-4">Playoffs</h2>
          <div className="space-y-6">
            <InfoBox>
              This league has playoffs enabled. The top{" "}
              <strong>{playoffConfig.playoff_size} players</strong> by regular season standings will qualify.
            </InfoBox>

            <div className="space-y-8">
              <RuleSection
                title="Qualification & Format"
                icon={
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 0 1-.982-3.172M9.497 14.25a7.454 7.454 0 0 0 .981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 0 0 7.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M7.73 9.728a6.726 6.726 0 0 0 2.748 1.35m8.272-6.842V4.5c0 2.108-.966 3.99-2.48 5.228m2.48-5.492a46.32 46.32 0 0 1 2.916.52 6.003 6.003 0 0 1-5.395 4.972m0 0a6.726 6.726 0 0 1-2.749 1.35m0 0a6.772 6.772 0 0 1-3.044 0" />
                  </svg>
                }
              >
                <Bullet>
                  The top <strong>{playoffConfig.playoff_size} players</strong> by regular season standings qualify. Seeding is automatic once the regular season ends — no manager action required.
                </Bullet>
                <Bullet>
                  Players are placed into <strong>pods</strong> (matchup groups). The highest-scoring member of each pod advances to the next round; all others are eliminated. Ties are broken by regular season seed (lower seed wins).
                </Bullet>
                <Bullet>
                  The playoff bracket spans the last tournaments in the league's schedule — those events are reserved as playoff rounds.
                </Bullet>
              </RuleSection>

              <RuleSection
                title="Playoff Picks — Preference List"
                icon={
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 6.75h12M8.25 12h12m-12 5.25h12M3.75 6.75h.007v.008H3.75V6.75Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0ZM3.75 12h.007v.008H3.75V12Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm-.375 5.25h.007v.008H3.75v-.008Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />
                  </svg>
                }
              >
                <Bullet>
                  Instead of picking one golfer, you submit a <strong>ranked preference list</strong> before each playoff tournament. The system assigns your picks automatically from your rankings when the tournament begins.
                </Bullet>
                <Bullet>
                  Picks are assigned <strong>within your pod only</strong> — two members in the same pod cannot be assigned the same golfer. Assignment follows the{" "}
                  <strong>{fmtDraftStyle(playoffConfig.draft_style).toLowerCase()}</strong> order configured for this league.
                </Bullet>
                <Bullet>
                  You must rank enough golfers to cover all pick slots in your pod ({fmtPicksPerRound(playoffConfig.picks_per_round)}, × pod size). This ensures coverage if your top choices are taken.
                </Bullet>
                <Bullet>
                  <strong>No no-repeat rule in playoffs.</strong> Any golfer may be ranked regardless of whether you used them in the regular season.
                </Bullet>
              </RuleSection>

              <RuleSection
                title="Playoff Pick Deadline"
                icon={
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                  </svg>
                }
              >
                <Bullet>
                  You can submit and update your preference list as soon as the bracket is seeded (Round 1) or as soon as the previous round's results are finalized (subsequent rounds).
                </Bullet>
                <Bullet>
                  The preference list <strong>locks when the very first Round 1 tee time of the playoff tournament passes</strong> — unlike the regular season, the lock is tied to the field's first tee time, not your specific golfer's.
                </Bullet>
                <Bullet>
                  Failing to submit a preference list before the deadline results in a{" "}
                  <strong>{league ? fmtPenalty(league.no_pick_penalty) : "…"} penalty per unresolved pick slot</strong>.
                </Bullet>
              </RuleSection>

              <RuleSection
                title="Playoff Scoring"
                icon={
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="m3.75 13.5 10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75Z" />
                  </svg>
                }
              >
                <Bullet>
                  Scoring uses the same formula as the regular season:{" "}
                  <strong>earnings × tournament multiplier</strong>. Any multiplier the manager set for a playoff tournament applies here too.
                </Bullet>
                <Bullet>
                  A round cannot be scored until official earnings are published — incomplete data is never locked in.
                </Bullet>
                <Bullet>
                  Once a round is scored, the next round's preference window opens automatically for the advancing members.
                </Bullet>

              </RuleSection>

              <RuleSection
                title="Member Departures"
                icon={
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
                  </svg>
                }
              >
                <Bullet>
                  <strong>Before the regular season ends:</strong> if a member leaves, the playoff bracket automatically shrinks to the largest valid size (2, 4, 8, 16…) that fits the remaining members. If fewer than 2 members remain, playoffs are disabled entirely.
                </Bullet>
                <Bullet>
                  <strong>After the regular season ends</strong> (schedule locked): the bracket size stays the same. The departed member's slot becomes a <strong>bye</strong> — it can never advance or win. Their pending picks and preference lists are cleared; all past round results are preserved and permanent.
                </Bullet>
              </RuleSection>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
