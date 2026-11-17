# """Username / password login gate (Streamlit glue for ``core.auth``) with a modern UI.

# Call :func:`require_login` once near the top of ``app.py``, *before* any data is loaded. When login is
# switched off it does nothing, so the application behaves exactly as before. When it is on, nothing
# else in the app runs until the user has signed in.

# Public API is unchanged: ``require_login``, ``render_account_box``, ``user_pill``, ``current_user``,
# ``sign_out``, ``load_config``.

# What is new in the UI
# ---------------------
# * **Login screen** — split layout: a brand panel (animated background, rotating "ask a question" demo,
#   trust chips) and a glass sign-in card with focus glow, gradient button, spinner while verifying.
# * **After sign-in** — a welcome toast, an avatar chip in the header (initials, online dot, name, role)
#   and a profile card with a Sign out button in the sidebar.
# * Everything is plain CSS injected through ``st.markdown``; no extra dependency. Animations are turned
#   off automatically for users who prefer reduced motion.

# Configuration — either source works, no ``.streamlit`` folder is required
# -------------------------------------------------------------------------
# **A. ``.env`` (local; same mechanism as the rest of the app, via ``core.settings``)**::

#     LOGIN_ENABLED=true
#     LOGIN_IDLE_MINUTES=30
#     LOGIN_MAX_SESSION_MINUTES=480
#     LOGIN_MAX_ATTEMPTS=5
#     LOGIN_LOCKOUT_MINUTES=15
#     LOGIN_USERS='{"jsmith":{"name":"Jane Smith","role":"analyst","password_hash":"scrypt$32768$8$1$..."}}'

# Add users with ``python scripts/hash_password.py --env-file .env`` (it merges into ``LOGIN_USERS``).

# **B. Streamlit secrets** (*Secrets* in the app settings on Streamlit Community Cloud, or
# ``.streamlit/secrets.toml``). When a ``[login]`` table exists in the secrets it is used instead of the
# ``.env`` values::

#     [login]
#     enabled = true
#     idle_minutes = 30
#     max_session_minutes = 480
#     max_attempts = 5
#     lockout_minutes = 15

#     [login.users.jsmith]
#     name = "Jane Smith"
#     role = "analyst"
#     password_hash = "scrypt$32768$8$1$..."

# Self-service sign-up (optional)
# -------------------------------
# Set ``LOGIN_REGISTRATION_ENABLED=true`` and ``LOGIN_REGISTRATION_CODE=<at least 8 characters>`` in ``.env``.
# A "Create an account" button then appears under Sign in. A new user enters the access code, a username, a
# display name and a password; the account is saved to ``LOGIN_USERS`` in ``.env`` (salted hash only) and works
# immediately. Without the code anyone who can open the app could create an account, so the button stays
# hidden when the code is missing or too short. It is also hidden when users come from the Streamlit secrets.

# Behaviour
# ---------
# * **Off by default.** No login configuration, or ``enabled = false`` / ``LOGIN_ENABLED=false`` → no gate.
# * **Fails closed.** Enabled but misconfigured (no users, malformed hash) → an error screen and ``st.stop()``.
# * **Sign-in state lives in the browser session only.** Reload, closing the tab, sign-out or a timeout
#   clears the whole session (chat history, tables).
# * Users removed from the configuration lose access on their next interaction.
# * Failed attempts are counted per username across all sessions; the message is identical for unknown
#   usernames and wrong passwords. Events go to the ``datatalk.auth`` logger (never passwords).
# """
# from __future__ import annotations

# import hmac
# import html
# import json
# import logging
# import math
# import time
# import zlib
# from collections.abc import Mapping
# from dataclasses import dataclass
# from pathlib import Path
# from typing import Any

# import streamlit as st

# from components import ui
# from core import auth as A

# log = logging.getLogger("datatalk.auth")

# SESSION_KEY = "_auth"
# NOTICE_KEY = "_auth_notice"
# WELCOME_KEY = "_auth_welcome"
# MODE_KEY = "_auth_mode"       # "login" (default) or "register"
# FAILURE_DELAY_SECONDS = 0.8   # slows scripted guessing; only blocks the failing session
# MIN_REGISTRATION_CODE_LENGTH = 8


# @dataclass(frozen=True)
# class AuthConfig:
#     users: dict[str, A.UserRecord]
#     idle_seconds: int = 30 * 60
#     max_session_seconds: int = 8 * 3600
#     max_attempts: int = 5
#     lockout_seconds: int = 15 * 60
#     register_enabled: bool = False   # "Create account" is offered (needs an access code and .env-based users)
#     register_code: str = ""


# @dataclass(frozen=True)
# class AuthUser:
#     username: str
#     name: str
#     role: str = ""


# # ── configuration ──────────────────────────────────────────────────────────────
# def _truthy(value: Any) -> bool:
#     return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


# def _minutes(section: Mapping, key: str, default: float, *, minimum: float = 0.0) -> int:
#     value = float(section.get(key, default))
#     if value < minimum:
#         raise ValueError(f"{key} must be at least {minimum:g}")
#     return int(value * 60)


# def _secrets_section(secrets: Mapping | None) -> Mapping | None:
#     if secrets is None:
#         try:
#             section = st.secrets.get("login")
#         except Exception:  # no secrets available at all
#             return None
#     else:
#         section = secrets.get("login")
#     return section if isinstance(section, Mapping) else None


# def _settings_section(settings: Any) -> Mapping | None:
#     """The ``LOGIN_*`` values of ``core.settings.Settings`` (environment / ``.env``) as a secrets-style table."""
#     if settings is None:
#         try:
#             from core.settings import get_settings
#             settings = get_settings()
#         except Exception:
#             return None
#     if not hasattr(settings, "login_enabled"):  # settings.py has not been updated: nothing to read
#         return None
#     raw = getattr(settings, "login_users", "")
#     raw = raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw or "")
#     try:
#         users = json.loads(raw) if raw.strip() else {}
#     except ValueError:
#         raise ValueError("LOGIN_USERS is not valid JSON (use single quotes around the whole value in .env)") from None
#     if not isinstance(users, dict):
#         raise ValueError("LOGIN_USERS must be a JSON object of users")
#     code = getattr(settings, "login_registration_code", "")
#     code = code.get_secret_value() if hasattr(code, "get_secret_value") else str(code or "")
#     return {"enabled": settings.login_enabled, "idle_minutes": settings.login_idle_minutes,
#             "max_session_minutes": settings.login_max_session_minutes, "max_attempts": settings.login_max_attempts,
#             "lockout_minutes": settings.login_lockout_minutes, "users": users,
#             "registration_enabled": getattr(settings, "login_registration_enabled", False),
#             "registration_code": code.strip()}


# def load_config(secrets: Mapping | None = None, settings: Any = None) -> AuthConfig | None:
#     """``None`` when login is disabled. Raises ``ValueError`` for an enabled-but-invalid configuration.

#     A ``[login]`` table in the Streamlit secrets wins; otherwise the ``LOGIN_*`` settings are used."""
#     secrets_section = _secrets_section(secrets)
#     section = secrets_section or _settings_section(settings)
#     if not isinstance(section, Mapping) or not _truthy(section.get("enabled", False)):
#         return None
#     from_env = secrets_section is None   # users live in .env, so new accounts can be saved there
#     raw_users = dict(section.get("users") or {})
#     if from_env:  # accounts created on the login screen since the app started (also saved to .env)
#         raw_users = {**_registered_users(), **raw_users}
#     users = A.parse_users(raw_users)
#     if not users:
#         raise ValueError("login is enabled but no users are defined (LOGIN_USERS or [login.users.<username>])")

#     register_enabled, register_code = False, str(section.get("registration_code") or "").strip()
#     if from_env and _truthy(section.get("registration_enabled", False)):
#         if len(register_code) >= MIN_REGISTRATION_CODE_LENGTH:
#             register_enabled = True
#         else:
#             log.warning("registration is enabled but LOGIN_REGISTRATION_CODE is missing or shorter than %d "
#                         "characters: the Create account button is hidden", MIN_REGISTRATION_CODE_LENGTH)
#     return AuthConfig(
#         users=users,
#         idle_seconds=_minutes(section, "idle_minutes", 30, minimum=1),
#         max_session_seconds=_minutes(section, "max_session_minutes", 480, minimum=1),
#         max_attempts=int(section.get("max_attempts", 5)),
#         lockout_seconds=_minutes(section, "lockout_minutes", 15, minimum=1),
#         register_enabled=register_enabled,
#         register_code=register_code if register_enabled else "",
#     )


# @st.cache_resource(show_spinner=False)
# def _throttle(max_attempts: int, lockout_seconds: int) -> A.LoginThrottle:
#     """One counter per process, shared by every browser session."""
#     return A.LoginThrottle(max_attempts, lockout_seconds)


# @st.cache_resource(show_spinner=False)
# def _register_throttle(max_attempts: int, lockout_seconds: int) -> A.LoginThrottle:
#     """Separate counter for wrong access codes (one shared key), so guessing the code is rate-limited too."""
#     return A.LoginThrottle(max_attempts, lockout_seconds)


# @st.cache_resource(show_spinner=False)
# def _registered_users() -> dict[str, dict[str, str]]:
#     """Accounts created since the app started. They are also written to .env; keeping them here makes them
#     usable at once (settings are cached until restart)."""
#     return {}


# # ── session ────────────────────────────────────────────────────────────────────
# def _user_from(record: Mapping) -> AuthUser:
#     return AuthUser(str(record["user"]), str(record.get("name") or record["user"]), str(record.get("role") or ""))


# def current_user() -> AuthUser | None:
#     """The signed-in user, or ``None`` (not signed in, or login is disabled)."""
#     record = st.session_state.get(SESSION_KEY)
#     return _user_from(record) if isinstance(record, Mapping) else None


# def end_session(notice: str = "") -> None:
#     """Drop everything held for this browser session, then show the login screen."""
#     st.session_state.clear()
#     if notice:
#         st.session_state[NOTICE_KEY] = notice
#     st.rerun()


# def _audit_username() -> str:
#     user = current_user()
#     return user.username if user else ""


# def _audit_role() -> str:
#     user = current_user()
#     return user.role if user else ""


# # Lets core.auth.audit() stamp events with the signed-in user and core.auth.can_export() check their role.
# A.set_user_provider(_audit_username)
# A.set_role_provider(_audit_role)


# def sign_out() -> None:
#     user = current_user()
#     log.info("logout user=%s", user.username if user else "?")
#     end_session("You have been signed out.")


# def _stop_with_error(message: str) -> None:
#     ui.page_title("🔒", "DataTalk.AI is not available", "")
#     st.error(message)
#     ui.footer()
#     st.stop()


# # ── styling ────────────────────────────────────────────────────────────────────
# # Profile chip + sidebar account card. Injected on every run once the user is signed in.
# _PROFILE_CSS = """
# <style>
# .dt-user{display:inline-flex;align-items:center;gap:10px;padding:5px 16px 5px 5px;border-radius:999px;
#   background:linear-gradient(135deg,rgba(37,99,235,.20),rgba(124,58,237,.20));
#   border:1px solid rgba(148,163,184,.30);transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease;
#   cursor:default;vertical-align:middle}
# .dt-user:hover{transform:translateY(-1px);border-color:rgba(96,165,250,.8);box-shadow:0 6px 18px rgba(37,99,235,.30)}
# .dt-userbar{--dt-lift:1.8rem;display:flex;justify-content:flex-end;align-items:center;position:relative;z-index:2;
#   margin:calc(var(--dt-lift) * -1) 4px 0 0;animation:dt-slide .5s ease both}
# @keyframes dt-slide{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}
# .dt-av{position:relative;flex:0 0 auto;width:38px;height:38px;border-radius:50%;display:flex;align-items:center;
#   justify-content:center;color:#fff;font-weight:700;font-size:.85rem;letter-spacing:.5px;
#   background:linear-gradient(135deg,hsl(var(--h),82%,56%),hsl(calc(var(--h) + 45),82%,44%));
#   box-shadow:0 0 0 2px rgba(255,255,255,.18)}
# .dt-av.lg{width:60px;height:60px;font-size:1.25rem}
# .dt-av .dt-dot{position:absolute;right:-1px;bottom:-1px;width:11px;height:11px;border-radius:50%;
#   background:#22c55e;border:2px solid #0b1330;animation:dt-pulse 2.4s ease-out infinite}
# .dt-av.lg .dt-dot{width:14px;height:14px;right:1px;bottom:1px}
# .dt-utxt{display:flex;flex-direction:column;line-height:1.15;text-align:left}
# .dt-uhello{font-size:.68rem;opacity:.65}
# .dt-uname{font-size:.9rem;font-weight:700;white-space:nowrap}
# .dt-role{display:inline-block;margin-left:6px;padding:1px 8px;border-radius:999px;font-size:.62rem;font-weight:700;
#   letter-spacing:.6px;text-transform:uppercase;color:#93c5fd;background:rgba(59,130,246,.18);
#   border:1px solid rgba(59,130,246,.35);vertical-align:middle}
# .dt-acct{display:flex;align-items:center;gap:14px;padding:14px;border-radius:16px;margin-bottom:8px;
#   background:linear-gradient(135deg,rgba(37,99,235,.16),rgba(124,58,237,.16));
#   border:1px solid rgba(148,163,184,.25)}
# .dt-acct .dt-aname{font-weight:700;font-size:1rem;line-height:1.2}
# .dt-acct .dt-ameta{font-size:.74rem;opacity:.7;margin-top:3px}
# .st-key-dt_sign_out button{border-radius:12px;border:1px solid rgba(239,68,68,.45);transition:all .2s ease}
# .st-key-dt_sign_out button:hover{background:rgba(239,68,68,.12);border-color:#ef4444;transform:translateY(-1px)}
# @keyframes dt-pulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.6)}70%{box-shadow:0 0 0 7px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}
# @media (prefers-reduced-motion:reduce){.dt-av .dt-dot{animation:none}.dt-user,.st-key-dt_sign_out button{transition:none}}
# </style>
# """

# # Login screen only. Forces its own dark look so it reads the same in light and dark Streamlit themes.
# _LOGIN_CSS = """
# <style>
# [data-testid="stAppViewContainer"]{background:
#   radial-gradient(1100px 600px at 8% -10%,rgba(37,99,235,.38),transparent 60%),
#   radial-gradient(900px 520px at 100% 0%,rgba(124,58,237,.30),transparent 55%),
#   linear-gradient(160deg,#060b1c,#0b1330 55%,#0a1026)!important}
# [data-testid="stHeader"]{background:transparent!important}
# [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stExpandSidebarButton"]{display:none!important}
# .stApp::before,.stApp::after{content:"";position:fixed;border-radius:50%;filter:blur(36px);pointer-events:none;z-index:0}
# .stApp::before{width:520px;height:520px;left:-140px;top:30%;background:radial-gradient(circle,rgba(59,130,246,.35),transparent 65%);
#   animation:dtl-float 16s ease-in-out infinite}
# .stApp::after{width:460px;height:460px;right:-120px;bottom:-80px;background:radial-gradient(circle,rgba(168,85,247,.32),transparent 65%);
#   animation:dtl-float 19s ease-in-out infinite reverse}
# @keyframes dtl-float{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(40px,-30px) scale(1.12)}}
# @keyframes dtl-up{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
# @keyframes dtl-cycle{0%{opacity:0;transform:translateY(10px)}4%,28%{opacity:1;transform:none}33%,100%{opacity:0;transform:translateY(-6px)}}
# @keyframes dtl-dots{0%,20%{opacity:.2}50%{opacity:1}100%{opacity:.2}}
# @keyframes dtl-shine{from{transform:translateX(-120%)}to{transform:translateX(220%)}}
# @keyframes dtl-spin{to{transform:rotate(360deg)}}
# .dtl-hero{position:relative;z-index:1;padding:6vh 1.5rem 0 1rem;animation:dtl-up .7s ease both;color:#e2e8f0}
# .dtl-brand{display:flex;align-items:center;gap:14px;margin-bottom:28px}
# .dtl-orb{width:54px;height:54px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.6rem;
#   background:radial-gradient(circle at 30% 30%,#60a5fa,#2563eb 60%,#1e3a8a);box-shadow:0 0 0 6px rgba(37,99,235,.18),0 10px 30px rgba(37,99,235,.45)}
# .dtl-name{font-size:1.5rem;font-weight:800;color:#f8fafc;letter-spacing:.3px}
# .dtl-sub{font-size:.82rem;color:#94a3b8}
# .dtl-title{font-size:2.6rem;line-height:1.12;font-weight:800;margin:0 0 14px 0;color:#f8fafc}
# .dtl-title span{background:linear-gradient(90deg,#60a5fa,#c084fc);-webkit-background-clip:text;background-clip:text;color:transparent}
# .dtl-lead{font-size:1rem;color:#94a3b8;max-width:34rem;margin:0 0 26px 0}
# .dtl-demo{position:relative;height:128px;max-width:34rem;margin-bottom:22px}
# .dtl-turn{position:absolute;inset:0;opacity:0;animation:dtl-cycle 12s infinite}
# .dtl-q,.dtl-a{padding:10px 14px;border-radius:14px;font-size:.88rem;max-width:92%;backdrop-filter:blur(8px)}
# .dtl-q{background:rgba(37,99,235,.28);border:1px solid rgba(96,165,250,.35);color:#e0edff;margin-left:auto;width:fit-content}
# .dtl-a{margin-top:10px;background:rgba(15,23,42,.6);border:1px solid rgba(148,163,184,.22);color:#cbd5e1;width:fit-content}
# .dtl-a i{font-style:normal;display:inline-block;animation:dtl-dots 1.2s infinite}
# .dtl-a i:nth-child(2){animation-delay:.2s}.dtl-a i:nth-child(3){animation-delay:.4s}
# .dtl-chips{display:flex;flex-wrap:wrap;gap:10px}
# .dtl-chip{padding:7px 14px;border-radius:999px;font-size:.78rem;color:#cbd5e1;background:rgba(148,163,184,.10);
#   border:1px solid rgba(148,163,184,.22);transition:all .2s ease}
# .dtl-chip:hover{transform:translateY(-2px);border-color:rgba(96,165,250,.7);color:#fff;background:rgba(59,130,246,.16)}
# .st-key-dtl_card{position:relative;z-index:1;margin-top:7vh;padding:30px 28px 18px;border-radius:22px;
#   background:rgba(15,23,42,.66);backdrop-filter:blur(20px);border:1px solid rgba(148,163,184,.22);
#   box-shadow:0 30px 70px rgba(2,6,23,.55),inset 0 1px 0 rgba(255,255,255,.06);animation:dtl-up .7s .1s ease both}
# .dtl-card-head{text-align:center;margin-bottom:6px}
# .dtl-lock{width:52px;height:52px;margin:0 auto 10px;border-radius:16px;display:flex;align-items:center;justify-content:center;
#   font-size:1.5rem;background:linear-gradient(135deg,#2563eb,#7c3aed);box-shadow:0 10px 26px rgba(79,70,229,.5)}
# .dtl-card-title{font-size:1.4rem;font-weight:800;color:#f8fafc}
# .dtl-card-sub{font-size:.85rem;color:#94a3b8;margin-top:2px}
# .st-key-dtl_card [data-testid="stForm"]{border:0;padding:0}
# .st-key-dtl_card label p{color:#cbd5e1!important;font-size:.82rem!important;font-weight:600!important}
# .st-key-dtl_card [data-baseweb="input"],.st-key-dtl_card [data-baseweb="base-input"]{border-radius:12px!important;
#   background:rgba(2,6,23,.55)!important;border-color:rgba(148,163,184,.28)!important;transition:box-shadow .2s ease,border-color .2s ease}
# .st-key-dtl_card [data-baseweb="input"]:focus-within{border-color:#60a5fa!important;box-shadow:0 0 0 4px rgba(96,165,250,.25)!important}
# .st-key-dtl_card input{color:#f8fafc!important;-webkit-text-fill-color:#f8fafc!important;caret-color:#60a5fa;padding:.7rem .85rem!important}
# .st-key-dtl_card input::placeholder{color:#64748b!important;-webkit-text-fill-color:#64748b!important}
# .st-key-dtl_card [data-baseweb="input"] button svg{fill:#94a3b8!important}
# .st-key-dtl_card [data-testid="stFormSubmitButton"] button{position:relative;overflow:hidden;width:100%;border:0;border-radius:12px;
#   padding:.72rem 1rem;font-weight:700;letter-spacing:.3px;color:#fff;background:linear-gradient(90deg,#2563eb,#7c3aed);
#   box-shadow:0 10px 24px rgba(79,70,229,.45);transition:transform .2s ease,box-shadow .2s ease,filter .2s ease}
# .st-key-dtl_card [data-testid="stFormSubmitButton"] button:hover{transform:translateY(-2px);filter:brightness(1.08);
#   box-shadow:0 16px 34px rgba(79,70,229,.6)}
# .st-key-dtl_card [data-testid="stFormSubmitButton"] button:active{transform:translateY(0)}
# .st-key-dtl_card [data-testid="stFormSubmitButton"] button::after{content:"";position:absolute;top:0;left:0;width:40%;height:100%;
#   background:linear-gradient(100deg,transparent,rgba(255,255,255,.35),transparent);transform:translateX(-120%)}
# .st-key-dtl_card [data-testid="stFormSubmitButton"] button:hover::after{animation:dtl-shine .9s ease}
# .st-key-dtl_card [data-testid="stCaptionContainer"]{color:#94a3b8;text-align:center}
# .st-key-dtl_card [data-testid="stAlert"]{border-radius:12px}
# .dtl-or{display:flex;align-items:center;gap:12px;margin:14px 0 2px;color:#64748b;font-size:.78rem}
# .dtl-or::before,.dtl-or::after{content:"";flex:1;height:1px;background:rgba(148,163,184,.22)}
# .st-key-dtl_card [data-testid="stButton"] button{width:100%;border-radius:12px;padding:.62rem 1rem;font-weight:600;
#   background:rgba(148,163,184,.08);border:1px solid rgba(148,163,184,.30);transition:all .2s ease}
# .st-key-dtl_card [data-testid="stButton"] button p{color:#e2e8f0!important}
# .st-key-dtl_card [data-testid="stButton"] button:hover{border-color:#60a5fa;background:rgba(59,130,246,.16);
#   transform:translateY(-1px);box-shadow:0 8px 20px rgba(37,99,235,.25)}
# @media (max-width:900px){.dtl-lead,.dtl-demo,.dtl-chips{display:none}.dtl-title{font-size:1.9rem}.dtl-hero{padding-top:1rem}
#   .st-key-dtl_card{margin-top:1rem}}
# @media (prefers-reduced-motion:reduce){.stApp::before,.stApp::after,.dtl-hero,.st-key-dtl_card,.dtl-turn,.dtl-a i{animation:none!important}
#   .dtl-turn:first-child{opacity:1}.dtl-turn:not(:first-child){display:none}}
# </style>
# """

# _DEMO_TURNS = (
#     ("Which provider types have the highest overturn rate?", "Comparing determinations by provider type"),
#     ("How many open appeals are past the SLA?", "Counting open cases older than the SLA window"),
#     ("Show monthly volume for escalated appeals", "Trending escalations by received month"),
# )
# _TRUST_CHIPS = ("🔐 Salted scrypt passwords", "🛡️ Evidence-checked answers", "📜 Audit-logged access")


# def _initials(name: str) -> str:
#     words = [w for w in str(name).replace(".", " ").split() if w]
#     if not words:
#         return "?"
#     letters = words[0][0] + (words[-1][0] if len(words) > 1 else "")
#     return html.escape(letters.upper())


# def _hue(username: str) -> int:
#     """Stable avatar colour per user (no security meaning)."""
#     return zlib.crc32(username.encode("utf-8")) % 360


# def _avatar(user: AuthUser, *, large: bool = False) -> str:
#     return (f"<div class='dt-av{' lg' if large else ''}' style='--h:{_hue(user.username)}'>"
#             f"{_initials(user.name)}<span class='dt-dot'></span></div>")


# def _hero_html() -> str:
#     turns = "".join(
#         f"<div class='dtl-turn' style='animation-delay:{i * 4}s'><div class='dtl-q'>{html.escape(q)}</div>"
#         f"<div class='dtl-a'>🧠 {html.escape(a)} <i>●</i><i>●</i><i>●</i></div></div>"
#         for i, (q, a) in enumerate(_DEMO_TURNS))
#     chips = "".join(f"<span class='dtl-chip'>{html.escape(c)}</span>" for c in _TRUST_CHIPS)
#     return (
#         "<div class='dtl-hero'>"
#         "<div class='dtl-brand'><div class='dtl-orb'>🧠</div><div><div class='dtl-name'>DataTalk.AI</div>"
#         "<div class='dtl-sub'>Healthcare Appeals Intelligence Platform</div></div></div>"
#         "<h1 class='dtl-title'>Ask your appeals data <span>anything.</span></h1>"
#         "<p class='dtl-lead'>Conversational analytics on governed Databricks data, with every number "
#         "checked against evidence before you see it.</p>"
#         f"<div class='dtl-demo'>{turns}</div><div class='dtl-chips'>{chips}</div></div>")


# # ── gate ───────────────────────────────────────────────────────────────────────
# def require_login() -> AuthUser | None:
#     """Gate for the whole app. Returns the signed-in user, ``None`` when login is disabled; otherwise it
#     renders the login screen and stops the script."""
#     try:
#         cfg = load_config()
#     except Exception as exc:
#         log.error("login configuration invalid: %s", exc)
#         _stop_with_error("Login is turned on but its configuration is invalid. Ask the application owner to "
#                          "check the LOGIN_* settings (or the [login] section of the app secrets).")
#         return None
#     if cfg is None:
#         return None

#     record = st.session_state.get(SESSION_KEY)
#     if isinstance(record, dict):
#         now = time.time()
#         status = A.session_status(record, now, cfg.idle_seconds, cfg.max_session_seconds)
#         if record.get("user") not in cfg.users:
#             log.info("session ended: user %s no longer configured", record.get("user"))
#             end_session("Your access has changed. Please sign in again.")
#         elif status == "idle":
#             log.info("session ended: idle user=%s", record.get("user"))
#             end_session("You were signed out after a period of inactivity.")
#         elif status == "expired":
#             log.info("session ended: maximum length user=%s", record.get("user"))
#             end_session("Your session has reached its time limit. Please sign in again.")
#         record["last_seen"] = now
#         user = _user_from(record)
#         if st.session_state.pop(WELCOME_KEY, False):
#             st.toast(f"Welcome back, {user.name.split()[0]} 👋", icon="✅")
#         return user

#     _render_login(cfg)
#     st.stop()
#     return None


# def _card_head(icon: str, title: str, subtitle: str) -> None:
#     st.markdown(
#         f"<div class='dtl-card-head'><div class='dtl-lock'>{icon}</div><div class='dtl-card-title'>{html.escape(title)}</div>"
#         f"<div class='dtl-card-sub'>{html.escape(subtitle)}</div></div>", unsafe_allow_html=True)
#     notice = st.session_state.pop(NOTICE_KEY, "")
#     if notice:
#         st.info(notice)


# def _set_mode(mode: str) -> None:
#     st.session_state[MODE_KEY] = mode
#     st.rerun()


# def _render_login(cfg: AuthConfig) -> None:
#     st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
#     mode = st.session_state.get(MODE_KEY, "login")
#     if mode == "register" and not cfg.register_enabled:
#         mode = "login"
#     hero, form = st.columns([1.15, 0.85], gap="large", vertical_alignment="top")
#     with hero:
#         st.markdown(_hero_html(), unsafe_allow_html=True)
#     with form:
#         with st.container(key="dtl_card"):
#             if mode == "register":
#                 _render_register_card(cfg)
#             else:
#                 _render_signin_card(cfg)
#     ui.footer()


# def _render_signin_card(cfg: AuthConfig) -> None:
#     _card_head("🔒", "Welcome back", "Sign in to continue to your workspace")
#     with st.form("dt_login_form", clear_on_submit=False, border=False):
#         username = st.text_input("Username", max_chars=64, autocomplete="username",
#                                  placeholder="Enter your username")
#         password = st.text_input("Password", type="password", max_chars=A.MAX_PASSWORD_LENGTH,
#                                  autocomplete="current-password", placeholder="Enter your password")
#         submitted = st.form_submit_button("Sign in  →", type="primary", width="stretch")
#     if submitted:
#         _attempt(cfg, username, password)
#     if cfg.register_enabled:
#         st.markdown("<div class='dtl-or'>New here?</div>", unsafe_allow_html=True)
#         if st.button("✨ Create an account", key="dtl_go_register", width="stretch"):
#             _set_mode("register")
#     st.caption("🛡️ Access is limited to authorised users. Activity is logged.")


# def _render_register_card(cfg: AuthConfig) -> None:
#     _card_head("✨", "Create your account", "You need the access code from your administrator")
#     with st.form("dt_register_form", clear_on_submit=False, border=False):
#         code = st.text_input("Access code", type="password", max_chars=128, key="dt_reg_code",
#                              autocomplete="off", placeholder="Provided by your administrator")
#         username = st.text_input("Username", max_chars=64, key="dt_reg_user", autocomplete="username",
#                                  placeholder="Letters, digits and . _ @ -")
#         display = st.text_input("Display name", max_chars=80, key="dt_reg_name", autocomplete="name",
#                                 placeholder="e.g. Jane Smith")
#         password = st.text_input("Password", type="password", max_chars=A.MAX_PASSWORD_LENGTH, key="dt_reg_pw",
#                                  autocomplete="new-password", placeholder=f"At least {A.MIN_PASSWORD_LENGTH} characters")
#         confirm = st.text_input("Confirm password", type="password", max_chars=A.MAX_PASSWORD_LENGTH,
#                                 key="dt_reg_pw2", autocomplete="new-password", placeholder="Repeat the password")
#         submitted = st.form_submit_button("Create account  →", type="primary", width="stretch")
#     if submitted:
#         _register(cfg, code, username, display, password, confirm)
#     st.markdown("<div class='dtl-or'>Already have an account?</div>", unsafe_allow_html=True)
#     if st.button("← Back to sign in", key="dtl_go_login", width="stretch"):
#         _set_mode("login")
#     st.caption("🛡️ Your password is stored only as a salted scrypt hash. Activity is logged.")


# def _attempt(cfg: AuthConfig, username: str, password: str) -> None:
#     key = A.normalise_username(username)
#     if not key or not password:
#         st.error("Enter your username and password.")
#         return
#     throttle = _throttle(cfg.max_attempts, cfg.lockout_seconds)
#     now = time.time()
#     wait = throttle.locked_for(key, now)
#     if wait:
#         log.warning("login blocked (locked) user=%s", key[:64])
#         st.error(f"Too many failed attempts. Try again in {math.ceil(wait / 60)} minute(s).")
#         return

#     record = cfg.users.get(key)
#     with st.spinner("Verifying credentials…"):
#         verified = A.verify_password(password, record.password_hash if record else None)
#     if verified and record:
#         throttle.reset(key)
#         stamp = time.time()
#         st.session_state[SESSION_KEY] = {"user": record.username, "name": record.name, "role": record.role,
#                                          "login_at": stamp, "last_seen": stamp}
#         st.session_state[WELCOME_KEY] = True
#         log.info("login ok user=%s", record.username)
#         st.rerun()
#         return

#     locked = throttle.fail(key, time.time())
#     log.warning("login failed user=%s%s", key[:64], " (now locked)" if locked else "")
#     time.sleep(FAILURE_DELAY_SECONDS)
#     if locked:
#         st.error(f"Too many failed attempts. Try again in {math.ceil(locked / 60)} minute(s).")
#     else:
#         st.error("Incorrect username or password.")


# # ── registration ───────────────────────────────────────────────────────────────
# def _env_path() -> Path:
#     from core.settings import PROJECT_ROOT   # same file pydantic-settings reads (PROJECT_ROOT / ".env")
#     return PROJECT_ROOT / ".env"


# def _registration_problems(cfg: AuthConfig, key: str, password: str, confirm: str) -> list[str]:
#     """Why a new account is rejected (empty list = fine). ``key`` is the normalised username."""
#     problems = []
#     if not A.USERNAME_PATTERN.fullmatch(key):
#         problems.append("Username may contain only letters, digits and . _ @ - (max 64 characters).")
#     elif key in cfg.users:
#         problems.append("That username is not available.")
#     if password != confirm:
#         problems.append("The passwords do not match.")
#     problems += [f"Password: {p}." for p in A.password_problems(password)]
#     return problems


# def _register(cfg: AuthConfig, code: str, username: str, display: str, password: str, confirm: str) -> None:
#     throttle = _register_throttle(cfg.max_attempts, cfg.lockout_seconds)
#     wait = throttle.locked_for("code", time.time())
#     if wait:
#         log.warning("registration blocked (locked)")
#         st.error(f"Too many failed attempts. Try again in {math.ceil(wait / 60)} minute(s).")
#         return
#     if not hmac.compare_digest(str(code).strip().encode("utf-8"), cfg.register_code.encode("utf-8")):
#         locked = throttle.fail("code", time.time())
#         log.warning("registration rejected: wrong access code%s", " (now locked)" if locked else "")
#         time.sleep(FAILURE_DELAY_SECONDS)
#         if locked:
#             st.error(f"Too many failed attempts. Try again in {math.ceil(locked / 60)} minute(s).")
#         else:
#             st.error("Invalid access code.")
#         return

#     key = A.normalise_username(username)
#     problems = _registration_problems(cfg, key, password, confirm)
#     if problems:
#         st.error("\n".join(f"- {p}" for p in problems))
#         return

#     with st.spinner("Creating your account…"):
#         entry = {"name": A.clean_display_name(display) or key, "password_hash": A.hash_password(password)}
#         try:
#             A.save_user_to_env(_env_path(), key, entry)
#         except (OSError, ValueError):
#             log.exception("could not save new user %s to .env", key)
#             st.error("Your account could not be saved. Please contact the administrator.")
#             return
#     _registered_users()[key] = entry   # usable immediately; .env keeps it across restarts
#     throttle.reset("code")
#     log.info("register ok user=%s", key)
#     A.audit("register", new_user=key)
#     st.session_state[NOTICE_KEY] = f"Account created for **{key}**. You can sign in now."
#     _set_mode("login")


# # ── account UI (sidebar / header) ──────────────────────────────────────────────
# def _session_minutes() -> int:
#     record = st.session_state.get(SESSION_KEY)
#     try:
#         return max(0, int((time.time() - float(record["login_at"])) // 60))
#     except (KeyError, TypeError, ValueError):
#         return 0


# def render_account_box() -> None:
#     """Profile card for the signed-in user and a Sign out button. Renders nothing when login is disabled."""
#     user = current_user()
#     if user is None:
#         return
#     role = f"<span class='dt-role' style='margin-left:0'>{html.escape(user.role)}</span>" if user.role else ""
#     minutes = _session_minutes()
#     active = "Signed in just now" if minutes < 1 else f"Signed in for {minutes} min"
#     st.markdown(
#         _PROFILE_CSS.strip() +
#         f"<div class='dt-acct'>{_avatar(user, large=True)}<div><div class='dt-aname'>{html.escape(user.name)}</div>"
#         f"{role}<div class='dt-ameta'>🟢 {active}</div></div></div>",
#         unsafe_allow_html=True)
#     if st.button("🚪 Sign out", key="dt_sign_out", width="stretch"):
#         sign_out()


# def user_pill() -> str:
#     """Header chip for the signed-in user: avatar with online dot, name and role.
#     Returns an empty string when login is disabled."""
#     user = current_user()
#     if user is None:
#         return ""
#     role = f"<span class='dt-role'>{html.escape(user.role)}</span>" if user.role else ""
#     return (f"<div class='dt-user' title='Signed in as {html.escape(user.name)}'>{_avatar(user)}"
#             f"<div class='dt-utxt'><span class='dt-uhello'>Welcome back</span>"
#             f"<span class='dt-uname'>{html.escape(user.name)}{role}</span></div></div>")


# def render_user_banner() -> None:
#     """Welcome chip at the top right, under the Deploy button and above the header card (call it just before
#     ``ui.header``). Carries the profile CSS in the same element so it adds no extra gap to the page.
#     Renders nothing when login is disabled. Tune the vertical position with ``--dt-lift`` in the CSS."""
#     chip = user_pill()
#     if chip:
#         st.markdown(_PROFILE_CSS.strip() + f"<div class='dt-userbar'>{chip}</div>", unsafe_allow_html=True)


# __all__ = ["require_login", "render_account_box", "render_user_banner", "user_pill", "current_user", "sign_out", "load_config",
#            "AuthConfig", "AuthUser"]






"""Username / password login gate (Streamlit glue for ``core.auth``) with a modern UI.

Call :func:`require_login` once near the top of ``app.py``, *before* any data is loaded. When login is
switched off it does nothing, so the application behaves exactly as before. When it is on, nothing
else in the app runs until the user has signed in.

Public API is unchanged: ``require_login``, ``render_account_box``, ``user_pill``, ``current_user``,
``sign_out``, ``load_config``.

What is new in the UI
---------------------
* **Login screen** — split layout: a brand panel (animated background, rotating "ask a question" demo,
  trust chips) and a glass sign-in card with focus glow, gradient button, spinner while verifying.
* **After sign-in** — a welcome toast, an avatar chip in the header (initials, online dot, name, role)
  and a profile card with a Sign out button in the sidebar.
* Everything is plain CSS injected through ``st.markdown``; no extra dependency. Animations are turned
  off automatically for users who prefer reduced motion.

Configuration — either source works, no ``.streamlit`` folder is required
-------------------------------------------------------------------------
**A. ``.env`` (local; same mechanism as the rest of the app, via ``core.settings``)**::

    LOGIN_ENABLED=true
    LOGIN_IDLE_MINUTES=30
    LOGIN_MAX_SESSION_MINUTES=480
    LOGIN_MAX_ATTEMPTS=5
    LOGIN_LOCKOUT_MINUTES=15
    LOGIN_USERS='{"jsmith":{"name":"Jane Smith","role":"analyst","password_hash":"scrypt$32768$8$1$..."}}'

Add users with ``python scripts/hash_password.py --env-file .env`` (it merges into ``LOGIN_USERS``).

**B. Streamlit secrets** (*Secrets* in the app settings on Streamlit Community Cloud, or
``.streamlit/secrets.toml``). When a ``[login]`` table exists in the secrets it is used instead of the
``.env`` values::

    [login]
    enabled = true
    idle_minutes = 30
    max_session_minutes = 480
    max_attempts = 5
    lockout_minutes = 15

    [login.users.jsmith]
    name = "Jane Smith"
    role = "analyst"
    password_hash = "scrypt$32768$8$1$..."

Self-service sign-up (optional)
-------------------------------
Set ``LOGIN_REGISTRATION_ENABLED=true`` and ``LOGIN_REGISTRATION_CODE=<at least 8 characters>`` in ``.env``.
A "Create an account" button then appears under Sign in. A new user enters the access code, a username, a
display name and a password; the account is saved to ``LOGIN_USERS`` in ``.env`` (salted hash only) and works
immediately. Without the code anyone who can open the app could create an account, so the button stays
hidden when the code is missing or too short. It is also hidden when users come from the Streamlit secrets.

Behaviour
---------
* **Off by default.** No login configuration, or ``enabled = false`` / ``LOGIN_ENABLED=false`` → no gate.
* **Fails closed.** Enabled but misconfigured (no users, malformed hash) → an error screen and ``st.stop()``.
* **Sign-in state lives in the browser session only.** Reload, closing the tab, sign-out or a timeout
  clears the whole session (chat history, tables).
* Users removed from the configuration lose access on their next interaction.
* Failed attempts are counted per username across all sessions; the message is identical for unknown
  usernames and wrong passwords. Events go to the ``datatalk.auth`` logger (never passwords).
"""
from __future__ import annotations

import hmac
import html
import json
import logging
import math
import time
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st

from components import ui
from core import auth as A

log = logging.getLogger("datatalk.auth")

SESSION_KEY = "_auth"
NOTICE_KEY = "_auth_notice"
WELCOME_KEY = "_auth_welcome"
MODE_KEY = "_auth_mode"       # "login" (default) or "register"
FAILURE_DELAY_SECONDS = 0.8   # slows scripted guessing; only blocks the failing session
MIN_REGISTRATION_CODE_LENGTH = 8


@dataclass(frozen=True)
class AuthConfig:
    users: dict[str, A.UserRecord]
    idle_seconds: int = 30 * 60
    max_session_seconds: int = 8 * 3600
    max_attempts: int = 5
    lockout_seconds: int = 15 * 60
    register_enabled: bool = False   # "Create account" is offered (needs an access code and .env-based users)
    register_code: str = ""


@dataclass(frozen=True)
class AuthUser:
    username: str
    name: str
    role: str = ""


# ── configuration ──────────────────────────────────────────────────────────────
def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def _minutes(section: Mapping, key: str, default: float, *, minimum: float = 0.0) -> int:
    value = float(section.get(key, default))
    if value < minimum:
        raise ValueError(f"{key} must be at least {minimum:g}")
    return int(value * 60)


def _secrets_section(secrets: Mapping | None) -> Mapping | None:
    if secrets is None:
        try:
            section = st.secrets.get("login")
        except Exception:  # no secrets available at all
            return None
    else:
        section = secrets.get("login")
    return section if isinstance(section, Mapping) else None


def _settings_section(settings: Any) -> Mapping | None:
    """The ``LOGIN_*`` values of ``core.settings.Settings`` (environment / ``.env``) as a secrets-style table."""
    if settings is None:
        try:
            from core.settings import get_settings
            settings = get_settings()
        except Exception:
            return None
    if not hasattr(settings, "login_enabled"):  # settings.py has not been updated: nothing to read
        return None
    raw = getattr(settings, "login_users", "")
    raw = raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw or "")
    try:
        users = json.loads(raw) if raw.strip() else {}
    except ValueError:
        raise ValueError("LOGIN_USERS is not valid JSON (use single quotes around the whole value in .env)") from None
    if not isinstance(users, dict):
        raise ValueError("LOGIN_USERS must be a JSON object of users")
    code = getattr(settings, "login_registration_code", "")
    code = code.get_secret_value() if hasattr(code, "get_secret_value") else str(code or "")
    return {"enabled": settings.login_enabled, "idle_minutes": settings.login_idle_minutes,
            "max_session_minutes": settings.login_max_session_minutes, "max_attempts": settings.login_max_attempts,
            "lockout_minutes": settings.login_lockout_minutes, "users": users,
            "registration_enabled": getattr(settings, "login_registration_enabled", False),
            "registration_code": code.strip()}


def load_config(secrets: Mapping | None = None, settings: Any = None) -> AuthConfig | None:
    """``None`` when login is disabled. Raises ``ValueError`` for an enabled-but-invalid configuration.

    A ``[login]`` table in the Streamlit secrets wins; otherwise the ``LOGIN_*`` settings are used."""
    secrets_section = _secrets_section(secrets)
    section = secrets_section or _settings_section(settings)
    if not isinstance(section, Mapping) or not _truthy(section.get("enabled", False)):
        return None
    from_env = secrets_section is None   # users live in .env, so new accounts can be saved there
    raw_users = dict(section.get("users") or {})
    if from_env:  # accounts created on the login screen since the app started (also saved to .env)
        raw_users = {**_registered_users(), **raw_users}
    users = A.parse_users(raw_users)
    if not users:
        raise ValueError("login is enabled but no users are defined (LOGIN_USERS or [login.users.<username>])")

    register_enabled, register_code = False, str(section.get("registration_code") or "").strip()
    if from_env and _truthy(section.get("registration_enabled", False)):
        if len(register_code) >= MIN_REGISTRATION_CODE_LENGTH:
            register_enabled = True
        else:
            log.warning("registration is enabled but LOGIN_REGISTRATION_CODE is missing or shorter than %d "
                        "characters: the Create account button is hidden", MIN_REGISTRATION_CODE_LENGTH)
    return AuthConfig(
        users=users,
        idle_seconds=_minutes(section, "idle_minutes", 30, minimum=1),
        max_session_seconds=_minutes(section, "max_session_minutes", 480, minimum=1),
        max_attempts=int(section.get("max_attempts", 5)),
        lockout_seconds=_minutes(section, "lockout_minutes", 15, minimum=1),
        register_enabled=register_enabled,
        register_code=register_code if register_enabled else "",
    )


@st.cache_resource(show_spinner=False)
def _throttle(max_attempts: int, lockout_seconds: int) -> A.LoginThrottle:
    """One counter per process, shared by every browser session."""
    return A.LoginThrottle(max_attempts, lockout_seconds)


@st.cache_resource(show_spinner=False)
def _register_throttle(max_attempts: int, lockout_seconds: int) -> A.LoginThrottle:
    """Separate counter for wrong access codes (one shared key), so guessing the code is rate-limited too."""
    return A.LoginThrottle(max_attempts, lockout_seconds)


@st.cache_resource(show_spinner=False)
def _registered_users() -> dict[str, dict[str, str]]:
    """Accounts created since the app started. They are also written to .env; keeping them here makes them
    usable at once (settings are cached until restart)."""
    return {}


# ── session ────────────────────────────────────────────────────────────────────
def _user_from(record: Mapping) -> AuthUser:
    return AuthUser(str(record["user"]), str(record.get("name") or record["user"]), str(record.get("role") or ""))


def current_user() -> AuthUser | None:
    """The signed-in user, or ``None`` (not signed in, or login is disabled)."""
    record = st.session_state.get(SESSION_KEY)
    return _user_from(record) if isinstance(record, Mapping) else None


def end_session(notice: str = "") -> None:
    """Drop everything held for this browser session, then show the login screen."""
    st.session_state.clear()
    if notice:
        st.session_state[NOTICE_KEY] = notice
    st.rerun()


def _audit_username() -> str:
    user = current_user()
    return user.username if user else ""


def _audit_role() -> str:
    user = current_user()
    return user.role if user else ""


# Lets core.auth.audit() stamp events with the signed-in user and core.auth.can_export() check their role.
A.set_user_provider(_audit_username)
A.set_role_provider(_audit_role)


def sign_out() -> None:
    user = current_user()
    log.info("logout user=%s", user.username if user else "?")
    end_session("You have been signed out.")


def _stop_with_error(message: str) -> None:
    ui.page_title("🔒", "DataTalk.AI is not available", "")
    st.error(message)
    ui.footer()
    st.stop()


# ── styling ────────────────────────────────────────────────────────────────────
# Profile chip + sidebar account card. Injected on every run once the user is signed in.
_PROFILE_CSS = """
<style>
.dt-user{display:inline-flex;align-items:center;gap:10px;padding:5px 16px 5px 5px;border-radius:999px;
  background:linear-gradient(135deg,rgba(37,99,235,.20),rgba(124,58,237,.20));
  border:1px solid rgba(148,163,184,.30);transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease;
  cursor:default;vertical-align:middle}
.dt-user:hover{transform:translateY(-1px);border-color:rgba(96,165,250,.8);box-shadow:0 6px 18px rgba(37,99,235,.30)}
.dt-userbar{display:flex;justify-content:flex-start;align-items:center;margin:0 0 10px 6px;animation:dt-slide .5s ease both}
@keyframes dt-slide{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}
.dt-av{position:relative;flex:0 0 auto;width:38px;height:38px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;color:#fff;font-weight:700;font-size:.85rem;letter-spacing:.5px;
  background:linear-gradient(135deg,hsl(var(--h),82%,56%),hsl(calc(var(--h) + 45),82%,44%));
  box-shadow:0 0 0 2px rgba(255,255,255,.18)}
.dt-av.lg{width:60px;height:60px;font-size:1.25rem}
.dt-av .dt-dot{position:absolute;right:-1px;bottom:-1px;width:11px;height:11px;border-radius:50%;
  background:#22c55e;border:2px solid #0b1330;animation:dt-pulse 2.4s ease-out infinite}
.dt-av.lg .dt-dot{width:14px;height:14px;right:1px;bottom:1px}
.dt-utxt{display:flex;flex-direction:column;line-height:1.15;text-align:left}
.dt-uhello{font-size:.68rem;opacity:.65}
.dt-uname{font-size:.9rem;font-weight:700;white-space:nowrap}
.dt-role{display:inline-block;margin-left:6px;padding:1px 8px;border-radius:999px;font-size:.62rem;font-weight:700;
  letter-spacing:.6px;text-transform:uppercase;color:#93c5fd;background:rgba(59,130,246,.18);
  border:1px solid rgba(59,130,246,.35);vertical-align:middle}
.dt-acct{display:flex;align-items:center;gap:14px;padding:14px;border-radius:16px;margin-bottom:8px;
  background:linear-gradient(135deg,rgba(37,99,235,.16),rgba(124,58,237,.16));
  border:1px solid rgba(148,163,184,.25)}
.dt-acct .dt-aname{font-weight:700;font-size:1rem;line-height:1.2}
.dt-acct .dt-ameta{font-size:.74rem;opacity:.7;margin-top:3px}
.st-key-dt_sign_out button{border-radius:12px;border:1px solid rgba(239,68,68,.45);transition:all .2s ease}
.st-key-dt_sign_out button:hover{background:rgba(239,68,68,.12);border-color:#ef4444;transform:translateY(-1px)}
@keyframes dt-pulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.6)}70%{box-shadow:0 0 0 7px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}
@media (prefers-reduced-motion:reduce){.dt-av .dt-dot{animation:none}.dt-user,.st-key-dt_sign_out button{transition:none}}
</style>
"""

# Login screen only. Forces its own dark look so it reads the same in light and dark Streamlit themes.
_LOGIN_CSS = """
<style>
[data-testid="stAppViewContainer"]{background:
  radial-gradient(1100px 600px at 8% -10%,rgba(37,99,235,.38),transparent 60%),
  radial-gradient(900px 520px at 100% 0%,rgba(124,58,237,.30),transparent 55%),
  linear-gradient(160deg,#060b1c,#0b1330 55%,#0a1026)!important}
[data-testid="stHeader"]{background:transparent!important}
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stExpandSidebarButton"]{display:none!important}
.stApp::before,.stApp::after{content:"";position:fixed;border-radius:50%;filter:blur(36px);pointer-events:none;z-index:0}
.stApp::before{width:520px;height:520px;left:-140px;top:30%;background:radial-gradient(circle,rgba(59,130,246,.35),transparent 65%);
  animation:dtl-float 16s ease-in-out infinite}
.stApp::after{width:460px;height:460px;right:-120px;bottom:-80px;background:radial-gradient(circle,rgba(168,85,247,.32),transparent 65%);
  animation:dtl-float 19s ease-in-out infinite reverse}
@keyframes dtl-float{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(40px,-30px) scale(1.12)}}
@keyframes dtl-up{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
@keyframes dtl-cycle{0%{opacity:0;transform:translateY(10px)}4%,28%{opacity:1;transform:none}33%,100%{opacity:0;transform:translateY(-6px)}}
@keyframes dtl-dots{0%,20%{opacity:.2}50%{opacity:1}100%{opacity:.2}}
@keyframes dtl-shine{from{transform:translateX(-120%)}to{transform:translateX(220%)}}
@keyframes dtl-spin{to{transform:rotate(360deg)}}
.dtl-hero{position:relative;z-index:1;padding:6vh 1.5rem 0 1rem;animation:dtl-up .7s ease both;color:#e2e8f0}
.dtl-brand{display:flex;align-items:center;gap:14px;margin-bottom:28px}
.dtl-orb{width:54px;height:54px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.6rem;
  background:radial-gradient(circle at 30% 30%,#60a5fa,#2563eb 60%,#1e3a8a);box-shadow:0 0 0 6px rgba(37,99,235,.18),0 10px 30px rgba(37,99,235,.45)}
.dtl-name{font-size:1.5rem;font-weight:800;color:#f8fafc;letter-spacing:.3px}
.dtl-sub{font-size:.82rem;color:#94a3b8}
.dtl-title{font-size:2.6rem;line-height:1.12;font-weight:800;margin:0 0 14px 0;color:#f8fafc}
.dtl-title span{background:linear-gradient(90deg,#60a5fa,#c084fc);-webkit-background-clip:text;background-clip:text;color:transparent}
.dtl-lead{font-size:1rem;color:#94a3b8;max-width:34rem;margin:0 0 26px 0}
.dtl-demo{position:relative;height:128px;max-width:34rem;margin-bottom:22px}
.dtl-turn{position:absolute;inset:0;opacity:0;animation:dtl-cycle 12s infinite}
.dtl-q,.dtl-a{padding:10px 14px;border-radius:14px;font-size:.88rem;max-width:92%;backdrop-filter:blur(8px)}
.dtl-q{background:rgba(37,99,235,.28);border:1px solid rgba(96,165,250,.35);color:#e0edff;margin-left:auto;width:fit-content}
.dtl-a{margin-top:10px;background:rgba(15,23,42,.6);border:1px solid rgba(148,163,184,.22);color:#cbd5e1;width:fit-content}
.dtl-a i{font-style:normal;display:inline-block;animation:dtl-dots 1.2s infinite}
.dtl-a i:nth-child(2){animation-delay:.2s}.dtl-a i:nth-child(3){animation-delay:.4s}
.dtl-chips{display:flex;flex-wrap:wrap;gap:10px}
.dtl-chip{padding:7px 14px;border-radius:999px;font-size:.78rem;color:#cbd5e1;background:rgba(148,163,184,.10);
  border:1px solid rgba(148,163,184,.22);transition:all .2s ease}
.dtl-chip:hover{transform:translateY(-2px);border-color:rgba(96,165,250,.7);color:#fff;background:rgba(59,130,246,.16)}
.st-key-dtl_card{position:relative;z-index:1;margin-top:7vh;padding:30px 28px 18px;border-radius:22px;
  background:rgba(15,23,42,.66);backdrop-filter:blur(20px);border:1px solid rgba(148,163,184,.22);
  box-shadow:0 30px 70px rgba(2,6,23,.55),inset 0 1px 0 rgba(255,255,255,.06);animation:dtl-up .7s .1s ease both}
.dtl-card-head{text-align:center;margin-bottom:6px}
.dtl-lock{width:52px;height:52px;margin:0 auto 10px;border-radius:16px;display:flex;align-items:center;justify-content:center;
  font-size:1.5rem;background:linear-gradient(135deg,#2563eb,#7c3aed);box-shadow:0 10px 26px rgba(79,70,229,.5)}
.dtl-card-title{font-size:1.4rem;font-weight:800;color:#f8fafc}
.dtl-card-sub{font-size:.85rem;color:#94a3b8;margin-top:2px}
.st-key-dtl_card [data-testid="stForm"]{border:0;padding:0}
.st-key-dtl_card label p{color:#cbd5e1!important;font-size:.82rem!important;font-weight:600!important}
.st-key-dtl_card [data-baseweb="input"],.st-key-dtl_card [data-baseweb="base-input"]{border-radius:12px!important;
  background:rgba(2,6,23,.55)!important;border-color:rgba(148,163,184,.28)!important;transition:box-shadow .2s ease,border-color .2s ease}
.st-key-dtl_card [data-baseweb="input"]:focus-within{border-color:#60a5fa!important;box-shadow:0 0 0 4px rgba(96,165,250,.25)!important}
.st-key-dtl_card input{color:#f8fafc!important;-webkit-text-fill-color:#f8fafc!important;caret-color:#60a5fa;padding:.7rem .85rem!important}
.st-key-dtl_card input::placeholder{color:#64748b!important;-webkit-text-fill-color:#64748b!important}
.st-key-dtl_card [data-baseweb="input"] button svg{fill:#94a3b8!important}
.st-key-dtl_card [data-testid="stFormSubmitButton"] button{position:relative;overflow:hidden;width:100%;border:0;border-radius:12px;
  padding:.72rem 1rem;font-weight:700;letter-spacing:.3px;color:#fff;background:linear-gradient(90deg,#2563eb,#7c3aed);
  box-shadow:0 10px 24px rgba(79,70,229,.45);transition:transform .2s ease,box-shadow .2s ease,filter .2s ease}
.st-key-dtl_card [data-testid="stFormSubmitButton"] button:hover{transform:translateY(-2px);filter:brightness(1.08);
  box-shadow:0 16px 34px rgba(79,70,229,.6)}
.st-key-dtl_card [data-testid="stFormSubmitButton"] button:active{transform:translateY(0)}
.st-key-dtl_card [data-testid="stFormSubmitButton"] button::after{content:"";position:absolute;top:0;left:0;width:40%;height:100%;
  background:linear-gradient(100deg,transparent,rgba(255,255,255,.35),transparent);transform:translateX(-120%)}
.st-key-dtl_card [data-testid="stFormSubmitButton"] button:hover::after{animation:dtl-shine .9s ease}
.st-key-dtl_card [data-testid="stCaptionContainer"]{color:#94a3b8;text-align:center}
.st-key-dtl_card [data-testid="stAlert"]{border-radius:12px}
.dtl-or{display:flex;align-items:center;gap:12px;margin:14px 0 2px;color:#64748b;font-size:.78rem}
.dtl-or::before,.dtl-or::after{content:"";flex:1;height:1px;background:rgba(148,163,184,.22)}
.st-key-dtl_card [data-testid="stButton"] button{width:100%;border-radius:12px;padding:.62rem 1rem;font-weight:600;
  background:rgba(148,163,184,.08);border:1px solid rgba(148,163,184,.30);transition:all .2s ease}
.st-key-dtl_card [data-testid="stButton"] button p{color:#e2e8f0!important}
.st-key-dtl_card [data-testid="stButton"] button:hover{border-color:#60a5fa;background:rgba(59,130,246,.16);
  transform:translateY(-1px);box-shadow:0 8px 20px rgba(37,99,235,.25)}
@media (max-width:900px){.dtl-lead,.dtl-demo,.dtl-chips{display:none}.dtl-title{font-size:1.9rem}.dtl-hero{padding-top:1rem}
  .st-key-dtl_card{margin-top:1rem}}
@media (prefers-reduced-motion:reduce){.stApp::before,.stApp::after,.dtl-hero,.st-key-dtl_card,.dtl-turn,.dtl-a i{animation:none!important}
  .dtl-turn:first-child{opacity:1}.dtl-turn:not(:first-child){display:none}}
</style>
"""

_DEMO_TURNS = (
    ("Which provider types have the highest overturn rate?", "Comparing determinations by provider type"),
    ("How many open appeals are past the SLA?", "Counting open cases older than the SLA window"),
    ("Show monthly volume for escalated appeals", "Trending escalations by received month"),
)
_TRUST_CHIPS = ("🔐 Salted scrypt passwords", "🛡️ Evidence-checked answers", "📜 Audit-logged access")


def _initials(name: str) -> str:
    words = [w for w in str(name).replace(".", " ").split() if w]
    if not words:
        return "?"
    letters = words[0][0] + (words[-1][0] if len(words) > 1 else "")
    return html.escape(letters.upper())


def _hue(username: str) -> int:
    """Stable avatar colour per user (no security meaning)."""
    return zlib.crc32(username.encode("utf-8")) % 360


def _avatar(user: AuthUser, *, large: bool = False) -> str:
    return (f"<div class='dt-av{' lg' if large else ''}' style='--h:{_hue(user.username)}'>"
            f"{_initials(user.name)}<span class='dt-dot'></span></div>")


def _hero_html() -> str:
    turns = "".join(
        f"<div class='dtl-turn' style='animation-delay:{i * 4}s'><div class='dtl-q'>{html.escape(q)}</div>"
        f"<div class='dtl-a'>🧠 {html.escape(a)} <i>●</i><i>●</i><i>●</i></div></div>"
        for i, (q, a) in enumerate(_DEMO_TURNS))
    chips = "".join(f"<span class='dtl-chip'>{html.escape(c)}</span>" for c in _TRUST_CHIPS)
    return (
        "<div class='dtl-hero'>"
        "<div class='dtl-brand'><div class='dtl-orb'>🧠</div><div><div class='dtl-name'>DataTalk.AI</div>"
        "<div class='dtl-sub'>Healthcare Appeals Intelligence Platform</div></div></div>"
        "<h1 class='dtl-title'>Ask your appeals data <span>anything.</span></h1>"
        "<p class='dtl-lead'>Conversational analytics on governed Databricks data, with every number "
        "checked against evidence before you see it.</p>"
        f"<div class='dtl-demo'>{turns}</div><div class='dtl-chips'>{chips}</div></div>")


# ── gate ───────────────────────────────────────────────────────────────────────
def require_login() -> AuthUser | None:
    """Gate for the whole app. Returns the signed-in user, ``None`` when login is disabled; otherwise it
    renders the login screen and stops the script."""
    try:
        cfg = load_config()
    except Exception as exc:
        log.error("login configuration invalid: %s", exc)
        _stop_with_error("Login is turned on but its configuration is invalid. Ask the application owner to "
                         "check the LOGIN_* settings (or the [login] section of the app secrets).")
        return None
    if cfg is None:
        return None

    record = st.session_state.get(SESSION_KEY)
    if isinstance(record, dict):
        now = time.time()
        status = A.session_status(record, now, cfg.idle_seconds, cfg.max_session_seconds)
        if record.get("user") not in cfg.users:
            log.info("session ended: user %s no longer configured", record.get("user"))
            end_session("Your access has changed. Please sign in again.")
        elif status == "idle":
            log.info("session ended: idle user=%s", record.get("user"))
            end_session("You were signed out after a period of inactivity.")
        elif status == "expired":
            log.info("session ended: maximum length user=%s", record.get("user"))
            end_session("Your session has reached its time limit. Please sign in again.")
        record["last_seen"] = now
        user = _user_from(record)
        st.markdown(_PROFILE_CSS, unsafe_allow_html=True)
        if st.session_state.pop(WELCOME_KEY, False):
            st.toast(f"Welcome back, {user.name.split()[0]} 👋", icon="✅")
        return user

    _render_login(cfg)
    st.stop()
    return None


def _card_head(icon: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"<div class='dtl-card-head'><div class='dtl-lock'>{icon}</div><div class='dtl-card-title'>{html.escape(title)}</div>"
        f"<div class='dtl-card-sub'>{html.escape(subtitle)}</div></div>", unsafe_allow_html=True)
    notice = st.session_state.pop(NOTICE_KEY, "")
    if notice:
        st.info(notice)


def _set_mode(mode: str) -> None:
    st.session_state[MODE_KEY] = mode
    st.rerun()


def _render_login(cfg: AuthConfig) -> None:
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    mode = st.session_state.get(MODE_KEY, "login")
    if mode == "register" and not cfg.register_enabled:
        mode = "login"
    hero, form = st.columns([1.15, 0.85], gap="large", vertical_alignment="top")
    with hero:
        st.markdown(_hero_html(), unsafe_allow_html=True)
    with form:
        with st.container(key="dtl_card"):
            if mode == "register":
                _render_register_card(cfg)
            else:
                _render_signin_card(cfg)
    ui.footer()


def _render_signin_card(cfg: AuthConfig) -> None:
    _card_head("🔒", "Welcome back", "Sign in to continue to your workspace")
    with st.form("dt_login_form", clear_on_submit=False, border=False):
        username = st.text_input("Username", max_chars=64, autocomplete="username",
                                 placeholder="Enter your username")
        password = st.text_input("Password", type="password", max_chars=A.MAX_PASSWORD_LENGTH,
                                 autocomplete="current-password", placeholder="Enter your password")
        submitted = st.form_submit_button("Sign in  →", type="primary", width="stretch")
    if submitted:
        _attempt(cfg, username, password)
    if cfg.register_enabled:
        st.markdown("<div class='dtl-or'>New here?</div>", unsafe_allow_html=True)
        if st.button("✨ Create an account", key="dtl_go_register", width="stretch"):
            _set_mode("register")
    st.caption("🛡️ Access is limited to authorised users. Activity is logged.")


def _render_register_card(cfg: AuthConfig) -> None:
    _card_head("✨", "Create your account", "You need the access code from your administrator")
    with st.form("dt_register_form", clear_on_submit=False, border=False):
        code = st.text_input("Access code", type="password", max_chars=128, key="dt_reg_code",
                             autocomplete="off", placeholder="Provided by your administrator")
        username = st.text_input("Username", max_chars=64, key="dt_reg_user", autocomplete="username",
                                 placeholder="Letters, digits and . _ @ -")
        display = st.text_input("Display name", max_chars=80, key="dt_reg_name", autocomplete="name",
                                placeholder="e.g. Jane Smith")
        password = st.text_input("Password", type="password", max_chars=A.MAX_PASSWORD_LENGTH, key="dt_reg_pw",
                                 autocomplete="new-password", placeholder=f"At least {A.MIN_PASSWORD_LENGTH} characters")
        confirm = st.text_input("Confirm password", type="password", max_chars=A.MAX_PASSWORD_LENGTH,
                                key="dt_reg_pw2", autocomplete="new-password", placeholder="Repeat the password")
        submitted = st.form_submit_button("Create account  →", type="primary", width="stretch")
    if submitted:
        _register(cfg, code, username, display, password, confirm)
    st.markdown("<div class='dtl-or'>Already have an account?</div>", unsafe_allow_html=True)
    if st.button("← Back to sign in", key="dtl_go_login", width="stretch"):
        _set_mode("login")
    st.caption("🛡️ Your password is stored only as a salted scrypt hash. Activity is logged.")


def _attempt(cfg: AuthConfig, username: str, password: str) -> None:
    key = A.normalise_username(username)
    if not key or not password:
        st.error("Enter your username and password.")
        return
    throttle = _throttle(cfg.max_attempts, cfg.lockout_seconds)
    now = time.time()
    wait = throttle.locked_for(key, now)
    if wait:
        log.warning("login blocked (locked) user=%s", key[:64])
        st.error(f"Too many failed attempts. Try again in {math.ceil(wait / 60)} minute(s).")
        return

    record = cfg.users.get(key)
    with st.spinner("Verifying credentials…"):
        verified = A.verify_password(password, record.password_hash if record else None)
    if verified and record:
        throttle.reset(key)
        stamp = time.time()
        st.session_state[SESSION_KEY] = {"user": record.username, "name": record.name, "role": record.role,
                                         "login_at": stamp, "last_seen": stamp}
        st.session_state[WELCOME_KEY] = True
        log.info("login ok user=%s", record.username)
        st.rerun()
        return

    locked = throttle.fail(key, time.time())
    log.warning("login failed user=%s%s", key[:64], " (now locked)" if locked else "")
    time.sleep(FAILURE_DELAY_SECONDS)
    if locked:
        st.error(f"Too many failed attempts. Try again in {math.ceil(locked / 60)} minute(s).")
    else:
        st.error("Incorrect username or password.")


# ── registration ───────────────────────────────────────────────────────────────
def _env_path() -> Path:
    from core.settings import PROJECT_ROOT   # same file pydantic-settings reads (PROJECT_ROOT / ".env")
    return PROJECT_ROOT / ".env"


def _registration_problems(cfg: AuthConfig, key: str, password: str, confirm: str) -> list[str]:
    """Why a new account is rejected (empty list = fine). ``key`` is the normalised username."""
    problems = []
    if not A.USERNAME_PATTERN.fullmatch(key):
        problems.append("Username may contain only letters, digits and . _ @ - (max 64 characters).")
    elif key in cfg.users:
        problems.append("That username is not available.")
    if password != confirm:
        problems.append("The passwords do not match.")
    problems += [f"Password: {p}." for p in A.password_problems(password)]
    return problems


def _register(cfg: AuthConfig, code: str, username: str, display: str, password: str, confirm: str) -> None:
    throttle = _register_throttle(cfg.max_attempts, cfg.lockout_seconds)
    wait = throttle.locked_for("code", time.time())
    if wait:
        log.warning("registration blocked (locked)")
        st.error(f"Too many failed attempts. Try again in {math.ceil(wait / 60)} minute(s).")
        return
    if not hmac.compare_digest(str(code).strip().encode("utf-8"), cfg.register_code.encode("utf-8")):
        locked = throttle.fail("code", time.time())
        log.warning("registration rejected: wrong access code%s", " (now locked)" if locked else "")
        time.sleep(FAILURE_DELAY_SECONDS)
        if locked:
            st.error(f"Too many failed attempts. Try again in {math.ceil(locked / 60)} minute(s).")
        else:
            st.error("Invalid access code.")
        return

    key = A.normalise_username(username)
    problems = _registration_problems(cfg, key, password, confirm)
    if problems:
        st.error("\n".join(f"- {p}" for p in problems))
        return

    with st.spinner("Creating your account…"):
        entry = {"name": A.clean_display_name(display) or key, "password_hash": A.hash_password(password)}
        try:
            A.save_user_to_env(_env_path(), key, entry)
        except (OSError, ValueError):
            log.exception("could not save new user %s to .env", key)
            st.error("Your account could not be saved. Please contact the administrator.")
            return
    _registered_users()[key] = entry   # usable immediately; .env keeps it across restarts
    throttle.reset("code")
    log.info("register ok user=%s", key)
    A.audit("register", new_user=key)
    st.session_state[NOTICE_KEY] = f"Account created for **{key}**. You can sign in now."
    _set_mode("login")


# ── account UI (sidebar / header) ──────────────────────────────────────────────
def _session_minutes() -> int:
    record = st.session_state.get(SESSION_KEY)
    try:
        return max(0, int((time.time() - float(record["login_at"])) // 60))
    except (KeyError, TypeError, ValueError):
        return 0


def render_account_box() -> None:
    """Profile card for the signed-in user and a Sign out button. Renders nothing when login is disabled."""
    user = current_user()
    if user is None:
        return
    role = f"<span class='dt-role' style='margin-left:0'>{html.escape(user.role)}</span>" if user.role else ""
    minutes = _session_minutes()
    active = "Signed in just now" if minutes < 1 else f"Signed in for {minutes} min"
    st.markdown(
        f"<div class='dt-acct'>{_avatar(user, large=True)}<div><div class='dt-aname'>{html.escape(user.name)}</div>"
        f"{role}<div class='dt-ameta'>🟢 {active}</div></div></div>",
        unsafe_allow_html=True)
    if st.button("🚪 Sign out", key="dt_sign_out", width="stretch"):
        sign_out()


def user_pill() -> str:
    """Header chip for the signed-in user: avatar with online dot, name and role.
    Returns an empty string when login is disabled."""
    user = current_user()
    if user is None:
        return ""
    role = f"<span class='dt-role'>{html.escape(user.role)}</span>" if user.role else ""
    return (f"<div class='dt-user' title='Signed in as {html.escape(user.name)}'>{_avatar(user)}"
            f"<div class='dt-utxt'><span class='dt-uhello'>Welcome back</span>"
            f"<span class='dt-uname'>{html.escape(user.name)}{role}</span></div></div>")


def render_user_banner() -> None:
    """Welcome chip on its own line (call it just before ``ui.header``, so it sits above the Spark logo).
    Renders nothing when login is disabled."""
    chip = user_pill()
    if chip:
        st.markdown(f"<div class='dt-userbar'>{chip}</div>", unsafe_allow_html=True)


__all__ = ["require_login", "render_account_box", "render_user_banner", "user_pill", "current_user", "sign_out", "load_config",
           "AuthConfig", "AuthUser"]