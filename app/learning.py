"""Learning-loop aggregation — findings, habits, proposals. No silent overwrites.

Rules (from the private-app design, enforced here):
- 1 game (one distinct review with a feedback kind) = a FINDING.
  Recorded only. It changes nothing.
- 2-3 distinct reviews with the same (tip_kind, feedback kind) =
  a HABIT candidate. Still changes nothing by itself.
- A template change is PROPOSED only after multiple games AND
  multiple users: at least 3 distinct reviews AND at least 2 distinct
  users with the same (tip_kind, feedback kind). Even then the
  proposal sits in pending_review and is never applied silently.
- Applying a proposal appends a new version to learning_templates.json
  with the previous text preserved and provenance (reviews, users,
  date). It never overwrites in place, and it is a deliberate,
  human-reviewed action — there is deliberately NO HTTP endpoint
  that auto-applies templates.

Feedback rows are dicts with: review_id, user_id, kind
('drill-helped' | 'report-was-wrong'), tip_kind (optional),
drill (optional), note (optional). Rows without a tip_kind are
counted only as generic findings, never as a tip-template proposal.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

FINDING_MIN_REVIEWS = 1
HABIT_MIN_REVIEWS = 2
PROPOSAL_MIN_REVIEWS = 3
PROPOSAL_MIN_USERS = 2


def aggregate_feedback(rows):
    """Return findings, habits, and proposals from feedback rows.

    No row is ever mutated, and no template is changed by this function.
    Counts are by distinct review_id and distinct user_id, so one user
    spamming feedback on one review cannot manufacture a habit.
    """
    by_key = defaultdict(lambda: {"reviews": set(), "users": set(), "count": 0})
    generic = defaultdict(lambda: {"reviews": set(), "users": set(), "count": 0})
    for r in rows or []:
        kind = r.get("kind")
        if kind not in ("drill-helped", "report-was-wrong"):
            continue
        key = (r.get("tip_kind") or "", kind)
        bucket = by_key[key] if r.get("tip_kind") else generic[kind]
        bucket["reviews"].add(r.get("review_id"))
        bucket["users"].add(r.get("user_id"))
        bucket["count"] += 1
    findings, habits, proposals = [], [], []
    for (tip_kind, kind), b in sorted(by_key.items()):
        n_rev, n_users = len(b["reviews"]), len(b["users"])
        entry = {"tip_kind": tip_kind, "feedback_kind": kind,
                 "distinct_reviews": n_rev, "distinct_users": n_users,
                 "feedback_count": b["count"]}
        if n_rev >= FINDING_MIN_REVIEWS:
            findings.append(entry)
        if n_rev >= HABIT_MIN_REVIEWS:
            habits.append(entry)
        if n_rev >= PROPOSAL_MIN_REVIEWS and n_users >= PROPOSAL_MIN_USERS:
            proposals.append({**entry, "status": "pending_review",
                              "action": ("Review this tip template before any "
                                         "change; do not apply silently.")})
    for kind, b in sorted(generic.items()):
        findings.append({"tip_kind": None, "feedback_kind": kind,
                         "distinct_reviews": len(b["reviews"]),
                         "distinct_users": len(b["users"]),
                         "feedback_count": b["count"],
                         "note": "No tip_kind recorded; cannot propose a template change."})
    return {"findings": findings, "habits": habits, "proposals": proposals}


def apply_proposal(templates_path: str, proposal: dict, new_text: str,
                   applied_by: str = "human-review"):
    """Append a new template version, preserving the previous text.

    Raises ValueError unless the proposal is pending_review. The file
    format is a list of version entries; nothing is ever overwritten
    in place, so a bad change can be rolled back by reading the
    previous version.
    """
    if proposal.get("status") != "pending_review":
        raise ValueError("only pending_review proposals can be applied")
    versions = []
    if os.path.exists(templates_path):
        with open(templates_path) as f:
            versions = json.load(f)
    prev = None
    for v in versions:
        if v.get("tip_kind") == proposal.get("tip_kind"):
            prev = v
    versions.append({
        "tip_kind": proposal.get("tip_kind"),
        "feedback_kind": proposal.get("feedback_kind"),
        "text": new_text, "previous_text": prev["text"] if prev else None,
        "previous_version": prev["version"] if prev else None,
        "version": (prev["version"] + 1) if prev else 1,
        "distinct_reviews": proposal.get("distinct_reviews"),
        "distinct_users": proposal.get("distinct_users"),
        "applied_by": applied_by,
        "status": "applied-by-human-review",
    })
    os.makedirs(os.path.dirname(os.path.abspath(templates_path)), exist_ok=True)
    with open(templates_path, "w") as f:
        json.dump(versions, f, indent=2)
    return versions[-1]
