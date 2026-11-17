# """Simple username/password login for DataTalk.AI.

# Configure in `.env`:

#     AUTH_ENABLED=true
#     AUTH_USERS=admin:Admin@123:admin,analyst:Analyst@123:analyst,guest:Guest@123:viewer

# Format: username:password:role  (comma separated; role is optional, default "analyst").
# Passwords may also be stored hashed:  username:sha256$<hexdigest>:role
#     python -c "import hashlib;print(hashlib.sha256(b'mypassword').hexdigest())"

# Roles: "viewer" cannot export data; every other role can.
# Passwords and usernames must not contain ":" or ",".
# """

# from __future__ import annotations

# import hashlib
# import hmac
# import logging
# import os
# import time
# from dataclasses import dataclass

# import streamlit as st
# import streamlit.components.v1 as components

# try:  # pick up .env if python-dotenv is installed (settings.py may already do this)
#     from dotenv import load_dotenv

#     load_dotenv()
# except Exception:  # pragma: no cover
#     pass

# log = logging.getLogger("datatalk.auth")

# SESSION_KEY = "auth_user"
# MAX_ATTEMPTS = 5
# LOCKOUT_SECONDS = 60


# @dataclass(frozen=True)
# class AuthUser:
#     name: str
#     email: str
#     role: str
#     method: str = "password"


# # ── configuration ──────────────────────────────────────────────────────────────
# def _enabled() -> bool:
#     return os.getenv("AUTH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


# def _load_users() -> dict[str, tuple[str, str]]:
#     """Return {username: (password_or_hash, role)} from AUTH_USERS."""
#     users: dict[str, tuple[str, str]] = {}
#     for entry in os.getenv("AUTH_USERS", "").split(","):
#         parts = [p.strip() for p in entry.strip().split(":")]
#         if len(parts) < 2 or not parts[0] or not parts[1]:
#             continue
#         users[parts[0].lower()] = (parts[1], (parts[2] if len(parts) > 2 and parts[2] else "analyst").lower())
#     return users


# def _password_ok(stored: str, supplied: str) -> bool:
#     if stored.startswith("sha256$"):
#         digest = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
#         return hmac.compare_digest(stored[len("sha256$"):].lower(), digest)
#     return hmac.compare_digest(stored.encode("utf-8"), supplied.encode("utf-8"))


# # ── public API used by app.py and the dashboards ───────────────────────────────
# def current_user() -> AuthUser | None:
#     return st.session_state.get(SESSION_KEY)


# def audit(action: str, **details) -> None:
#     user = current_user()
#     log.info("audit | user=%s | action=%s | %s", user.email if user else "anonymous", action, details)


# def question_fields(text: str) -> dict:
#     """Audit fields describing a user's question, for ``audit("question", **question_fields(text))``.

#     By default the question text is NOT written to the log (it may contain patient or member details);
#     only its length, word count and a short hash are recorded so entries can still be correlated.
#     Set AUDIT_LOG_QUESTION_TEXT=true in `.env` to also log a truncated copy of the text.
#     """
#     text = (text or "").strip()
#     fields: dict = {
#         "question_chars": len(text),
#         "question_words": len(text.split()),
#         "question_id": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
#     }
#     if os.getenv("AUDIT_LOG_QUESTION_TEXT", "false").strip().lower() in {"1", "true", "yes", "on"}:
#         fields["question"] = text if len(text) <= 300 else text[:300] + "…"
#     return fields


# def can_export() -> bool:
#     user = current_user()
#     return True if not _enabled() else bool(user and user.role != "viewer")


# def export_blocked_notice() -> None:
#     st.info("🔒 Your account role (viewer) is not allowed to export data.")


# # ── login page styling ─────────────────────────────────────────────────────────
# _LOGIN_CSS = """
# <style>
# @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

# :root {
#     --dt-bg: #060913;
#     --dt-panel: #0b1120;
#     --dt-border: rgba(148,163,184,.16);
#     --dt-text: #f8fafc;
#     --dt-muted: #94a3b8;
#     --dt-accent: #6366f1;
#     --dt-accent-2: #8b5cf6;
#     --dt-accent-3: #22d3ee;
# }

# html body, html body * { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }

# /* ── page background: animated aurora + dot grid ── */
# html body [data-testid="stApp"],
# html body [data-testid="stAppViewContainer"] {
#     background:
#         radial-gradient(900px 600px at 12% 8%, rgba(99,102,241,.35), transparent 60%),
#         radial-gradient(800px 600px at 92% 90%, rgba(139,92,246,.30), transparent 60%),
#         radial-gradient(600px 400px at 80% 10%, rgba(34,211,238,.14), transparent 60%),
#         var(--dt-bg) !important;
#     background-size: 140% 140%, 140% 140%, 140% 140%, auto !important;
#     animation: dtAurora 18s ease-in-out infinite alternate;
# }
# html body [data-testid="stAppViewContainer"]::before {
#     content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
#     background-image: radial-gradient(rgba(148,163,184,.14) 1px, transparent 1px);
#     background-size: 28px 28px;
#     -webkit-mask-image: radial-gradient(ellipse at center, #000 30%, transparent 78%);
#             mask-image: radial-gradient(ellipse at center, #000 30%, transparent 78%);
# }
# @keyframes dtAurora { 0% { background-position: 0% 0%, 100% 100%, 100% 0%, 0 0; }
#                       100% { background-position: 30% 20%, 70% 80%, 70% 30%, 0 0; } }

# html body [data-testid="stSidebar"], html body [data-testid="stSidebarCollapsedControl"],
# html body [data-testid="stHeader"], html body [data-testid="stToolbar"],
# html body footer { display: none !important; }

# html body [data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stMainBlockContainer"],
# html body [data-testid="stAppViewContainer"] .main .block-container,
# html body .stMainBlockContainer, html body .block-container {
#     max-width: 1120px !important; width: 100% !important;
#     margin: 0 auto !important; padding: 5vh 1rem 2rem 1rem !important;
#     position: relative; z-index: 1;
# }

# /* ── split card ── */
# html body [data-testid="stHorizontalBlock"] {
#     gap: 0 !important; align-items: stretch !important;
#     border-radius: 26px; overflow: hidden;
#     border: 1px solid var(--dt-border);
#     background: rgba(11,17,32,.72);
#     -webkit-backdrop-filter: blur(18px); backdrop-filter: blur(18px);
#     box-shadow: 0 40px 100px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.02) inset;
#     animation: dtRise .7s cubic-bezier(.2,.8,.2,1) both;
# }
# html body [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {
#     background: linear-gradient(180deg, rgba(13,20,38,.95), rgba(9,14,28,.95));
#     padding: 2.8rem 3.1rem;
# }
# html body [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) [data-testid="stVerticalBlock"] {
#     justify-content: center; min-height: 600px; gap: .35rem;
# }
# @keyframes dtRise { from { opacity: 0; transform: translateY(24px) scale(.985); } to { opacity: 1; transform: none; } }
# @keyframes dtFade { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }

# /* ── brand panel ── */
# .dt-brand {
#     height: 100%; min-height: 660px; padding: 2.6rem 2.5rem; color: #e2e8f0;
#     display: flex; flex-direction: column; position: relative; overflow: hidden;
#     background: linear-gradient(155deg, #3340d6 0%, #5636ee 48%, #7c3aed 100%);
# }
# .dt-brand::before { /* soft grid */
#     content: ""; position: absolute; inset: 0; opacity: .5;
#     background-image: linear-gradient(rgba(255,255,255,.07) 1px, transparent 1px),
#                       linear-gradient(90deg, rgba(255,255,255,.07) 1px, transparent 1px);
#     background-size: 36px 36px;
#     -webkit-mask-image: radial-gradient(circle at 30% 20%, #000, transparent 75%);
#             mask-image: radial-gradient(circle at 30% 20%, #000, transparent 75%);
# }
# .dt-orb { position: absolute; border-radius: 50%; filter: blur(2px); pointer-events: none; }
# .dt-orb.o1 { width: 340px; height: 340px; right: -130px; top: -130px; background: rgba(255,255,255,.13); animation: dtFloat 9s ease-in-out infinite; }
# .dt-orb.o2 { width: 260px; height: 260px; left: -100px; bottom: -110px; background: rgba(34,211,238,.20); animation: dtFloat 12s ease-in-out infinite reverse; }
# .dt-orb.o3 { width: 90px; height: 90px; right: 18%; bottom: 22%; background: rgba(255,255,255,.12); animation: dtFloat 7s ease-in-out infinite; }
# @keyframes dtFloat { 0%,100% { transform: translate(0,0); } 50% { transform: translate(14px,-18px); } }

# .dt-logo { display: flex; align-items: center; gap: .8rem; position: relative; z-index: 1; animation: dtFade .6s .1s both; }
# .dt-logo-badge {
#     width: 46px; height: 46px; border-radius: 14px; display: grid; place-items: center;
#     background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.28);
#     -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
#     box-shadow: 0 8px 24px rgba(0,0,0,.2);
# }
# .dt-logo-text { font-size: 1.3rem; font-weight: 700; color: #fff; letter-spacing: .2px; }
# .dt-logo-text b { color: #a5f3fc; font-weight: 700; }

# .dt-headline { margin-top: 2.6rem; font-size: 2.05rem; line-height: 1.18; font-weight: 800; color: #fff;
#     letter-spacing: -.02em; position: relative; z-index: 1; animation: dtFade .6s .2s both; }
# .dt-rotator { display: block; position: relative; height: 1.25em; margin-top: .15rem; overflow: hidden; }
# .dt-rotator span { position: absolute; left: 0; top: 0; opacity: 0; transform: translateY(60%);
#     background: linear-gradient(90deg, #a5f3fc, #ffffff); -webkit-background-clip: text; background-clip: text;
#     -webkit-text-fill-color: transparent; animation: dtWord 12s infinite; white-space: nowrap; }
# .dt-rotator span:nth-child(2) { animation-delay: 4s; }
# .dt-rotator span:nth-child(3) { animation-delay: 8s; }
# @keyframes dtWord { 0% { opacity: 0; transform: translateY(60%); } 4%, 30% { opacity: 1; transform: none; }
#                     34%, 100% { opacity: 0; transform: translateY(-60%); } }

# .dt-sub { margin-top: .9rem; font-size: .97rem; line-height: 1.6; color: rgba(255,255,255,.82);
#     position: relative; z-index: 1; animation: dtFade .6s .3s both; max-width: 34ch; }

# /* live chat preview */
# .dt-chat { margin-top: 1.7rem; position: relative; z-index: 1; display: flex; flex-direction: column; gap: .6rem;
#     animation: dtFade .6s .4s both; }
# .dt-bubble { max-width: 88%; padding: .65rem .9rem; border-radius: 14px; font-size: .85rem; line-height: 1.45;
#     border: 1px solid rgba(255,255,255,.18); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); }
# .dt-bubble.q { align-self: flex-end; background: rgba(255,255,255,.22); color: #fff; border-bottom-right-radius: 4px; }
# .dt-bubble.a { align-self: flex-start; background: rgba(8,12,30,.38); color: #e0e7ff; border-bottom-left-radius: 4px; }
# .dt-bubble.a .bars { display: flex; align-items: flex-end; gap: 4px; height: 34px; margin-top: .5rem; }
# .dt-bubble.a .bars i { flex: 1; border-radius: 3px 3px 0 0; background: linear-gradient(180deg, #a5f3fc, #818cf8);
#     transform-origin: bottom; animation: dtBar 2.6s ease-in-out infinite; }
# .dt-bubble.a .bars i:nth-child(1) { height: 40%; animation-delay: 0s; }
# .dt-bubble.a .bars i:nth-child(2) { height: 70%; animation-delay: .15s; }
# .dt-bubble.a .bars i:nth-child(3) { height: 55%; animation-delay: .3s; }
# .dt-bubble.a .bars i:nth-child(4) { height: 90%; animation-delay: .45s; }
# .dt-bubble.a .bars i:nth-child(5) { height: 65%; animation-delay: .6s; }
# .dt-bubble.a .bars i:nth-child(6) { height: 80%; animation-delay: .75s; }
# @keyframes dtBar { 0%,100% { transform: scaleY(1); } 50% { transform: scaleY(.55); } }
# .dt-typing { display: inline-flex; gap: 4px; align-items: center; margin-left: .35rem; vertical-align: middle; }
# .dt-typing i { width: 5px; height: 5px; border-radius: 50%; background: #c7d2fe; animation: dtDot 1.2s infinite; }
# .dt-typing i:nth-child(2) { animation-delay: .15s; } .dt-typing i:nth-child(3) { animation-delay: .3s; }
# @keyframes dtDot { 0%,60%,100% { opacity: .3; transform: none; } 30% { opacity: 1; transform: translateY(-3px); } }

# .dt-features { margin-top: 1.6rem; display: grid; gap: .55rem; position: relative; z-index: 1; animation: dtFade .6s .5s both; }
# .dt-feat { display: flex; gap: .75rem; align-items: center; font-size: .88rem; color: rgba(255,255,255,.92);
#     padding: .5rem .65rem; border-radius: 12px; border: 1px solid transparent;
#     transition: background .2s ease, border-color .2s ease, transform .2s ease; }
# .dt-feat:hover { background: rgba(255,255,255,.12); border-color: rgba(255,255,255,.2); transform: translateX(4px); }
# .dt-feat .ic { width: 30px; height: 30px; border-radius: 9px; background: rgba(255,255,255,.16);
#     display: grid; place-items: center; flex: 0 0 30px; font-size: .95rem; }
# .dt-brand-foot { margin-top: auto; padding-top: 1.6rem; font-size: .76rem; color: rgba(255,255,255,.65); position: relative; z-index: 1; }

# /* ── form side ── */
# .dt-chip { display: inline-flex; align-items: center; gap: .45rem; padding: .28rem .7rem; border-radius: 999px;
#     font-size: .72rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: #a5b4fc;
#     background: rgba(99,102,241,.12); border: 1px solid rgba(99,102,241,.3); animation: dtFade .5s .15s both; }
# .dt-chip .pulse { width: 7px; height: 7px; border-radius: 50%; background: #34d399; box-shadow: 0 0 0 0 rgba(52,211,153,.6);
#     animation: dtPulse 2s infinite; }
# @keyframes dtPulse { 70% { box-shadow: 0 0 0 8px rgba(52,211,153,0); } 100% { box-shadow: 0 0 0 0 rgba(52,211,153,0); } }
# .dt-title { font-size: 1.95rem; font-weight: 800; color: var(--dt-text); margin: .9rem 0 .3rem 0; letter-spacing: -.02em;
#     animation: dtFade .5s .2s both; }
# .dt-subtitle { font-size: .95rem; color: var(--dt-muted); margin-bottom: 1.5rem; animation: dtFade .5s .25s both; }
# .dt-foot { margin-top: 1.3rem; font-size: .76rem; color: #64748b; text-align: center; display: flex;
#     gap: .5rem; align-items: center; justify-content: center; }
# .dt-foot svg { flex: 0 0 auto; }

# html body [data-testid="stForm"] { border: none !important; padding: 0 !important; background: transparent !important;
#     animation: dtFade .5s .3s both; }
# html body [data-testid="stForm"] label p { color: #cbd5e1 !important; font-size: .82rem !important; font-weight: 600 !important;
#     letter-spacing: .01em; }
# html body [data-testid="stForm"] [data-baseweb="input"],
# html body [data-testid="stForm"] [data-baseweb="base-input"] { background: #0f172a !important; border-radius: 12px !important; }
# html body [data-testid="stForm"] [data-baseweb="input"] {
#     border: 1px solid #243049 !important; transition: border-color .2s ease, box-shadow .2s ease, transform .2s ease; }
# html body [data-testid="stForm"] [data-baseweb="input"]:hover { border-color: #3b4a6b !important; }
# html body [data-testid="stForm"] [data-baseweb="input"]:focus-within {
#     border-color: var(--dt-accent) !important; box-shadow: 0 0 0 4px rgba(99,102,241,.22) !important; transform: translateY(-1px); }
# html body [data-testid="stForm"] input { color: #f1f5f9 !important; -webkit-text-fill-color: #f1f5f9 !important;
#     padding: .85rem 1rem !important; font-size: .95rem !important; }
# html body [data-testid="stForm"] input::placeholder { color: #5b6b86 !important; -webkit-text-fill-color: #5b6b86 !important; }
# html body [data-testid="stForm"] input:-webkit-autofill {
#     -webkit-box-shadow: 0 0 0 40px #0f172a inset !important; -webkit-text-fill-color: #f1f5f9 !important; }
# html body [data-testid="stForm"] button[kind="tertiary"], html body [data-testid="stForm"] [data-baseweb="input"] button {
#     color: #94a3b8 !important; background: transparent !important; }
# html body [data-testid="stForm"] [data-baseweb="input"] button:hover { color: #e2e8f0 !important; }

# html body [data-testid="stFormSubmitButton"] button {
#     position: relative; overflow: hidden; height: 3.1rem; border: none !important; border-radius: 12px !important;
#     font-weight: 700 !important; font-size: 1rem !important; letter-spacing: .2px; margin-top: .8rem; color: #fff !important;
#     background: linear-gradient(90deg, #4f46e5, #7c3aed, #4f46e5) !important; background-size: 200% 100% !important;
#     box-shadow: 0 10px 28px rgba(99,102,241,.4);
#     transition: transform .15s ease, box-shadow .15s ease, background-position .5s ease; }
# html body [data-testid="stFormSubmitButton"] button::after {
#     content: ""; position: absolute; top: 0; left: -60%; width: 40%; height: 100%;
#     background: linear-gradient(100deg, transparent, rgba(255,255,255,.35), transparent); transform: skewX(-20deg); }
# html body [data-testid="stFormSubmitButton"] button:hover { transform: translateY(-2px); background-position: 100% 0 !important;
#     box-shadow: 0 16px 36px rgba(99,102,241,.55); }
# html body [data-testid="stFormSubmitButton"] button:hover::after { left: 130%; transition: left .7s ease; }
# html body [data-testid="stFormSubmitButton"] button:active { transform: translateY(0) scale(.99); }
# html body [data-testid="stFormSubmitButton"] button:focus-visible { outline: 3px solid rgba(165,180,252,.6); outline-offset: 2px; }

# html body [data-testid="stAlert"] { border-radius: 12px; animation: dtShake .4s ease both; }
# @keyframes dtShake { 10%,90% { transform: translateX(-1px); } 20%,80% { transform: translateX(2px); }
#                      30%,50%,70% { transform: translateX(-4px); } 40%,60% { transform: translateX(4px); } }

# /* attempts meter + lockout */
# .dt-attempts { display: flex; gap: 6px; margin: .7rem 0 0; align-items: center; font-size: .75rem; color: #fbbf24; }
# .dt-attempts i { flex: 1; height: 4px; border-radius: 4px; background: #1e293b; }
# .dt-attempts i.on { background: linear-gradient(90deg, #f59e0b, #ef4444); }
# .dt-lock { text-align: center; padding: 2rem 1.2rem; border-radius: 18px; border: 1px solid rgba(239,68,68,.3);
#     background: rgba(239,68,68,.07); animation: dtFade .4s both; }
# .dt-lock .big { font-size: 2.6rem; font-weight: 800; color: #fca5a5; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
# .dt-lock p { color: #cbd5e1; margin: .4rem 0 0; font-size: .92rem; }
# .dt-lock .track { margin-top: 1.1rem; height: 5px; border-radius: 5px; background: rgba(255,255,255,.08); overflow: hidden; }
# .dt-lock .track b { display: block; height: 100%; background: linear-gradient(90deg, #ef4444, #f59e0b); transition: width 1s linear; }

# @media (prefers-reduced-motion: reduce) { html body *, html body *::before, html body *::after {
#     animation-duration: .001ms !important; animation-iteration-count: 1 !important; transition-duration: .001ms !important; } }

# @media (max-width: 900px) {
#     html body [data-testid="stHorizontalBlock"] { border-radius: 18px; }
#     html body [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) { padding: 2rem 1.4rem; }
#     html body [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(1) { display: none; }
#     html body [data-testid="stHorizontalBlock"] [data-testid="stVerticalBlock"] { min-height: 0 !important; }
#     html body .block-container, html body .stMainBlockContainer { padding-top: 2vh !important; }
# }
# </style>
# """

# _LOGO_SVG = (
#     '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8" '
#     'stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/>'
#     '<path d="M8.5 13.5v-2M12 13.5v-4M15.5 13.5v-3"/></svg>'
# )
# _SHIELD_SVG = (
#     '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
#     'stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 5 3.4 8 8 9 4.6-1 8-4 8-9V6l-8-3Z"/>'
#     '<path d="m9 12 2 2 4-4"/></svg>'
# )

# _BRAND_HTML = f"""
# <div class="dt-brand">
#   <div class="dt-orb o1"></div><div class="dt-orb o2"></div><div class="dt-orb o3"></div>
#   <div class="dt-logo"><div class="dt-logo-badge">{_LOGO_SVG}</div>
#     <div class="dt-logo-text">DataTalk<b>.AI</b></div></div>
#   <div class="dt-headline">Healthcare appeals intelligence,
#     <span class="dt-rotator"><span>in plain English.</span><span>in real time.</span><span>with full audit trails.</span></span>
#   </div>
#   <div class="dt-sub">Ask questions, track SLA risk and uncover trends across your appeals data in seconds.</div>
#   <div class="dt-chat">
#     <div class="dt-bubble q">Which appeals are at SLA risk this week?</div>
#     <div class="dt-bubble a">Analyzing your data<span class="dt-typing"><i></i><i></i><i></i></span>
#       <div class="bars"><i></i><i></i><i></i><i></i><i></i><i></i></div></div>
#   </div>
#   <div class="dt-features">
#     <div class="dt-feat"><span class="ic">💬</span><div>Conversational AI grounded in your data</div></div>
#     <div class="dt-feat"><span class="ic">📊</span><div>Interactive dashboards &amp; risk findings</div></div>
#     <div class="dt-feat"><span class="ic">🛡️</span><div>Role-based access with audited exports</div></div>
#   </div>
#   <div class="dt-brand-foot">© DataTalk.AI · Secure workspace</div>
# </div>
# """

# # Runs in a same-origin iframe: autofocus, caps-lock hint, Enter-to-advance. Fails silently if blocked.
# _LOGIN_JS = """
# <script>
# (function () {
#   try {
#     const doc = window.parent.document;
#     const tryBind = (n) => {
#       const user = doc.querySelector('input[aria-label="Username"]');
#       const pass = doc.querySelector('input[aria-label="Password"]');
#       if (!user || !pass) { if (n < 40) setTimeout(() => tryBind(n + 1), 100); return; }
#       if (!user.value && doc.activeElement === doc.body) user.focus();
#       if (pass.dataset.dtBound) return;
#       pass.dataset.dtBound = "1";
#       let hint = doc.getElementById("dt-caps");
#       if (!hint) {
#         hint = doc.createElement("div");
#         hint.id = "dt-caps";
#         hint.textContent = "⇪ Caps Lock is on";
#         hint.style.cssText = "display:none;margin-top:6px;font-size:12px;color:#fbbf24;font-weight:600";
#         pass.closest('[data-testid="stTextInput"]').appendChild(hint);
#       }
#       const check = (e) => { hint.style.display = (e.getModifierState && e.getModifierState("CapsLock")) ? "block" : "none"; };
#       pass.addEventListener("keydown", check);
#       pass.addEventListener("keyup", check);
#       pass.addEventListener("blur", () => (hint.style.display = "none"));
#       user.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); pass.focus(); } });
#     };
#     tryBind(0);
#   } catch (e) {}
# })();
# </script>
# """


# def _render_lockout(remaining: int) -> None:
#     pct = max(0, min(100, int(remaining / LOCKOUT_SECONDS * 100)))
#     st.markdown(
#         f'<div class="dt-lock"><div class="big">{remaining}s</div>'
#         f"<p>Too many failed attempts. Sign-in is temporarily locked.</p>"
#         f'<div class="track"><b style="width:{pct}%"></b></div></div>',
#         unsafe_allow_html=True,
#     )


# def require_login() -> AuthUser | None:
#     """Show the login page and stop the script until the user is signed in.

#     Returns None when AUTH_ENABLED=false.
#     """
#     if not _enabled():
#         return None
#     user = current_user()
#     if user:
#         return user

#     users = _load_users()
#     st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
#     left, right = st.columns([1.1, 1])
#     with left:
#         st.markdown(_BRAND_HTML, unsafe_allow_html=True)
#     with right:
#         st.markdown(
#             '<div class="dt-chip"><span class="pulse"></span>Secure sign-in</div>'
#             '<div class="dt-title">Welcome back 👋</div>'
#             '<div class="dt-subtitle">Sign in to your workspace to continue.</div>',
#             unsafe_allow_html=True,
#         )

#         if not users:
#             st.error("No users are configured. Add `AUTH_USERS=username:password:role` to your `.env` file "
#                      "and restart the app.")
#             st.stop()

#         remaining = int(st.session_state.get("auth_locked_until", 0.0) - time.time()) + 1
#         if remaining > 1 or st.session_state.get("auth_locked_until", 0.0) > time.time():
#             _render_lockout(max(remaining, 1))
#             time.sleep(1)
#             st.rerun()

#         failed_so_far = int(st.session_state.get("auth_failed", 0))

#         with st.form("login_form", clear_on_submit=False):
#             username = st.text_input("Username", placeholder="Enter your username", key="login_username")
#             password = st.text_input("Password", type="password", placeholder="Enter your password",
#                                      key="login_password")
#             submitted = st.form_submit_button("Sign in  →", width="stretch")

#         if submitted:
#             if not username.strip() or not password:
#                 st.warning("Please enter both your username and password.")
#             else:
#                 record = users.get(username.strip().lower())
#                 if record and _password_ok(record[0], password):
#                     name = username.strip()
#                     st.session_state[SESSION_KEY] = AuthUser(name=name.title(), email=name.lower(), role=record[1])
#                     st.session_state["auth_failed"] = 0
#                     audit("login")
#                     st.toast(f"Welcome back, {name.title()}!", icon="✅")
#                     with st.spinner("Signing you in…"):
#                         time.sleep(0.6)
#                     st.rerun()
#                 failed = failed_so_far + 1
#                 st.session_state["auth_failed"] = failed
#                 log.warning("failed login for username=%r", username)
#                 if failed >= MAX_ATTEMPTS:
#                     st.session_state["auth_locked_until"] = time.time() + LOCKOUT_SECONDS
#                     st.session_state["auth_failed"] = 0
#                     st.rerun()
#                 st.error("Invalid username or password.")
#                 left_tries = MAX_ATTEMPTS - failed
#                 if left_tries <= 2:
#                     bars = "".join(f'<i class="{"on" if i < failed else ""}"></i>' for i in range(MAX_ATTEMPTS))
#                     st.markdown(
#                         f'<div class="dt-attempts">{bars}<span>{left_tries} attempt'
#                         f'{"s" if left_tries != 1 else ""} left</span></div>',
#                         unsafe_allow_html=True,
#                     )

#         st.markdown(
#             f'<div class="dt-foot">{_SHIELD_SVG}<span>Authorized users only · Activity is monitored and logged</span></div>',
#             unsafe_allow_html=True,
#         )
#         components.html(_LOGIN_JS, height=0)
#     st.stop()


# # ── sidebar account box ────────────────────────────────────────────────────────
# _ROLE_COLORS = {
#     "admin": ("#f472b6", "rgba(244,114,182,.14)"),
#     "analyst": ("#818cf8", "rgba(129,140,248,.14)"),
#     "viewer": ("#94a3b8", "rgba(148,163,184,.14)"),
# }

# _ACCOUNT_CSS = """
# <style>
# .dt-acct { display: flex; align-items: center; gap: .75rem; padding: .8rem .85rem; border-radius: 14px;
#     border: 1px solid rgba(148,163,184,.18); background: linear-gradient(135deg, rgba(99,102,241,.12), rgba(139,92,246,.06));
#     transition: border-color .2s ease, transform .2s ease; }
# .dt-acct:hover { border-color: rgba(129,140,248,.5); transform: translateY(-1px); }
# .dt-avatar { position: relative; width: 40px; height: 40px; border-radius: 12px; flex: 0 0 40px; display: grid; place-items: center;
#     font-weight: 700; color: #fff; background: linear-gradient(135deg, #4f46e5, #7c3aed); }
# .dt-avatar::after { content: ""; position: absolute; right: -2px; bottom: -2px; width: 11px; height: 11px; border-radius: 50%;
#     background: #34d399; border: 2px solid #0b1120; }
# .dt-acct-name { font-weight: 600; font-size: .92rem; line-height: 1.2; }
# .dt-role { display: inline-block; margin-top: .2rem; padding: .1rem .5rem; border-radius: 999px; font-size: .68rem;
#     font-weight: 700; letter-spacing: .05em; text-transform: uppercase; }
# </style>
# """


# def render_account_box() -> None:
#     """Sidebar box showing who is signed in, with a sign-out button."""
#     user = current_user()
#     if not user:
#         return
#     color, bg = _ROLE_COLORS.get(user.role, _ROLE_COLORS["analyst"])
#     initials = "".join(w[0] for w in user.name.split()[:2]).upper() or "U"
#     st.markdown(_ACCOUNT_CSS, unsafe_allow_html=True)
#     st.markdown(
#         f'<div class="dt-acct"><div class="dt-avatar">{initials}</div><div>'
#         f'<div class="dt-acct-name">{user.name}</div>'
#         f'<span class="dt-role" style="color:{color};background:{bg}">{user.role}</span></div></div>',
#         unsafe_allow_html=True,
#     )
#     if st.button("🚪 Sign out", width="stretch", key="logout_btn"):
#         audit("logout")
#         for key in list(st.session_state.keys()):
#             del st.session_state[key]
#         st.rerun()


"""Authentication primitives for the DataTalk.AI login gate. No Streamlit imports.

Kept free of Streamlit on purpose (``core.runtime`` is the only ``core`` module that imports it):
the Streamlit wiring lives in ``components/login_page.py``.

What is here
------------
* ``hash_password`` / ``verify_password`` — salted ``scrypt`` (standard library, no extra dependency).
  The stored format is self-describing (``scrypt$N$r$p$salt$hash``) so the cost can be raised later
  without invalidating existing hashes. Verification is constant-time, and an unknown user costs the
  same work as a wrong password so response time does not reveal which usernames exist.
* ``parse_users`` — validates the ``[login.users.*]`` secrets table at start-up (fail closed).
* ``LoginThrottle`` — process-wide failed-attempt counter with a growing lockout. It is keyed by
  username (unknown names included) so the error behaviour is identical for real and invented users.
* ``session_status`` — idle and absolute session timeout rules.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Literal

SCRYPT_N = 2 ** 15          # 32 MiB of memory per hash; raise when your host allows it
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32
_MAXMEM = 256 * 1024 * 1024  # OpenSSL's default limit (32 MiB) is below what N=2**15 needs
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256    # bounds the work an attacker can force per attempt
_PREFIX = "scrypt"


# ── passwords ──────────────────────────────────────────────────────────────────
def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=KEY_BYTES, maxmem=_MAXMEM)


def password_problems(password: str) -> list[str]:
    """Reasons a new password is rejected (empty list = acceptable)."""
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"use at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"use at most {MAX_PASSWORD_LENGTH} characters")
    if password and len(set(password)) < 5:
        problems.append("use more than a few distinct characters")
    return problems


def hash_password(password: str) -> str:
    """Salted scrypt hash in the ``scrypt$N$r$p$salt$hash`` format."""
    salt = secrets.token_bytes(SALT_BYTES)
    key = _derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"{_PREFIX}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(key)}"


def _parse_hash(stored: str) -> tuple[int, int, int, bytes, bytes]:
    parts = str(stored).strip().split("$")
    if len(parts) != 6 or parts[0] != _PREFIX:
        raise ValueError("password_hash must look like scrypt$N$r$p$salt$hash")
    n, r, p = (int(x) for x in parts[1:4])
    if n < 2 ** 14 or n & (n - 1) or r < 1 or p < 1 or n > 2 ** 20:
        raise ValueError("password_hash has unsupported scrypt parameters")
    salt, key = _unb64(parts[4]), _unb64(parts[5])
    if len(salt) < 8 or len(key) < 16:
        raise ValueError("password_hash salt or key is too short")
    return n, r, p, salt, key


# Verified against when the username does not exist, so both cases cost one scrypt run.
_DUMMY = (SCRYPT_N, SCRYPT_R, SCRYPT_P, b"\x00" * SALT_BYTES, b"\x00" * KEY_BYTES)


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check. ``stored=None`` (unknown user) still performs the hashing work."""
    if not isinstance(password, str) or not password or len(password) > MAX_PASSWORD_LENGTH:
        return False
    try:
        n, r, p, salt, key = _parse_hash(stored) if stored else _DUMMY
    except (ValueError, TypeError):
        n, r, p, salt, key = _DUMMY
        stored = None
    try:
        candidate = _derive(password, salt, n, r, p)
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(candidate, key) and stored is not None


# ── users ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class UserRecord:
    username: str
    name: str
    password_hash: str = ""
    role: str = ""


def normalise_username(value: str) -> str:
    return " ".join(str(value or "").split()).lower()


def parse_users(raw: Mapping[str, Any] | None) -> dict[str, UserRecord]:
    """Validate the ``[login.users.<username>]`` tables. Raises ``ValueError`` naming the user only."""
    users: dict[str, UserRecord] = {}
    for username, entry in (raw or {}).items():
        key = normalise_username(username)
        if not key or len(key) > 64:
            raise ValueError("a username is empty or longer than 64 characters")
        if key in users:
            raise ValueError(f"duplicate username '{key}' (usernames are case-insensitive)")
        if not isinstance(entry, Mapping):
            raise ValueError(f"user '{key}' must be a table with name and password_hash")
        try:
            _parse_hash(str(entry.get("password_hash", "")))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"user '{key}': {exc}") from None
        users[key] = UserRecord(username=key, name=str(entry.get("name") or username).strip()[:80],
                                password_hash=str(entry["password_hash"]).strip(),
                                role=str(entry.get("role") or "").strip()[:32])
    return users


USERNAME_PATTERN = re.compile(r"[a-z0-9._@\-]{1,64}")   # what a new username may contain (after lower-casing)


def clean_display_name(text: str) -> str:
    """Drop characters that would need escaping inside the single-quoted .env value; max 80 characters."""
    return re.sub(r"[\\'\"\r\n\t]", "", str(text or "")).strip()[:80]


# ── persisting users to .env ───────────────────────────────────────────────────
_ENV_LINE = re.compile(r"^[ \t]*LOGIN_USERS[ \t]*=[^\r\n]*", re.M)
_env_lock = threading.Lock()


def save_user_to_env(path: str | Path, username: str, entry: Mapping[str, Any]) -> None:
    """Add or replace ``username`` in the ``LOGIN_USERS`` JSON line of the ``.env`` file at ``path``.

    Same result as ``scripts/hash_password.py --env-file``: every other line, other users and the file's
    line endings stay exactly as they are. The change is serialised with a lock and written to a temporary
    file that then replaces the original, so a crash or two simultaneous sign-ups cannot corrupt ``.env``.
    Raises ``ValueError`` if the existing ``LOGIN_USERS`` line is not a JSON object and ``OSError`` if the
    file cannot be read or written.
    """
    path = Path(path)
    with _env_lock:
        text = ""
        if path.exists():
            with path.open("r", encoding="utf-8", newline="") as fh:  # newline="" keeps CRLF files unchanged
                text = fh.read()
        users: dict[str, Any] = {}
        match = _ENV_LINE.search(text)
        if match:
            raw = match.group(0).split("=", 1)[1].strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
                raw = raw[1:-1]
            try:
                users = json.loads(raw) if raw else {}
            except ValueError:
                raise ValueError("the existing LOGIN_USERS line is not valid JSON") from None
            if not isinstance(users, dict):
                raise ValueError("the existing LOGIN_USERS value is not a JSON object")
        users[username] = dict(entry)
        line = "LOGIN_USERS='" + json.dumps(users, separators=(",", ":")) + "'"
        if match:
            text = text[:match.start()] + line + text[match.end():]
        else:
            newline = "\r\n" if "\r\n" in text else "\n"
            text = text + ("" if not text or text.endswith(("\n", "\r")) else newline) + line + newline
        tmp = path.with_name(path.name + ".tmp")
        try:
            with tmp.open("w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            if path.exists():
                shutil.copymode(path, tmp)  # keep restrictive permissions if the file had them
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)


# ── throttling ─────────────────────────────────────────────────────────────────
class LoginThrottle:
    """Failed-attempt counter shared by every session in the process (thread-safe).

    After ``max_attempts`` consecutive failures a key is locked for ``lockout_seconds``; each further
    lockout doubles the time (up to 8x). A success resets the key. Memory is bounded by ``max_entries``.
    """

    def __init__(self, max_attempts: int = 5, lockout_seconds: int = 900, max_entries: int = 1000) -> None:
        self.max_attempts = max(1, int(max_attempts))
        self.lockout_seconds = max(1, int(lockout_seconds))
        self.max_entries = max(10, int(max_entries))
        self._state: dict[str, dict[str, float]] = {}
        self._lock = threading.Lock()

    def locked_for(self, key: str, now: float) -> int:
        """Seconds still locked (0 = free to try)."""
        with self._lock:
            entry = self._state.get(key)
            return max(0, int(entry["until"] - now + 0.999)) if entry else 0

    def fail(self, key: str, now: float) -> int:
        """Record a failure. Returns the lockout seconds if this failure triggered one, else 0."""
        with self._lock:
            entry = self._state.setdefault(key, {"fails": 0.0, "locks": 0.0, "until": 0.0})
            if entry["until"] > now:
                return int(entry["until"] - now)
            entry["fails"] += 1
            triggered = 0
            if entry["fails"] >= self.max_attempts:
                triggered = self.lockout_seconds * min(2 ** int(entry["locks"]), 8)
                entry.update(fails=0.0, locks=entry["locks"] + 1, until=now + triggered)
            self._prune(now)
            return triggered

    def reset(self, key: str) -> None:
        with self._lock:
            self._state.pop(key, None)

    def _prune(self, now: float) -> None:
        if len(self._state) <= self.max_entries:
            return
        for k in [k for k, v in self._state.items() if v["until"] <= now and v["fails"] == 0][: len(self._state)]:
            self._state.pop(k, None)
        while len(self._state) > self.max_entries:
            self._state.pop(next(iter(self._state)))


# ── sessions ───────────────────────────────────────────────────────────────────
SessionStatus = Literal["ok", "idle", "expired"]


def session_status(record: Mapping[str, Any], now: float, idle_seconds: int, max_seconds: int) -> SessionStatus:
    """``idle`` after ``idle_seconds`` without activity, ``expired`` after ``max_seconds`` in total."""
    try:
        login_at, last_seen = float(record["login_at"]), float(record["last_seen"])
    except (KeyError, TypeError, ValueError):
        return "expired"
    if max_seconds and now - login_at > max_seconds:
        return "expired"
    if idle_seconds and now - last_seen > idle_seconds:
        return "idle"
    return "ok"


# ── audit trail ────────────────────────────────────────────────────────────────
# Who asked what, and when. Written to the ``datatalk.audit`` logger as one JSON object per line, so it
# can be routed to its own file or log sink. Kept free of Streamlit: ``components/login_page.py``
# registers a function that tells this module who the current user is.
_audit_log = logging.getLogger("datatalk.audit")
_user_provider: Callable[[], str] | None = None


def set_user_provider(provider: Callable[[], str] | None) -> None:
    """Register a zero-argument function returning the signed-in username (or ``""``)."""
    global _user_provider
    _user_provider = provider


def _current_username() -> str:
    try:
        return str(_user_provider() or "") if _user_provider else ""
    except Exception:  # e.g. called from a worker thread without a session
        return ""


# ── permissions ────────────────────────────────────────────────────────────────
# Roles (the optional ``role`` of a login user, lower-case) that may NOT download / export results.
# Empty = everyone who can sign in may export. Example: EXPORT_BLOCKED_ROLES = frozenset({"viewer"})
EXPORT_BLOCKED_ROLES: frozenset[str] = frozenset()
_role_provider: Callable[[], str] | None = None


def set_role_provider(provider: Callable[[], str] | None) -> None:
    """Register a zero-argument function returning the signed-in user's role (or ``""``)."""
    global _role_provider
    _role_provider = provider


def _current_role() -> str:
    try:
        return str(_role_provider() or "").strip().lower() if _role_provider else ""
    except Exception:
        return ""


def can_export(role: str | None = None) -> bool:
    """May the current user (or the given ``role``) export / download results?

    Always ``True`` when login is turned off (no role is known) or the role is not in
    ``EXPORT_BLOCKED_ROLES``."""
    role = (_current_role() if role is None else str(role or "")).strip().lower()
    return role not in EXPORT_BLOCKED_ROLES


def question_fields(text: str) -> dict[str, Any]:
    """Audit fields describing a user question without storing its text.

    Questions about healthcare appeals can contain provider or member details, so only the length, the
    word count and a short SHA-256 prefix (to spot repeats) are recorded."""
    text = str(text or "")
    return {
        "question_chars": len(text),
        "question_words": len(text.split()),
        "question_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
    }


def audit(event: str, **fields: Any) -> None:
    """Record an audit event. Never raises: a logging problem must not break the user's request."""
    try:
        record = {"ts": round(time.time(), 3), "event": str(event), "user": _current_username(), **fields}
        _audit_log.info(json.dumps(record, default=str, separators=(",", ":")))
    except Exception:
        pass


__all__ = ["UserRecord", "LoginThrottle", "hash_password", "verify_password", "password_problems",
           "parse_users", "normalise_username", "session_status", "audit", "question_fields",
           "set_user_provider", "set_role_provider", "can_export", "EXPORT_BLOCKED_ROLES",
           "save_user_to_env", "clean_display_name", "USERNAME_PATTERN",
           "MIN_PASSWORD_LENGTH", "MAX_PASSWORD_LENGTH"]