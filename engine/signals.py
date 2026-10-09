"""One vocabulary for signals, with the evidence each one needs before it counts.

Announced: the company made it public. It can go in the email.
Watched: you saw it in your tools. It ranks the account; the email never mentions it.
"""
import re
from typing import Optional

EVIDENCE = {
    "funding_round": "What the announcement says the money is for. Cash is not a need.",
    "acquisition": "Which side you sell to, and what consolidates.",
    "contract_win": "The scope of work it creates downstream.",
    "new_leader": "What this person is now responsible for, which is rarely the job title.",
    "job_posting": "Which capability is being added.",
    "job_repost": "Two separately dated postings of the same role. Syndication across boards is not a repost.",
    "hiring_campaign": "Several roles in one function inside a short window.",
    "job_change": "The person moved, and the new employer fits the ICP.",
    "product_launch": "The initiative, dated, from the company itself.",
    "market_expansion": "The new market confirmed, plus the gap a buyer there hits.",
    "partnership": "What distribution or delivery work it implies.",
    "pricing_change": "The previous state and the current state. A pricing page is not a change.",
    "tech_migration": "Evidence of the switch. A current tool fingerprint is not evidence.",
    "website_change": "Before and after, dated.",
    "tender": "The published notice, and the buying body that issued it.",
    "agency_request": "The actual post asking.",
    "customer_complaint": "A specific named problem, public.",
    "competitor_change": "A retirement or price move, plus proof this account uses it.",
    "compliance_milestone": "A deadline that creates work.",
    "layoffs": "A hold signal. A smaller team means a cancelled budget.",
    "pricing_page_visit": "From your analytics. Ranks the account; the message never mentions it.",
    "repeat_visits": "From your analytics: the same account back more than once.",
    "website_visit": "Someone from the company visited your website.",
    "closed_lost": "From your CRM: an earlier deal that did not close.",
    "existing_relationship": "From your CRM: someone there already knows you.",
    "icp_match": "The company matches the ICP. Nothing happened.",
}
TYPES = tuple(EVIDENCE)
HOLD = ("layoffs",)
STATIC = ("icp_match",)
# Signals from the same source family count once toward a stack (check 3: two signals, not one signal twice).
FAMILY = {"job_posting": "jobs", "job_repost": "jobs", "hiring_campaign": "jobs",
          "pricing_change": "site", "website_change": "site"}
WATCHED = ("pricing_page_visit", "repeat_visits", "website_visit", "closed_lost", "existing_relationship")
ANNOUNCED = tuple(t for t in TYPES if t not in WATCHED and t not in STATIC)
# What the three v1 sources can produce. Keeps Haiku from reaching for signals it cannot see.
FROM_SOURCE = {
    "boards": ("job_posting", "job_repost", "hiring_campaign"),
    "pages": ("pricing_change", "website_change", "product_launch", "market_expansion", "new_leader", "partnership"),
    "news": ("funding_round", "acquisition", "new_leader", "product_launch", "market_expansion",
             "partnership", "contract_win", "layoffs", "customer_complaint", "tech_migration"),
}

_ALIASES = [
    (r"layoff|lay-off|redundanc|downsiz", "layoffs"),
    (r"re-?post|re-?publish|still open|hard to fill", "job_repost"),
    (r"hiring campaign|several roles|multiple roles|hiring spree", "hiring_campaign"),
    (r"new (leader|vp|head|director|cro|cmo|ceo|cfo)|appointed|joins as", "new_leader"),
    (r"hiring|job post|job offer|open role|vacancy|posting", "job_posting"),
    (r"acqui|merger|m&a", "acquisition"),
    (r"fund|raise|raised|series [a-e]\b|seed round", "funding_round"),
    (r"launch", "product_launch"),
    (r"expan|new market|new office|new country", "market_expansion"),
    (r"partner", "partnership"),
    (r"pricing (change|update)|price change|new pricing", "pricing_change"),
    (r"website (change|redesign|relaunch)|rebrand", "website_change"),
]


def canonical(text: Optional[str]) -> Optional[str]:
    t = (text or "").strip().lower()
    if not t:
        return None
    key = re.sub(r"[\s\-]+", "_", t)
    if key in EVIDENCE:
        return key
    for name in EVIDENCE:
        if key.startswith(name + "_"):
            return name
    for pattern, name in _ALIASES:
        if re.search(pattern, t):
            return name
    return None


def is_announced(name: str) -> bool:
    return name in ANNOUNCED
