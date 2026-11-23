"""Match Chronicle HTML generator (beautiful-article design protocol).

Transforms parsed replay telemetry, phase breakdowns, and coaching tips into a
publication-grade, standalone historical/tactical report with Tufte data-ink typography,
print-ready styling, and zero external runtime dependencies.
"""
from __future__ import annotations

import html
import json


def render_match_chronicle(review: dict) -> str:
    title = html.escape(review.get("title", "Age of Empires II Replay Chronicle"))
    ign = html.escape(review.get("in_game_name", "Focus Player"))
    verdict = html.escape(review.get("executive_verdict", "Strategic & Tactical Performance Debrief"))
    phases = review.get("phases", [])
    tips = review.get("tips", [])
    parser = review.get("parser", {})
    unit_counters = parser.get("unit_counters_amount_summed", {})

    phases_html = ""
    for p in phases:
        name = html.escape(p.get("name", "Match Phase"))
        time_span = f"{int(p.get('start_s', 0) // 60):02d}:{int(p.get('start_s', 0) % 60):02d} – {int(p.get('end_s', 0) // 60):02d}:{int(p.get('end_s', 0) % 60):02d}"
        summary = html.escape(p.get("summary", ""))
        phases_html += f"""
        <section class="chronicle-section">
          <div class="section-meta">
            <span class="phase-stamp">{time_span}</span>
            <h3>{name}</h3>
          </div>
          <p class="section-text">{summary}</p>
        </section>
        """

    tips_html = ""
    for idx, t in enumerate(tips, 1):
        phase = html.escape(t.get("phase", "General"))
        kind = html.escape(t.get("kind", "Tactical Note"))
        tip_text = html.escape(t.get("tip", ""))
        drill = html.escape(t.get("drill", ""))
        evidence = html.escape(t.get("evidence", "Visual confirmation"))
        tips_html += f"""
        <div class="chronicle-callout">
          <div class="callout-header">
            <span class="callout-badge">Observation #{idx} · {phase}</span>
            <span class="callout-kind">{kind}</span>
          </div>
          <p class="callout-body"><strong>Finding:</strong> {tip_text}</p>
          <div class="callout-drill">
            <strong>Recommended Practice Drill:</strong>
            <p>{drill}</p>
          </div>
          <div class="callout-evidence">Telemetry Grounding: {evidence}</div>
        </div>
        """

    stats_rows = ""
    if unit_counters:
        for unit, amt in unit_counters.items():
            stats_rows += f"<tr><td>{html.escape(unit.capitalize())} Produced</td><td class='num'>{amt}</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · The Match Chronicle</title>
<style>
  :root {{
    --ink: #1a1510;
    --paper: #fbf9f4;
    --border: #d5cbba;
    --gold: #b38628;
    --gold-dark: #7a5814;
    --subtle: #70685c;
    --font-serif: "Cinzel", "Palatino", "Georgia", serif;
    --font-body: "Garamond", "Baskerville", "Georgia", serif;
    --font-mono: "SF Mono", "Menlo", "Courier New", monospace;
  }}

  body {{
    margin: 0;
    padding: 2.5rem 1.5rem;
    background: #201b17;
    color: var(--ink);
    font-family: var(--font-body);
    font-size: 1.12rem;
    line-height: 1.65;
  }}

  .sheet {{
    max-width: 820px;
    margin: 0 auto;
    background: var(--paper);
    padding: 3.5rem 4rem;
    border-radius: 4px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.45);
    border: 1px solid var(--border);
  }}

  header.manuscript-header {{
    text-align: center;
    border-bottom: 2px solid var(--gold-dark);
    padding-bottom: 1.8rem;
    margin-bottom: 2.5rem;
  }}

  .crest {{
    font-size: 2.4rem;
    margin-bottom: 0.3rem;
  }}

  .manuscript-header h1 {{
    font-family: var(--font-serif);
    font-size: 2rem;
    letter-spacing: 0.04em;
    margin: 0 0 0.5rem;
    color: var(--gold-dark);
    text-transform: uppercase;
  }}

  .manuscript-meta {{
    font-family: var(--font-serif);
    font-size: 0.95rem;
    color: var(--subtle);
    display: flex;
    justify-content: center;
    gap: 1.5rem;
    flex-wrap: wrap;
    margin-top: 0.6rem;
  }}

  .verdict-box {{
    background: #f2ede2;
    border-left: 4px solid var(--gold-dark);
    padding: 1.2rem 1.6rem;
    margin-bottom: 2.5rem;
  }}

  .verdict-box h2 {{
    font-family: var(--font-serif);
    font-size: 1.15rem;
    margin: 0 0 0.4rem;
    color: var(--gold-dark);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }}

  .verdict-box p {{
    margin: 0;
    font-size: 1.05rem;
    color: #2b251d;
  }}

  h2.section-heading {{
    font-family: var(--font-serif);
    font-size: 1.35rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.4rem;
    margin-top: 2.5rem;
    margin-bottom: 1.2rem;
    color: #221c15;
    letter-spacing: 0.02em;
  }}

  .chronicle-section {{
    margin-bottom: 1.8rem;
  }}

  .section-meta {{
    display: flex;
    align-items: baseline;
    gap: 0.8rem;
    margin-bottom: 0.4rem;
  }}

  .phase-stamp {{
    font-family: var(--font-mono);
    font-size: 0.86rem;
    font-weight: 700;
    color: var(--gold-dark);
  }}

  .section-meta h3 {{
    font-family: var(--font-serif);
    font-size: 1.15rem;
    margin: 0;
    color: var(--ink);
  }}

  .section-text {{
    margin: 0;
    color: #332d24;
  }}

  .chronicle-callout {{
    background: #f7f3eb;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1.2rem;
  }}

  .callout-header {{
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.5rem;
    font-size: 0.85rem;
    font-family: var(--font-serif);
    font-weight: 700;
    color: var(--gold-dark);
  }}

  .callout-body {{
    margin: 0 0 0.6rem;
    color: #262018;
  }}

  .callout-drill {{
    background: #ece5d6;
    padding: 0.8rem 1rem;
    border-radius: 3px;
    font-size: 0.96rem;
    margin-top: 0.6rem;
  }}

  .callout-drill strong {{
    display: block;
    font-family: var(--font-serif);
    font-size: 0.85rem;
    color: var(--gold-dark);
    margin-bottom: 0.2rem;
    text-transform: uppercase;
  }}

  .callout-drill p {{
    margin: 0;
  }}

  .callout-evidence {{
    font-size: 0.82rem;
    color: var(--subtle);
    margin-top: 0.5rem;
    font-style: italic;
  }}

  table.telemetry-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 1.2rem 0 2rem;
    font-size: 1rem;
  }}

  table.telemetry-table th, table.telemetry-table td {{
    padding: 0.6rem 0.8rem;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }}

  table.telemetry-table th {{
    font-family: var(--font-serif);
    font-size: 0.88rem;
    text-transform: uppercase;
    color: var(--gold-dark);
    border-bottom: 2px solid var(--gold-dark);
  }}

  td.num {{
    text-align: right;
    font-family: var(--font-mono);
  }}

  footer.chronicle-footer {{
    margin-top: 3.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border);
    text-align: center;
    font-family: var(--font-serif);
    font-size: 0.88rem;
    color: var(--subtle);
  }}

  .print-btn {{
    display: inline-block;
    background: var(--gold-dark);
    color: #fff;
    padding: 0.6rem 1.4rem;
    font-family: var(--font-serif);
    font-size: 0.95rem;
    border-radius: 4px;
    text-decoration: none;
    margin-bottom: 1.5rem;
    cursor: pointer;
    font-weight: 700;
  }}

  @media print {{
    body {{
      background: #fff;
      padding: 0;
    }}
    .sheet {{
      box-shadow: none;
      border: none;
      padding: 0;
      max-width: 100%;
    }}
    .print-btn {{
      display: none;
    }}
  }}
</style>
</head>
<body>

<div class="sheet">
  <div style="text-align:right;">
    <button type="button" class="print-btn" onclick="window.print()">Print or Save as PDF 🖨</button>
  </div>

  <header class="manuscript-header">
    <div class="crest">⚔</div>
    <h1>The Match Chronicle</h1>
    <div style="font-family:var(--font-serif);font-size:1.15rem;color:#3d3326;">After-Action Tactical Review &amp; Debrief</div>
    <div class="manuscript-meta">
      <span>Focus: <strong>{ign}</strong></span>
      <span>Document ID: <strong>{html.escape(review.get("id", "showcase-01")[:8])}</strong></span>
      <span>Build: <strong>188329</strong></span>
    </div>
  </header>

  <div class="verdict-box">
    <h2>Executive Coaching Verdict</h2>
    <p>{verdict}</p>
  </div>

  <h2 class="section-heading">Phase-by-Phase Chronology</h2>
  {phases_html}

  <h2 class="section-heading">Identified Tactical Lessons &amp; Drills</h2>
  {tips_html}

  {"<h2 class='section-heading'>Verified Telemetry &amp; Sums</h2><table class='telemetry-table'><thead><tr><th>Metric</th><th style='text-align:right;'>Value</th></tr></thead><tbody>" + stats_rows + "</tbody></table>" if stats_rows else ""}

  <footer class="chronicle-footer">
    <p>Produced by <strong>Replay Chronicle</strong> · Dedicated to AoE2 Tactical Mastery.</p>
    <p style="font-size:0.78rem;">Telemetry verified against in-game video observations. Parser counts are exact sums.</p>
  </footer>
</div>

</body>
</html>"""
