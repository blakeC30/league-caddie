"""
Email service — sends transactional emails via Resend.

In local development, RESEND_API_KEY is empty. Emails are logged to the
console but not sent, so developers can copy the reset URL from the logs.

In production, set RESEND_API_KEY in the environment (Helm secret).
The domain (league-caddie.com) must be verified in the Resend dashboard.
"""

import logging

import resend

from app.config import settings

log = logging.getLogger(__name__)


def _send(to: str, subject: str, html: str, text: str) -> None:
    """Send an email via Resend, or log-only if no API key is configured."""
    if not settings.RESEND_API_KEY:
        log.info("Email not sent (no RESEND_API_KEY): to=%s subject=%r", to, subject)
        return

    resend.api_key = settings.RESEND_API_KEY
    resend.Emails.send(
        {
            "from": settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        }
    )


def send_password_reset_email(to_email: str, raw_token: str) -> None:
    """
    Send a password reset email to the given address.

    The raw token (not its hash) is embedded in the reset URL. The link is
    also logged at INFO level so it's easy to test locally without real email.
    """
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"

    # Always log the URL — essential for local dev where no email is delivered.
    log.info("Password reset URL for %s: %s", to_email, reset_url)

    text_body = (
        "You requested a password reset for your League Caddie account.\n\n"
        f"Click the link below to set a new password (expires in {settings.RESET_TOKEN_EXPIRE_HOURS} hour(s)):\n\n"
        f"{reset_url}\n\n"
        "If you didn't request this, you can safely ignore this email.\n"
    )

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Reset your League Caddie password</title>
</head>
<body style="margin:0;padding:0;background-color:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f3f4f6;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="100%" style="max-width:520px;background-color:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

          <!-- Header — matches Login/Register page gradient -->
          <tr>
            <td style="background:linear-gradient(to bottom right,#052e16,#14532d,#166534);padding:36px 40px;text-align:center;">
              <span style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.3px;">League Caddie</span>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 32px;">
              <!-- Eyebrow label — matches text-xs font-bold uppercase tracking-[0.15em] text-green-700 -->
              <p style="margin:0 0 8px;font-size:11px;font-weight:700;letter-spacing:0.15em;text-transform:uppercase;color:#15803d;">Password Reset</p>
              <h1 style="margin:0 0 16px;font-size:26px;font-weight:700;color:#111827;line-height:1.25;">Reset your password</h1>
              <p style="margin:0 0 28px;font-size:15px;color:#6b7280;line-height:1.6;">
                We received a request to reset the password for your League Caddie account.
                Click the button below to choose a new password. This link expires in <strong style="color:#111827;">{settings.RESET_TOKEN_EXPIRE_HOURS}&nbsp;hour(s)</strong>.
              </p>

              <!-- CTA button — matches bg-green-800 hover:bg-green-700 font-semibold py-3 px-6 rounded-xl -->
              <table cellpadding="0" cellspacing="0" style="margin:0 auto 28px;">
                <tr>
                  <td style="background-color:#166534;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.12);">
                    <a href="{reset_url}"
                       style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:12px;">
                      Reset password
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 6px;font-size:13px;color:#9ca3af;">Or copy and paste this link into your browser:</p>
              <p style="margin:0 0 28px;font-size:12px;word-break:break-all;">
                <a href="{reset_url}" style="color:#166534;text-decoration:none;">{reset_url}</a>
              </p>

              <!-- Divider -->
              <hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 24px;" />

              <p style="margin:0;font-size:13px;color:#9ca3af;line-height:1.5;">
                If you didn't request a password reset, you can safely ignore this email — your password won't change.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color:#f9fafb;border-top:1px solid #e5e7eb;padding:20px 40px;text-align:center;">
              <p style="margin:0;font-size:12px;color:#9ca3af;">
                &copy; 2026 League Caddie &nbsp;&middot;&nbsp; You're receiving this because a reset was requested for your account.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    _send(to_email, "Reset your League Caddie password", html_body, text_body)


def send_pick_reminder_email(
    to_email: str,
    display_name: str,
    unpicked: list[dict],
) -> None:
    """
    Send a consolidated weekly pick reminder listing all unpicked leagues.

    ``unpicked`` is a list of dicts, each with:
      - league_name, league_id, tournament_name, start_date, pick_window_open

    One email per user regardless of how many leagues/tournaments they need.
    """
    log.info(
        "Pick reminder for %s — %d unpicked league(s)",
        to_email,
        len(unpicked),
    )

    frontend = settings.FRONTEND_URL.rstrip("/")
    settings_url = f"{frontend}/settings"

    # Subject uses the first tournament name for brevity.
    first = unpicked[0]
    subject = (
        f"Pick reminder: {first['tournament_name']} starts {first['start_date']}"
        if len(unpicked) == 1
        else f"Pick reminder: {len(unpicked)} picks needed this week"
    )

    # ── Plain text body ──────────────────────────────────────────────
    lines = [f"Hi {display_name},\n"]
    if len(unpicked) == 1:
        u = unpicked[0]
        lines.append(
            f"You haven't submitted your pick for {u['tournament_name']} "
            f"({u['start_date']}) in {u['league_name']} yet.\n"
        )
        if u["pick_window_open"]:
            pick_url = f"{settings.FRONTEND_URL}/leagues/{u['league_id']}/pick"
            lines.append(f"Submit your pick: {pick_url}\n")
    else:
        lines.append("You have upcoming picks to make:\n")
        for u in unpicked:
            line = f"  • {u['league_name']} — {u['tournament_name']} ({u['start_date']})"
            if u["pick_window_open"]:
                line += f"  {settings.FRONTEND_URL}/leagues/{u['league_id']}/pick"
            lines.append(line)
        lines.append("")

    lines.append(
        "To stop receiving pick reminders, visit "
        f"{settings_url} and turn off email notifications.\n"
    )
    text_body = "\n".join(lines)

    # ── HTML body ────────────────────────────────────────────────────
    if len(unpicked) == 1:
        u = unpicked[0]
        pick_url = f"{settings.FRONTEND_URL}/leagues/{u['league_id']}/pick"
        detail_html = f"""
              <p style="margin:0 0 24px;font-size:15px;color:#6b7280;line-height:1.6;">
                You haven't submitted your pick for
                <strong style="color:#111827;">{u["tournament_name"]}</strong>
                (starts <strong style="color:#111827;">{u["start_date"]}</strong>)
                in <strong style="color:#111827;">{u["league_name"]}</strong> yet.
              </p>"""
        if u["pick_window_open"]:
            cta_html = f"""
              <table cellpadding="0" cellspacing="0" style="margin:0 auto 28px;">
                <tr>
                  <td style="background-color:#166534;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.12);">
                    <a href="{pick_url}"
                       style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:12px;">
                      Submit your pick &rarr;
                    </a>
                  </td>
                </tr>
              </table>"""
        else:
            cta_html = """
              <div style="background-color:#fefce8;border:1px solid #fde68a;border-radius:10px;padding:16px 20px;margin-bottom:28px;">
                <p style="margin:0;font-size:14px;color:#92400e;line-height:1.5;">
                  <strong>Picks not open yet.</strong> The pick window opens once the current
                  tournament finishes and earnings are posted.
                </p>
              </div>"""
    else:
        rows_html = ""
        for u in unpicked:
            pick_url = f"{settings.FRONTEND_URL}/leagues/{u['league_id']}/pick"
            if u["pick_window_open"]:
                action = (
                    f'<a href="{pick_url}" style="color:#166534;font-weight:600;'
                    f'text-decoration:none;">Pick now &rarr;</a>'
                )
            else:
                action = '<span style="color:#92400e;font-size:12px;">Opens soon</span>'
            rows_html += f"""
                <tr>
                  <td style="padding:10px 0;border-bottom:1px solid #f3f4f6;">
                    <p style="margin:0 0 2px;font-size:14px;font-weight:600;color:#111827;">{u["league_name"]}</p>
                    <p style="margin:0;font-size:13px;color:#6b7280;">{u["tournament_name"]} &middot; {u["start_date"]}</p>
                  </td>
                  <td style="padding:10px 0;border-bottom:1px solid #f3f4f6;text-align:right;vertical-align:middle;">
                    {action}
                  </td>
                </tr>"""

        detail_html = f"""
              <p style="margin:0 0 20px;font-size:15px;color:#6b7280;line-height:1.6;">
                You have <strong style="color:#111827;">{len(unpicked)} picks</strong> to make this week:
              </p>
              <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
                {rows_html}
              </table>"""
        cta_html = ""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Pick reminder</title>
</head>
<body style="margin:0;padding:0;background-color:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f3f4f6;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="100%" style="max-width:520px;background-color:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(to bottom right,#052e16,#14532d,#166534);padding:36px 40px;text-align:center;">
              <span style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.3px;">League Caddie</span>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 32px;">
              <p style="margin:0 0 8px;font-size:11px;font-weight:700;letter-spacing:0.15em;text-transform:uppercase;color:#15803d;">Pick Reminder</p>
              <h1 style="margin:0 0 16px;font-size:26px;font-weight:700;color:#111827;line-height:1.25;">Don't forget to pick!</h1>
              <p style="margin:0 0 8px;font-size:15px;color:#6b7280;line-height:1.6;">
                Hi <strong style="color:#111827;">{display_name}</strong>,
              </p>
{detail_html}
{cta_html}

              <hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 24px;" />

              <p style="margin:0;font-size:13px;color:#9ca3af;line-height:1.5;">
                To stop receiving pick reminders, visit
                <a href="{settings.FRONTEND_URL}/settings" style="color:#166534;text-decoration:none;">Settings</a>
                and turn off email notifications.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color:#f9fafb;border-top:1px solid #e5e7eb;padding:20px 40px;text-align:center;">
              <p style="margin:0 0 4px;font-size:12px;color:#9ca3af;">
                &copy; 2026 League Caddie
              </p>
              <p style="margin:0;font-size:11px;">
                <a href="{settings_url}" style="color:#9ca3af;text-decoration:underline;">Unsubscribe</a>
                <span style="color:#d1d5db;">&nbsp;&middot;&nbsp;</span>
                <a href="{frontend}" style="color:#9ca3af;text-decoration:underline;">Open app</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    _send(to_email, subject, html_body, text_body)


# ---------------------------------------------------------------------------
# Manager league email
# ---------------------------------------------------------------------------


def send_manager_league_email(
    to_email: str,
    member_name: str,
    league_name: str,
    sender_name: str,
    subject: str,
    body: str,
    league_id: str,
) -> None:
    """Send a manager-composed email to one league member."""
    frontend = settings.FRONTEND_URL.rstrip("/")
    league_url = f"{frontend}/leagues/{league_id}"
    settings_url = f"{frontend}/settings"

    # Escape user-provided content to prevent XSS in the HTML version.
    import html as html_mod

    safe_subject = html_mod.escape(subject)
    safe_body = html_mod.escape(body).replace("\n", "<br>")
    safe_sender = html_mod.escape(sender_name)
    safe_league = html_mod.escape(league_name)
    safe_member = html_mod.escape(member_name)

    full_subject = f"[{league_name}] {subject}"

    text_body = f"""Message from {sender_name} in {league_name}

Hi {member_name},

{body}

---
Open your league: {league_url}
To stop receiving these emails, update your preferences: {settings_url}
"""

    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{safe_subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f3f4f6;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="100%" style="max-width:520px;background-color:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

          <!-- Header — League Caddie branding -->
          <tr>
            <td style="background:linear-gradient(to bottom right,#052e16,#14532d,#166534);padding:36px 40px;text-align:center;">
              <span style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.3px;">League Caddie</span>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 32px;">
              <p style="margin:0 0 2px;font-size:11px;font-weight:700;letter-spacing:0.15em;text-transform:uppercase;color:#15803d;">
                {safe_league}
              </p>
              <p style="margin:0 0 16px;font-size:13px;color:#9ca3af;">
                From {safe_sender}
              </p>
              <h1 style="margin:0 0 20px;font-size:24px;font-weight:700;color:#111827;line-height:1.3;">
                {safe_subject}
              </h1>
              <p style="margin:0 0 24px;font-size:15px;color:#6b7280;line-height:1.6;">
                Hi {safe_member},
              </p>
              <p style="margin:0 0 28px;font-size:15px;color:#374151;line-height:1.6;">
                {safe_body}
              </p>

              <table cellpadding="0" cellspacing="0" style="margin:0 auto 28px;">
                <tr>
                  <td style="background-color:#166534;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.12);">
                    <a href="{league_url}" style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:12px;">
                      Open League
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color:#f9fafb;border-top:1px solid #e5e7eb;padding:20px 40px;text-align:center;">
              <p style="margin:0 0 4px;font-size:12px;color:#9ca3af;">
                &copy; 2026 League Caddie &nbsp;&middot;&nbsp; Sent by your league manager
              </p>
              <p style="margin:0;font-size:11px;">
                <a href="{settings_url}" style="color:#9ca3af;text-decoration:underline;">Unsubscribe</a>
                <span style="color:#d1d5db;">&nbsp;&middot;&nbsp;</span>
                <a href="{league_url}" style="color:#9ca3af;text-decoration:underline;">View league</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    _send(to_email, full_subject, html_body, text_body)
