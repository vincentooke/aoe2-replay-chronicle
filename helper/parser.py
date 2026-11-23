#!/usr/bin/env python3
"""Parser integration for the final-product helper (supporting numbers only).

Video is the core; this module only adds .aoe2record numbers alongside
video: age-up click times, tech research clicks, queue counters, and
villager queue-gap estimates. It NEVER produces kills, deaths, HP,
units alive, resource stockpiles, or measured TC idle time — those are
not in the mgz-fast command stream (see MVP parse_replay.py rules,
carried here verbatim in spirit).

Rules:
- mgz-fast 1.0.0 pinned for build 188329 only. Any other build or
  version fails loudly and returns parser=None; the review then stays
  honestly draft-limited (server labels it so).
- Unit counters ALWAYS sum queue `amount` fields, never rows.
- Age techs are click times only (101 Feudal, 102 Castle, 103 Imperial);
  completion times are NOT claimed.
- If mgz-fast is not importable in the packaged helper's bundled
  Python, parsing fails loudly — the helper must still upload video,
  and the review is draft-limited. It never invents numbers.
- GeForce: this module is never called — the replay file stays in the
  cloud and only video is used. Windows/Mac only.
"""
from __future__ import annotations

import importlib.metadata
import json
import os

PINNED = {188329: "1.0.0"}
AGE_TECHS = {101: "Feudal Age", 102: "Castle Age", 103: "Imperial Age"}
VILLAGER_UNIT_ID = 83
QUEUE_ACTIONS = {"Action.QUEUE", "Action.DE_QUEUE", "Action.MULTIQUEUE"}
# Action.DE_QUEUE is the DE queue command itself, NOT a dequeue.


def decode(value):
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def find_replay_file(platform: str, replay_choice: str = "newest"):
    """Locate a .aoe2record file on Windows/Mac only. GeForce -> None.

    Windows: %USERPROFILE%\\Games\\Age of Empires 2 DE\\<id>\\savegame\\
    macOS:   ~/Library/Application Support/Steam/steamapps/common/
             Age of Empires II DE/... (Steam path varies; search a few
             known roots, never prompt the user for a Terminal path).
    replay_choice 'newest' picks the newest .aoe2record by mtime;
    any other value is treated as a filename stem to match exactly.
    Returns a path string or None.
    """
    if platform == "geforce":
        return None
    roots = []
    if platform == "windows":
        base = os.environ.get("USERPROFILE", "")
        if base:
            roots.append(os.path.join(base, "Games", "Age of Empires 2 DE"))
    elif platform == "mac":
        home = os.path.expanduser("~")
        roots.append(os.path.join(home, "Library", "Application Support",
                                  "Steam", "steamapps", "common"))
    candidates = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            if "savegame" not in dirpath and "Savegame" not in dirpath:
                # Still scan: some installs keep replays beside saves.
                pass
            for f in files:
                if f.lower().endswith(".aoe2record"):
                    candidates.append(os.path.join(dirpath, f))
    if not candidates:
        return None
    if replay_choice and replay_choice != "newest":
        for c in candidates:
            if replay_choice in os.path.basename(c):
                return c
        return None
    return max(candidates, key=lambda p: os.path.getmtime(p))


def parse_replay(path: str, allow_other_version: bool = False):
    """Parse one .aoe2record. Returns (parser_dict | None, error | None).

    On any failure, parser_dict is None and error explains why — the
    caller must surface that as draft-limited, never fill numbers in.
    """
    if not path or not os.path.isfile(path):
        return None, f"no replay file at {path!r}"
    try:
        import mgz.fast  # noqa: F401
    except ImportError:
        return None, ("mgz-fast is not importable in this helper's Python; "
                      "parser numbers unavailable, review stays draft-limited")
    try:
        version = importlib.metadata.version("mgz-fast")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    if not allow_other_version and version != "1.0.0":
        return None, f"mgz-fast version {version} is not pinned 1.0.0; refusing to parse"
    try:
        from mgz.fast.header import parse as parse_header
        from mgz.fast import meta, operation
        from mgz.fast.enums import Operation
        with open(path, "rb") as f:
            header = parse_header(f)
        de = header.get("de", {}) if isinstance(header, dict) else {}
        build = de.get("build")
        if build not in PINNED:
            return None, (f"unsupported game build {build!r}; pinned builds: "
                          f"{sorted(PINNED)} — refusing to parse")
        if PINNED[build] != version and not allow_other_version:
            return None, f"build {build} pinned to mgz-fast {PINNED[build]}, got {version}"
        players = []
        for idx, p in enumerate(de.get("players", [])):
            players.append({
                "header_index": idx, "action_player_id": idx + 1,
                "name": decode(p.get("name")) if isinstance(p, dict) else str(p),
                "civ_id": p.get("civilization_id") if isinstance(p, dict) else None,
            })
        real = [p for p in players if p["name"]]

        def pname(pid):
            if isinstance(pid, int) and 1 <= pid <= len(players):
                return players[pid - 1]["name"] or f"unmapped:{pid}"
            return f"unmapped:{pid}"

        age_ups, research, queues, resigns = [], [], [], []
        cum_ms, total_ops = 0, 0
        with open(path, "rb") as f:
            parse_header(f)
            meta(f)
            while True:
                try:
                    op_type, payload = operation(f)
                except EOFError:
                    break
                total_ops += 1
                if op_type == Operation.SYNC:
                    inc = payload[0] if isinstance(payload, tuple) else None
                    if isinstance(inc, int):
                        cum_ms += inc
                elif op_type == Operation.ACTION:
                    act_type, act = payload
                    name = str(act_type)
                    if not isinstance(act, dict):
                        continue
                    pid = act.get("player_id")
                    if name == "Action.RESEARCH":
                        row = {"time_ms": cum_ms, "time_min": round(cum_ms / 60000, 2),
                               "player": pname(pid), "tech_id": act.get("technology_id")}
                        research.append(row)
                        if row["tech_id"] in AGE_TECHS and not any(
                                a["player"] == row["player"] and a["tech_id"] == row["tech_id"]
                                for a in age_ups):
                            age_ups.append({**row, "age": AGE_TECHS[row["tech_id"]]})
                    elif name in QUEUE_ACTIONS:
                        queues.append({"time_ms": cum_ms, "time_min": round(cum_ms / 60000, 2),
                                       "player": pname(pid), "unit_id": act.get("unit_id"),
                                       "amount": act.get("amount")})
                    elif name == "Action.RESIGN":
                        resigns.append({"time_ms": cum_ms, "time_min": round(cum_ms / 60000, 2),
                                        "player": pname(pid)})
    except Exception as e:
        return None, f"mgz-fast failed while parsing {path}: {e!r}; no numbers trusted"
    # Amount-summed counters, never row counts.
    counters = {}
    for q in queues:
        per = counters.setdefault(q["player"], {"queue_rows": 0, "units_amount_summed": 0,
                                                "by_unit_id": {}})
        per["queue_rows"] += 1
        amt = q["amount"] if isinstance(q["amount"], int) else 0
        per["units_amount_summed"] += amt
        by = per["by_unit_id"].setdefault(str(q["unit_id"]), {"rows": 0, "units": 0})
        by["rows"] += 1
        by["units"] += amt
    # Villager queue gaps: ESTIMATES only, >60s between villager queues.
    villager_gaps = {}
    for player in sorted({q["player"] for q in queues if q["unit_id"] == VILLAGER_UNIT_ID}):
        times = sorted(q["time_min"] for q in queues
                       if q["player"] == player and q["unit_id"] == VILLAGER_UNIT_ID)
        gaps = [{"from_min": round(a, 2), "to_min": round(b, 2), "gap_min": round(b - a, 2)}
                for a, b in zip(times, times[1:]) if b - a > 1.0]
        villager_gaps[player] = {
            "label": "QUEUE-GAP ESTIMATE ONLY — not measured TC idle time",
            "gaps_over_60s": gaps,
        }
    parser = {
        "parser": "mgz-fast", "parser_version": version, "game_build": build,
        "duration_min": round(cum_ms / 60000, 2), "total_ops_walked": total_ops,
        "players": real,
        "age_ups_click_times_only": sorted(age_ups, key=lambda r: r["time_ms"]),
        "age_up_note": "Research click times only. Completion times NOT claimed.",
        "research_total_rows": len(research),
        "unit_counters_amount_summed": counters,
        "villager_gaps": villager_gaps,
        "resignations": sorted(resigns, key=lambda r: r["time_ms"]),
        "not_recovered": ["kills, deaths, HP, units alive",
                          "resource stockpiles (not in command stream)",
                          "measured TC idle time (only queue-gap estimates)",
                          "age-up completion times (only click times)",
                          "fight outcomes / micro (video only)"],
    }
    return parser, None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument("--out", default="-")
    args = ap.parse_args()
    parser, err = parse_replay(args.replay)
    if err:
        print(f"error: {err}", file=__import__("sys").stderr)
        raise SystemExit(2)
    text = json.dumps(parser, indent=2, default=str)
    if args.out == "-":
        print(text)
    else:
        with open(args.out, "w") as f:
            f.write(text)
        print(f"parser summary: {args.out}")


if __name__ == "__main__":
    main()
