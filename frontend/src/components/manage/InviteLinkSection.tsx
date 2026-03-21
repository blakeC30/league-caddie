import { useEffect, useRef, useState } from "react";
import type { League } from "../../api/endpoints";
import { SectionIcon } from "./shared";

export interface InviteLinkSectionProps {
  league: League;
}

export function InviteLinkSection({ league }: InviteLinkSectionProps) {
  const [linkCopied, setLinkCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => () => clearTimeout(timerRef.current), []);

  function copyInviteLink() {
    const url = `${window.location.origin}/join/${league.invite_code}`;
    navigator.clipboard.writeText(url).then(() => {
      setLinkCopied(true);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setLinkCopied(false), 2000);
    });
  }

  return (
    <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
      <div className="flex items-center gap-3">
        <SectionIcon>
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
          </svg>
        </SectionIcon>
        <h2 className="text-base font-bold text-gray-900">Invite Link</h2>
      </div>
      <p className="text-sm text-gray-500">
        Share this link to let people request to join your league.
        As league manager, you'll approve or deny requests below.
      </p>
      <div className="bg-gray-50 border border-gray-200 rounded-xl overflow-hidden divide-y divide-gray-200">
        {/* Full invite URL */}
        <div className="flex items-center gap-3 px-4 py-3">
          <span className="text-gray-700 flex-1 truncate font-mono text-xs">
            {window.location.origin}/join/{league.invite_code}
          </span>
          <button
            onClick={copyInviteLink}
            className={`flex-shrink-0 text-sm font-semibold px-4 py-1.5 rounded-lg border transition-colors ${
              linkCopied
                ? "bg-green-50 border-green-300 text-green-700"
                : "border-gray-300 text-gray-700 hover:border-green-400 hover:text-green-700"
            }`}
          >
            {linkCopied ? "✓ Copied!" : "Copy link"}
          </button>
        </div>
        {/* Bare join code */}
        <div className="flex items-center gap-3 px-4 py-2.5">
          <span className="text-xs text-gray-400">Join code</span>
          <span className="font-mono text-sm font-semibold text-gray-800 tracking-wider">
            {league.invite_code}
          </span>
        </div>
      </div>
    </section>
  );
}
