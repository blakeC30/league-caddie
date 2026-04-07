import { useState } from "react";
import type { LeagueMember } from "../../api/endpoints";
import { useSendLeagueEmail, useLeagueEmails } from "../../hooks/useLeague";
import { SectionIcon } from "./shared";

export interface SendEmailSectionProps {
  leagueId: string;
  members: LeagueMember[] | undefined;
}

export function SendEmailSection({ leagueId, members }: SendEmailSectionProps) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectAll, setSelectAll] = useState(true);
  const [recipientSearch, setRecipientSearch] = useState("");
  const [success, setSuccess] = useState<{ count: number } | null>(null);
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  const sendEmail = useSendLeagueEmail(leagueId);
  const { data: emailHistory } = useLeagueEmails(leagueId);

  const approved = members?.filter((m) => m.status === "approved") ?? [];
  const optedIn = approved.filter((m) => m.user.manager_emails_enabled);
  const optedOut = approved.filter((m) => !m.user.manager_emails_enabled);
  const q = recipientSearch.toLowerCase();
  const filteredOptedIn = q ? optedIn.filter((m) => m.user.display_name.toLowerCase().includes(q)) : optedIn;
  const filteredOptedOut = q ? optedOut.filter((m) => m.user.display_name.toLowerCase().includes(q)) : optedOut;

  function toggleMember(userId: string) {
    setSelectAll(false);
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  }

  function handleSelectAll() {
    if (selectAll) {
      setSelectAll(false);
      setSelectedIds(new Set());
    } else {
      setSelectAll(true);
      setSelectedIds(new Set());
    }
  }

  const recipientCount = selectAll
    ? optedIn.length
    : optedIn.filter((m) => selectedIds.has(m.user_id)).length;

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess(null);

    const recipientUserIds = selectAll
      ? [] // empty = all opted-in
      : Array.from(selectedIds);

    try {
      const result = await sendEmail.mutateAsync({
        recipient_user_ids: recipientUserIds,
        subject: subject.trim(),
        body: body.trim(),
      });
      setSuccess({ count: result.recipient_count });
      setSubject("");
      setBody("");
      setSelectAll(true);
      setSelectedIds(new Set());
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Failed to send email. Please try again.");
    }
  }

  return (
    <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
      <div className="flex items-center gap-3">
        <SectionIcon>
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
          </svg>
        </SectionIcon>
        <h2 className="text-base font-bold text-gray-900">Send Email</h2>
      </div>
      <p className="text-sm text-gray-500">
        Send an announcement to your league members. Emails are sent from
        noreply@league-caddie.com on your behalf. You can send 1 email per day.
        Members can opt out of manager emails in their account settings.
      </p>

      {success && (
        <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-700">
          Email sent to {success.count} member{success.count !== 1 ? "s" : ""}.
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      <form onSubmit={handleSend} className="space-y-4">
        {/* Recipients */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-gray-700">Recipients</label>
          {approved.length > 10 && (
            <input
              type="text"
              placeholder="Search members..."
              value={recipientSearch}
              onChange={(e) => setRecipientSearch(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            />
          )}
          <div className="border border-gray-200 rounded-xl max-h-48 overflow-y-auto divide-y divide-gray-100">
            {/* Select all toggle */}
            {!recipientSearch && (
              <label className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-gray-50">
                <input
                  type="checkbox"
                  checked={selectAll}
                  onChange={handleSelectAll}
                  className="rounded border-gray-300 text-green-700 focus:ring-green-500"
                />
                <span className="text-sm font-medium text-gray-900">
                  All members ({optedIn.length})
                </span>
              </label>
            )}
            {filteredOptedIn.map((m) => (
              <label key={m.user_id} className="flex items-center gap-3 px-4 py-2 cursor-pointer hover:bg-gray-50">
                <input
                  type="checkbox"
                  checked={selectAll || selectedIds.has(m.user_id)}
                  disabled={selectAll}
                  onChange={() => toggleMember(m.user_id)}
                  className="rounded border-gray-300 text-green-700 focus:ring-green-500 disabled:opacity-40"
                />
                <span className="text-sm text-gray-700">{m.user.display_name}</span>
              </label>
            ))}
            {filteredOptedOut.map((m) => (
              <div key={m.user_id} className="flex items-center gap-3 px-4 py-2 opacity-40">
                <input type="checkbox" disabled checked={false} className="rounded border-gray-300" />
                <span className="text-sm text-gray-400">{m.user.display_name}</span>
                <span className="text-[10px] text-gray-400 ml-auto">opted out</span>
              </div>
            ))}
            {recipientSearch && filteredOptedIn.length === 0 && filteredOptedOut.length === 0 && (
              <p className="px-4 py-3 text-sm text-gray-400 text-center">No members match your search.</p>
            )}
          </div>
        </div>

        {/* Subject */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">Subject</label>
            <span className="text-[10px] text-gray-400 tabular-nums">{subject.length}/100</span>
          </div>
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value.slice(0, 100))}
            placeholder="e.g. Season update from your manager"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            required
          />
        </div>

        {/* Body */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">Message</label>
            <span className="text-[10px] text-gray-400 tabular-nums">{body.length}/2000</span>
          </div>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value.slice(0, 2000))}
            placeholder="Write your message..."
            rows={5}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 resize-y"
            required
          />
        </div>

        <button
          type="submit"
          disabled={sendEmail.isPending || recipientCount === 0 || !subject.trim() || !body.trim()}
          className="w-full bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold py-2.5 rounded-xl transition-colors"
        >
          {sendEmail.isPending
            ? "Sending..."
            : selectAll
              ? "Send to all members"
              : `Send to ${recipientCount} member${recipientCount !== 1 ? "s" : ""}`}
        </button>
      </form>

      {/* Email history */}
      {emailHistory && emailHistory.length > 0 && (
        <div className="pt-2 border-t border-gray-100">
          <button
            type="button"
            onClick={() => setShowHistory(!showHistory)}
            className="text-xs font-medium text-gray-500 hover:text-gray-700 flex items-center gap-1"
          >
            <svg className={`w-3 h-3 transition-transform ${showHistory ? "rotate-90" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            Recent emails ({emailHistory.length})
          </button>
          {showHistory && (
            <div className="mt-2 space-y-1.5">
              {emailHistory.slice(0, 5).map((e) => (
                <div key={e.id} className="text-xs text-gray-500 flex items-center justify-between">
                  <span className="truncate mr-2">{e.subject}</span>
                  <span className="text-gray-400 flex-shrink-0">
                    {e.recipient_count} recipient{e.recipient_count !== 1 ? "s" : ""} · {new Date(e.created_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
