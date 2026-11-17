# """Lightweight startup indicator."""
# from html import escape

# import streamlit as st


# _STYLE = """
# <style>
# .dtl-mini {
#     display: flex;
#     align-items: center;
#     gap: 12px;
#     padding: 16px 0;
#     color: inherit;
#     font-family: inherit;
# }

# .dtl-mini-spinner {
#     width: 26px;
#     height: 26px;
#     flex: 0 0 26px;
#     border: 3px solid rgba(127, 127, 127, 0.25);
#     border-top-color: var(--dt-accent, #60a5fa);
#     border-radius: 50%;
#     animation: dtl-mini-spin 0.85s linear infinite;
# }

# .dtl-mini-title {
#     font-size: 0.95rem;
#     font-weight: 650;
#     line-height: 1.5;
# }

# .dtl-mini-message {
#     font-size: 0.8rem;
#     opacity: 0.78;
#     line-height: 1.5;
# }

# @keyframes dtl-mini-spin {
#     to { transform: rotate(360deg); }
# }

# @media (prefers-reduced-motion: reduce) {
#     .dtl-mini-spinner {
#         animation: none;
#     }
# }
# </style>
# """


# class StartupLoader:
#     def __init__(self):
#         self.slot = st.empty()

#     def show(self, phase="loading", rows=None):
#         messages = {
#             "loading": "Loading appeals data…",
#             "loaded": "Initializing analytics…",
#             "preparing": "Preparing your dashboard…",
#         }

#         message = messages.get(phase, "Loading…")

#         self.slot.markdown(
#             _STYLE
#             + '<div class="dtl-mini" role="status" aria-live="polite">'
#             + '<span class="dtl-mini-spinner" aria-hidden="true"></span>'
#             + '<div>'
#             + '<div class="dtl-mini-title">DataTalk.AI</div>'
#             + f'<div class="dtl-mini-message">{escape(message)}</div>'
#             + '</div></div>',
#             unsafe_allow_html=True,
#         )

#     def clear(self):
#         self.slot.empty()



"""Startup loader for DataTalk.AI, styled to match the login screen."""
from __future__ import annotations

from html import escape

import streamlit as st

_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

.dtl-overlay, .dtl-overlay * { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; box-sizing: border-box; }

.dtl-overlay {
    position: fixed; inset: 0; z-index: 999990; display: grid; place-items: center; padding: 1rem; overflow: hidden;
    color: #e2e8f0;
    background:
        radial-gradient(900px 600px at 12% 8%, rgba(99,102,241,.35), transparent 60%),
        radial-gradient(800px 600px at 92% 90%, rgba(139,92,246,.30), transparent 60%),
        radial-gradient(600px 400px at 80% 10%, rgba(34,211,238,.14), transparent 60%),
        #060913;
    background-size: 140% 140%, 140% 140%, 140% 140%, auto;
    animation: dtlAurora 18s ease-in-out infinite alternate, dtlIn .35s ease both;
}
.dtl-overlay::before {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background-image: radial-gradient(rgba(148,163,184,.14) 1px, transparent 1px);
    background-size: 28px 28px;
    -webkit-mask-image: radial-gradient(ellipse at center, #000 30%, transparent 78%);
            mask-image: radial-gradient(ellipse at center, #000 30%, transparent 78%);
}
@keyframes dtlAurora { 0% { background-position: 0% 0%, 100% 100%, 100% 0%, 0 0; }
                       100% { background-position: 30% 20%, 70% 80%, 70% 30%, 0 0; } }
@keyframes dtlIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes dtlRise { from { opacity: 0; transform: translateY(20px) scale(.985); } to { opacity: 1; transform: none; } }

.dtl-card {
    position: relative; width: min(440px, 100%); padding: 2.4rem 2.2rem 2rem; border-radius: 24px;
    background: rgba(11,17,32,.78); border: 1px solid rgba(148,163,184,.16);
    -webkit-backdrop-filter: blur(18px); backdrop-filter: blur(18px);
    box-shadow: 0 40px 100px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.02) inset;
    animation: dtlRise .6s cubic-bezier(.2,.8,.2,1) both;
}
.dtl-card::before { /* gradient edge glow */
    content: ""; position: absolute; inset: -1px; border-radius: 25px; padding: 1px; pointer-events: none;
    background: linear-gradient(140deg, rgba(99,102,241,.7), transparent 40%, transparent 60%, rgba(34,211,238,.5));
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor; mask-composite: exclude; opacity: .55;
}

/* logo with orbiting ring */
.dtl-logo-wrap { position: relative; width: 84px; height: 84px; margin: 0 auto 1.3rem; display: grid; place-items: center; }
.dtl-ring { position: absolute; inset: 0; border-radius: 50%; border: 2px solid rgba(129,140,248,.18);
    border-top-color: #818cf8; border-right-color: #22d3ee; animation: dtlSpin 1.4s linear infinite; }
.dtl-ring.r2 { inset: 8px; border-width: 2px; border-top-color: transparent; border-bottom-color: #a78bfa;
    animation-duration: 2.2s; animation-direction: reverse; }
.dtl-badge { width: 52px; height: 52px; border-radius: 16px; display: grid; place-items: center;
    background: linear-gradient(145deg, #4f46e5, #7c3aed); box-shadow: 0 10px 30px rgba(99,102,241,.5);
    animation: dtlBreathe 2.4s ease-in-out infinite; }
@keyframes dtlSpin { to { transform: rotate(360deg); } }
@keyframes dtlBreathe { 0%,100% { transform: scale(1); } 50% { transform: scale(1.07); } }

.dtl-brand { text-align: center; font-size: 1.45rem; font-weight: 800; letter-spacing: -.02em; color: #f8fafc; }
.dtl-brand b { color: #67e8f9; font-weight: 800; }
.dtl-message { margin-top: .35rem; text-align: center; font-size: .92rem; color: #94a3b8; min-height: 1.4em; }
.dtl-dots { display: inline-flex; gap: 3px; margin-left: 4px; vertical-align: middle; }
.dtl-dots i { width: 4px; height: 4px; border-radius: 50%; background: #a5b4fc; animation: dtlDot 1.2s infinite; }
.dtl-dots i:nth-child(2) { animation-delay: .15s; } .dtl-dots i:nth-child(3) { animation-delay: .3s; }
@keyframes dtlDot { 0%,60%,100% { opacity: .3; transform: none; } 30% { opacity: 1; transform: translateY(-3px); } }

/* progress bar */
.dtl-bar { margin: 1.5rem 0 .4rem; height: 6px; border-radius: 6px; background: rgba(148,163,184,.14); overflow: hidden; position: relative; }
.dtl-bar > b { display: block; height: 100%; border-radius: 6px; position: relative; overflow: hidden;
    background: linear-gradient(90deg, #4f46e5, #7c3aed, #22d3ee); transition: width .6s cubic-bezier(.2,.8,.2,1); }
.dtl-bar > b::after { content: ""; position: absolute; top: 0; bottom: 0; width: 40%; left: -40%;
    background: linear-gradient(100deg, transparent, rgba(255,255,255,.5), transparent); animation: dtlShine 1.4s ease-in-out infinite; }
@keyframes dtlShine { to { left: 110%; } }
.dtl-meta { display: flex; justify-content: space-between; font-size: .74rem; color: #64748b; font-variant-numeric: tabular-nums; }

/* steps */
.dtl-steps { list-style: none; margin: 1.3rem 0 0; padding: 0; display: grid; gap: .45rem; }
.dtl-step { display: flex; align-items: center; gap: .7rem; padding: .55rem .7rem; border-radius: 12px; font-size: .86rem;
    color: #64748b; border: 1px solid transparent; transition: background .3s ease, color .3s ease, border-color .3s ease; }
.dtl-step .ic { width: 24px; height: 24px; border-radius: 50%; flex: 0 0 24px; display: grid; place-items: center;
    font-size: .72rem; font-weight: 700; background: rgba(148,163,184,.12); color: #64748b; }
.dtl-step.done { color: #cbd5e1; }
.dtl-step.done .ic { background: rgba(52,211,153,.16); color: #34d399; }
.dtl-step.active { color: #f8fafc; background: rgba(99,102,241,.12); border-color: rgba(99,102,241,.32); }
.dtl-step.active .ic { background: transparent; border: 2px solid rgba(129,140,248,.3); border-top-color: #818cf8;
    animation: dtlSpin .8s linear infinite; }
.dtl-step .tag { margin-left: auto; font-size: .72rem; color: #94a3b8; font-variant-numeric: tabular-nums; }

.dtl-foot { margin-top: 1.4rem; text-align: center; font-size: .74rem; color: #64748b; }

@media (max-width: 480px) { .dtl-card { padding: 1.8rem 1.3rem 1.5rem; border-radius: 20px; } }
@media (prefers-reduced-motion: reduce) {
    .dtl-overlay, .dtl-overlay *, .dtl-overlay *::before, .dtl-overlay *::after {
        animation-duration: .001ms !important; animation-iteration-count: 1 !important; transition-duration: .001ms !important; }
}
</style>
"""

_LOGO_SVG = (
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/>'
    '<path d="M8.5 13.5v-2M12 13.5v-4M15.5 13.5v-3"/></svg>'
)

_PHASES = ("loading", "loaded", "preparing")
_STEPS = ("Loading appeals data", "Initializing analytics", "Preparing your dashboard")
_MESSAGES = {
    "loading": "Loading appeals data",
    "loaded": "Initializing analytics",
    "preparing": "Preparing your dashboard",
}
_PROGRESS = {"loading": 25, "loaded": 62, "preparing": 90}


def _format_rows(rows) -> str:
    try:
        return f"{int(rows):,} records"
    except (TypeError, ValueError):
        return ""


class StartupLoader:
    def __init__(self):
        self.slot = st.empty()

    def show(self, phase="loading", rows=None):
        message = _MESSAGES.get(phase, "Loading")
        pct = _PROGRESS.get(phase, 15)
        current = _PHASES.index(phase) if phase in _PHASES else 0
        rows_text = _format_rows(rows) if rows is not None else ""

        steps = []
        for i, label in enumerate(_STEPS):
            if i < current:
                cls, icon = "done", "✓"
            elif i == current:
                cls, icon = "active", ""
            else:
                cls, icon = "", str(i + 1)
            tag = escape(rows_text) if (i == 0 and i < current and rows_text) else ""
            steps.append(
                f'<li class="dtl-step {cls}"><span class="ic">{icon}</span>'
                f'<span>{escape(label)}</span><span class="tag">{tag}</span></li>'
            )

        html = (
            '<div class="dtl-overlay" role="status" aria-live="polite">'
            '<div class="dtl-card">'
            '<div class="dtl-logo-wrap"><span class="dtl-ring"></span><span class="dtl-ring r2"></span>'
            f'<div class="dtl-badge">{_LOGO_SVG}</div></div>'
            '<div class="dtl-brand">DataTalk<b>.AI</b></div>'
            f'<div class="dtl-message">{escape(message)}'
            '<span class="dtl-dots" aria-hidden="true"><i></i><i></i><i></i></span></div>'
            f'<div class="dtl-bar"><b style="width:{pct}%"></b></div>'
            f'<div class="dtl-meta"><span>Step {current + 1} of {len(_STEPS)}</span><span>{pct}%</span></div>'
            f'<ul class="dtl-steps">{"".join(steps)}</ul>'
            '<div class="dtl-foot">Secure workspace · Preparing your session</div>'
            '</div></div>'
        )
        self.slot.markdown(_STYLE + html, unsafe_allow_html=True)

    def clear(self):
        self.slot.empty()