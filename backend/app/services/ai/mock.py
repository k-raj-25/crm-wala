"""Deterministic provider that answers from real CRM data using the same tools an LLM would call."""
from __future__ import annotations

import re

from flask import g

from app.services.ai import insights
from app.services.ai.providers import AIResult, ToolRunner, _collect_sources


def _money(v: float, cur: str = "INR") -> str:
    sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(cur, cur + " ")
    if cur == "INR":
        if v >= 1e7:
            return f"{sym}{v / 1e7:.2f} Cr"
        if v >= 1e5:
            return f"{sym}{v / 1e5:.2f} L"
    return f"{sym}{v:,.0f}"


def _days(q: str, default: int) -> int:
    m = re.search(r"(\d+)\s*(?:\+)?\s*days?", q)
    return int(m.group(1)) if m else default


class MockProvider:
    name = "mock"

    # ---------------- content generation ----------------
    def complete(self, kind, system, prompt, context):
        if kind == "email_draft":
            return AIResult(self._email(context))
        if kind == "summary":
            return AIResult(self._summary(context))
        if kind == "meeting_summary":
            return AIResult(self._meeting(context))
        if kind == "narrate":
            return AIResult(context.get("fallback", ""))
        return AIResult("")

    def _email(self, c: dict) -> str:
        name = (c.get("name") or "there").split(" ")[0]
        goal, sender = c.get("goal") or "follow_up", c.get("sender") or "me"
        company = c.get("company")
        recent = c.get("recent_activity") or []
        last = recent[0]["title"] if recent else None
        openers = {
            "follow_up": f"I wanted to follow up on our recent conversation{f' about {company}' if company else ''}{f' ({last.lower()})' if last else ''}.",
            "intro": f"I'm {sender} — I came across {company or 'your work'} and thought there could be a good fit with what we do.",
            "proposal": "Thank you for your time so far. I've put together next steps for working together and wanted to make them easy to review.",
            "meeting": "I'd love to set up a short call to walk through how we can help.",
            "check_in": "Just checking in to see how things are going on your side.",
            "win_back": "It's been a little while since we last spoke, and I wanted to reconnect.",
        }
        asks = {
            "follow_up": "Would you be open to a quick 15-minute call this week to talk through next steps?",
            "intro": "Would a 15-minute intro call next week be worthwhile?",
            "proposal": "Could you let me know a good time to discuss, or if there's anything you'd like me to adjust?",
            "meeting": "Do you have 20 minutes on Thursday or Friday? Happy to work around your schedule.",
            "check_in": "If there's anything we can help with, just reply here — happy to jump on a call.",
            "win_back": "A lot has improved since we last spoke. Would you be open to a short catch-up?",
        }
        subjects = {"follow_up": f"Following up{f' — {company}' if company else ''}", "intro": f"Quick intro{f' for {company}' if company else ''}", "proposal": "Next steps",
                    "meeting": "Can we find 20 minutes?", "check_in": "Checking in", "win_back": "Let's reconnect"}
        body = f"Hi {name},\n\n{openers.get(goal, openers['follow_up'])}\n\n{asks.get(goal, asks['follow_up'])}\n\nBest regards,\n{sender}"
        return f"SUBJECT: {subjects.get(goal, 'Following up')}\n\n{body}"

    def _summary(self, c: dict) -> str:
        e = c.get("entity")
        lines = []
        if e == "deal":
            lines.append(f"**{c['name']}** is an open {_money(c['value'], c['currency'])} deal in **{c['stage']}** ({c['probability']}% likely)" + (f" with {c['company']}" if c.get("company") else "") + ".")
            if c.get("expected_close"):
                lines.append(f"Expected close: {c['expected_close']}.")
            if c.get("days_since_activity") is not None:
                lines.append(f"Last activity {c['days_since_activity']} day(s) ago." + (" ⚠️ This deal is going cold." if c["days_since_activity"] > 7 else ""))
        elif e == "lead":
            lines.append(f"**{c['name']}**{' at ' + c['company'] if c.get('company') else ''} is a *{c['status']}* lead with a score of **{c['score']}/100**" + (f" from {c['source'].replace('_', ' ')}" if c.get("source") else "") + ".")
            if c.get("score_reasons"):
                lines.append("Why this score: " + ", ".join(f"{r['label']} ({r['points']:+d})" for r in c["score_reasons"][:4]) + ".")
        elif e == "contact":
            lines.append(f"**{c['name']}**" + (f", {c['job_title']}" if c.get("job_title") else "") + (f" at {c['company']}" if c.get("company") else "") + ".")
            if c.get("deals"):
                lines.append("Deals: " + "; ".join(f"{d['name']} ({d['status']}, {_money(d['value'])})" for d in c["deals"][:4]) + ".")
        else:
            lines.append(f"**{c['name']}**" + (f" — {c['industry']}" if c.get("industry") else "") + ".")
            if c.get("deals"):
                won = sum(d["value"] for d in c["deals"] if d["status"] == "won")
                lines.append(f"{len(c['deals'])} deal(s); {_money(won)} won so far.")
        act = c.get("recent_activity") or []
        if act:
            lines.append("**Recent activity:** " + " → ".join(a["title"] for a in act[:4]))
        if c.get("notes"):
            lines.append("**Latest note:** " + c["notes"][0][:200])
        lines.append("**Suggested next step:** " + ("Schedule a follow-up within 2 days." if not act or (c.get("days_since_activity") or 0) > 7 else "Keep momentum — send a short recap and confirm the next meeting."))
        return "\n\n".join(lines)

    def _meeting(self, c: dict) -> str:
        notes = (c.get("notes") or "").strip()
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", notes) if s.strip()]
        actions = [s for s in sentences if re.search(r"\b(will|todo|to do|action|follow up|send|schedule|need to|next step)\b", s, re.I)]
        out = f"**Summary:** {' '.join(sentences[:3]) or 'No notes were captured for this meeting.'}"
        if actions:
            out += "\n\n**Action items:**\n" + "\n".join(f"- {a}" for a in actions[:6])
        return out

    # ---------------- assistant ----------------
    def chat(self, system: str, history: list[dict], tools: list[dict], run_tool: ToolRunner, max_steps: int = 5) -> AIResult:
        q = str(history[-1]["content"]).lower()
        sources: list[dict] = []

        def call(name, **kw):
            out = run_tool(name, kw)
            sources.extend(_collect_sources(out))
            return out

        def deals_md(rows, extra=lambda d: ""):
            return "\n".join(f"- **[{d['name']}]({d['url']})** — {_money(d['value'], d['currency'])} · {d['stage']} · {d['probability']}%{extra(d)}" for d in rows)

        text = ""
        if re.search(r"focus|today|what should i|priorit", q) and "lead" not in q:
            acts = insights.next_best_actions(6)
            from app.services import reporting

            f = reporting.todays_focus(g.workspace.id, g.user.id)
            head = f"**Today's focus:** {f['follow_ups']['count']} follow-ups · {f['meetings']['count']} meetings · {f['deals_attention']['count']} deals need attention · {f['overdue_tasks']['count']} overdue tasks."
            text = head + ("\n\n" + "\n".join(f"{i + 1}. **{a['title']}** — {a['reason']}" for i, a in enumerate(acts)) if acts else "\n\nNothing urgent. A great moment to prospect for new leads!")
            sources += [{"label": a["title"], "url": a["url"], "type": a["kind"]} for a in acts[:4]]
        elif re.search(r"(haven'?t|not|never|no).{0,20}(contact|touch|reach)|stale|going cold", q) and "deal" not in q:
            out = call("list_leads", stale_days=_days(q, 7), limit=10)
            ls = out.get("leads", [])
            text = (f"**{out.get('total', 0)} open leads** haven't been contacted in {_days(q, 7)}+ days. Here are the highest-scoring ones:\n\n" + "\n".join(
                f"- **[{l['name']}]({l['url']})**{' · ' + l['company'] if l['company'] else ''} — score {l['score']}, status {l['status']}" for l in ls)) if ls else f"Great news — every open lead has been contacted in the last {_days(q, 7)} days. 🎉"
        elif re.search(r"likely to close|close this month|closing|forecast", q):
            out = call("list_deals", status="open", closing="this_month", sort="probability", limit=8)
            ds = out.get("deals", [])
            text = (f"**{len(ds)} deals** are expected to close this month, worth **{_money(out['total_value'])}**. Ranked by likelihood × value:\n\n" + deals_md(ds)) if ds else "No open deals have an expected close date this month. Add close dates to your deals to get a forecast."
        elif re.search(r"highest|biggest|largest|top .*(deal|opportunit)|most valuable|high-value", q):
            out = call("list_deals", status="open", sort="value", limit=6)
            ds = out.get("deals", [])
            text = ("**Your highest-value open opportunities:**\n\n" + deals_md(ds)) if ds else "You have no open deals yet. Create one from a qualified lead."
        elif re.search(r"salesperson|sales rep|rep\b|team|who.*(best|highest|top)|conversion rate", q):
            out = call("team_performance", days=_days(q, 90))
            reps = out.get("reps", [])
            if reps:
                best = max(reps, key=lambda r: (r["win_rate"], r["revenue"]))
                text = f"Over the last {out['days']} days, **{best['rep']}** has the highest win rate at **{best['win_rate']}%** ({best['deals_won']} won, {_money(best['revenue'])} revenue).\n\n| Rep | Won | Lost | Win rate | Revenue |\n|---|---|---|---|---|\n" + "\n".join(
                    f"| {r['rep']} | {r['deals_won']} | {r['deals_lost']} | {r['win_rate']}% | {_money(r['revenue'])} |" for r in sorted(reps, key=lambda r: -r["win_rate"]))
            else:
                text = "I don't have enough closed deals yet to compare your team."
        elif re.search(r"declin|drop|down|why.*pipeline|pipeline.*(why|decreas)|slow", q):
            d = insights.pipeline_diagnosis(_days(q, 30))
            text = f"Your pipeline looks **{d['direction']}** compared with the previous {d['days']} days.\n\n" + "\n".join(f"- **{f['title']}** ({f['severity']}) — {f['detail']}" for f in d["findings"])
        elif re.search(r"summar", q):
            name = re.sub(r".*summari[sz]e\s+(?:this\s+|the\s+|my\s+)?(?:customer|deal|lead|contact|company)?\s*", "", q).strip(" ?.")
            hit = call("search_crm", query=name) if name and name not in ("this", "it") else {}
            first = next(((k, v[0]) for k, v in hit.items() if v), None)
            if first:
                ent = {"deals": "deal", "leads": "lead", "contacts": "contact", "companies": "company"}[first[0]]
                ctx = run_tool("record_context", {"entity": ent, "ident": first[1]["id"]})
                text = self._summary(ctx)
            else:
                text = "Tell me which customer, deal or lead to summarize — for example “Summarize Acme Corp”."
        elif re.search(r"email|write|draft", q):
            name = re.sub(r".*(?:for|to)\s+", "", q).strip(" ?.")
            hit = call("search_crm", query=name) if name else {}
            first = next(((k, v[0]) for k, v in hit.items() if v and k in ("leads", "contacts")), None)
            if first:
                ent = {"leads": "lead", "contacts": "contact"}[first[0]]
                ctx = run_tool("record_context", {"entity": ent, "ident": first[1]["id"]})
                text = "Here's a draft:\n\n```\n" + self._email({**ctx, "sender": g.user.name, "goal": "follow_up"}).replace("SUBJECT: ", "Subject: ") + "\n```"
            else:
                text = "Who is the email for? Try “Write a follow-up email for John Smith”."
        elif re.search(r"task|overdue|todo|to-do", q):
            view = "overdue" if "overdue" in q else "today"
            ts = call("list_tasks", view=view).get("tasks", [])
            text = (f"You have **{len(ts)} {view} task(s):**\n\n" + "\n".join(f"- {t['title']}" + (f" — due {t['due_at'][:10]}" if t["due_at"] else "") for t in ts)) if ts else f"You have no {view} tasks. ✅"
        elif re.search(r"pipeline|funnel|stage", q):
            out = call("pipeline_summary")
            text = f"Your open pipeline is **{_money(out['open_value'])}** across {out['open_deals']} deals ({_money(out['weighted_value'])} weighted).\n\n" + "\n".join(f"- {s['stage']}: {s['deals']} deals · {_money(s['value'])}" for s in out["stages"])
        elif re.search(r"revenue|sales|won|closed", q):
            out = call("revenue_trend", days=_days(q, 30))
            text = f"In the last {out['days']} days you closed **{out['deals_won']['value']} deals** for **{_money(out['revenue']['value'])}** (conversion {out['conversion_rate']['value']}%). You added {out['new_leads']['value']} new leads."
        else:
            hit = call("search_crm", query=q.strip(" ?."))
            if hit:
                text = "Here's what I found:\n\n" + "\n".join(f"**{k.title()}**\n" + "\n".join(f"- [{r['name']}]({r['url']})" for r in v) for k, v in hit.items())
            else:
                text = ("I can help with your CRM data. Try asking:\n\n- *What should I focus on today?*\n- *Which deals are most likely to close this month?*\n- *Which leads haven't been contacted in 7 days?*\n"
                        "- *Show me my highest-value opportunities.*\n- *Which salesperson has the highest conversion rate?*\n- *Why is my pipeline declining?*\n- *Summarize Acme Corp*")
        return AIResult(text, sources=sources[:8], model="rules-v1")
