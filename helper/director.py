"""Camera director: where the camera should look, decided from the game.

This replaces the fixed 4-point timer tour, which Vincent corrected
2026-11-04: visiting 4 fixed minimap points proves the camera CAN
move, not that it looks at the right things. A review built on a
parked or wandering camera cannot support claims about fights,
players, or decisions.

V4 analyst priorities, highest first (Vincent's corrections
2026-11-04: bases still matter for analysis, and the camera must
focus on the uploader and their team). V5 (run 17 lesson) bounds
the sticky fight below — hold cap, static-mix demotion, focus
floor, guaranteed base-check slot — without changing this order.
V6 (run 18 lesson) adds motion: fights are ranked by how much
they CHANGE between scans (a battle moves; a base sits still),
the camera follows a fight that moves to a neighbouring cell,
small raids count as fights, and the hold is dynamic (a fight
that keeps moving earns a longer hold; one that goes quiet is
dropped early). V6 also fixes the v5 base-check slot, which
never fired live (see Run 18 lesson), and — Vincent's direction
2026-11-05 — defaults to MOVING: the camera tours on when
nothing relevant is happening instead of parking on the last
spot, and the tour step itself is shorter (test 30s, 15s in a
fight) so a battle cannot start, peak and end unseen.
1. ACTIVE FIGHT, sticky (v3): once a fight cell is chosen, the
   camera STAYS on it while its mix persists. A fight is never
   abandoned for a base or a sweep point — but v5 interrupts it
   for one step every BASE_CHECK_EVERY steps (a base check) and
   ends it after FIGHT_HOLD_MAX holds or a static mix (see Run
   17 lesson below); v6 follows it when it moves next door and
   extends the hold while it keeps moving (see Run 18 lesson);
   it then resumes or exits, never parks.
2. FRESH FOCUS FIGHT: a new balanced, moved mix involving the
   focus team (uploader + teammates), in a cell never visited as
   a fight this run. A fight with no focus team involved ranks
   below EVERY focus-team item, never above them.
3. FOCUS ATTENTION: a focus base under attack (an enemy colour
   appearing in a former focus single-colour cell) or a new focus
   expansion (a new dense focus cell appearing). These fire even
   when the rotation timer has not elapsed — they are events,
   not rotation.
4. PURPOSEFUL FOCUS BASE CHECKS at quiet times: economy,
   production and expansion checks, rotating through ALL focus
   players' bases across a phase so each player's eco, production
   and decisions get seen. Each visit carries its check kind in
   the debug record (eco_check / production_check /
   expansion_check). Focus bases may be revisited across phases;
   the fight visited-set rule never blocks a base revisit.
5. OPPONENT FIGHTS: fresh opponent-only fights, below every
   focus-team item but above holding — useful context, not the
   subject.
6. OPPONENT BASES, occasionally and only when relevant: at most
   1 in 4 base visits, and only for an opponent base under attack
   by the focus team or a new opponent expansion/castle.
   Otherwise opponent bases are skipped entirely.
7. MOVE, don't park (v6, Vincent's direction 2026-11-05): when
   nothing relevant is happening, the camera moves to the next
   relevant spot — a base check when rotation is due, an
   opponent fight or relevant opponent base, else the next sweep
   point — instead of sitting on the last spot. The old "hold
   last spot" behaviour is gone: 60s between moves was already
   too slow, and parking is the opposite of what a review needs.
   The "hold" reason survives only as a label for old logs and
   as a defensive branch in the helper; the director never
   returns it. Sweep survives as the quiet-time default, not
   just for scan failure and first placement.

Motion is a RATE, not a pixel count (v6): the tour step is now
30s at test pace and 15s inside a fight (120s/60s at standard),
so the pixel change between two scans shrinks as the sampling
gets faster — a base drifts ~5 px per 60s scan but ~1-2 px per
15s scan, while a fight keeps moving. Every change threshold is
therefore calibrated at a 60s reference interval and scaled by
the actual time between the two scans being compared
(_bar). At the reference interval the numbers are the v5 bars
(FIGHT_MOVE_MIN 8, MOTION_MIN 16); at 15s they are a quarter
of that, with a 4 px floor (v10, run 22 lesson) so stream noise
— and a gold pile's ~3 px minimap jitter on short scan gaps —
alone never counts as movement.

Focus plumbing: the director takes an optional focus_colours set
(minimap buckets for uploader + teammates); every other bucket is
an opponent. The helper's --focus-colours flag supplies it. When
absent, focus is UNMAPPED: all players are treated as focus and
the opponent rules are disabled — the log says so honestly, and
the director never guesses a mapping. Colour-to-player mapping
is per-match (colours vary by slot) and remains OPEN product
work: the server flow must ask the uploader who they are, or
parse the replay on Windows/Mac. No player's colours are
hardcoded anywhere in product code; the Nov 2 replay mapping
(green/cyan/blue focus) lives only in a test case.

Phase awareness: deliberately NOT implemented in v4. The tour
loop does not read the game clock per step (clock is read once
for the unpause check), and age labels would need a new,
uncalibrated OCR crop; game-time-to-phase approximations vary
too much by build and speed to weight priorities safely. The
priority order above already gives phase coverage — eco checks
early via rotation, armies and map control later via fights —
without risking capture to read the clock. Phase weighting is
open future work, not a v4 claim.

Run 16 lesson (2026-11-04, 1200s director-v2 run, 20 decisions:
1 sweep, 19 fight, 0 base_rotation): the director hopped to a
new "fight" cell every 60s, and every repeat landed ~660s after
the previous win — just outside v2's 600s window, so the window
never blocked anything. The mixes were balanced red/yellow
(second buckets 23-56 pixels) and passed v2's balance bar — and
run-15 frame verification already proved such mixes are
bases/resources, not battles. So v3/v4 stop tuning what counts
as a fight on one scan and instead control what happens ACROSS
scans: stay on a fight, never re-win a visited cell, never let
a base or a sweep point interrupt a fight, and hold rather
than wander.

Run 17 lesson (2026-11-05, 1200s director-v4 run, 20 decisions:
1 sweep, 3 fights, 16 fight_holds, 0 base checks): v4's
stickiness turned a false positive into a 12-minute park. Step 2
won cell (8,7) — yellow 61, red 26, green 1 — as a "focus fight"
(one green pixel counted as focus), then steps 3-13 held it
while its counts barely moved (yellow 58-64, red 22-30, total
88-90): a base's economy pixels, not a battle. Steps 14-19 did
the same on a green-dominant base cell. Vincent watched live:
the camera sat at Drake's (opponent) base while fights happened
elsewhere and never looked at his team's bases. So v5 bounds
the hold three ways: (1) FIGHT_HOLD_MAX caps consecutive holds
on one cell; (2) static-mix demotion exits when the mix moves
less than STATIC_MOVE_MIN on STATIC_HOLDS_TO_DEMOTE consecutive
holds — a real fight moves, a base does not; (3) a focus floor
(FOCUS_MIN_PIXELS, the same 6 px as the attention floor) so a
trace of a focus colour cannot make a cell a focus fight; and
(4) a guaranteed focus base-check slot every BASE_CHECK_EVERY
steps, so base checks can never starve for a whole run again.
A base check interrupts a fight for one step but does not
abandon it: the active fight resumes on the next step.

Run 18 lesson (2026-11-05, 1200s director-v5 run, 20 decisions):
v5 fixed the 12-minute park (hold cap fired; bases viewed
better — Vincent confirms), but key battles were still missed.
The camera spent fight + 3 holds = ~4 minutes on one cell at
test pace and judged one minimap snapshot per step, so a battle
could start, peak and end while the camera was locked in, a
fight that moved cell to cell was never chased, and small raids
never reached the 15 px fight bar. Cell (4,4) proves the
snapshot problem: green steadily rising 68->73->80 while yellow
faded 29->21->18 is a base with a passing army, yet it passes
the fight bar (second bucket >= 15 px and >= 25%). So v6: (1)
motion ranks fights — the most-changed mixed cell first, with
delta >= MOTION_MIN (rate-scaled) marking an unambiguously
moving fight; (2) the camera FOLLOWS a fight that moves to a
neighbouring cell (fight_follow); (3) a raid — focus colours
plus >= 6 px of an opponent colour — is a first-class focus
fight even below the 15 px bar; (4) the hold is dynamic: a
fight that keeps moving earns up to FIGHT_HOLD_MAX_EXTENDED
holds, one that goes quiet is dropped early by the static
demotion; (5) the tour loop re-checks twice as fast inside a
fight (helper.py next_tour_interval) and the base interval is
shorter (test 60s -> 30s, standard 300s -> 120s), so no spot is
held longer than ~2 minutes without a live fight.

Slot-fix lesson (run 18 completion check, final log, 77 lines):
v5's guaranteed base-check slot NEVER fired — zero base checks
in all 20 steps, steps 4/8/12/16 all fight_hold. The slot's
step counting was fine; its precondition was impossible:
_base_cells_ required a STRICTLY single-colour cell, but a real
minimap cell is never single-colour — a base sits with gold,
trees and terrain in the same 10x10 cell (run-18 cells were all
mixed, e.g. (4,4) green 70, yellow 28), and terrain pixels
bucket as colours too. Reproduced in a diagnostic: base_cells
returns [] on a live-like grid. So v6 defines a base by
DOMINANCE, not purity: one bucket with >= BASE_MIN_PIXELS and
>= BASE_DOMINANT_SHARE (60%) of the cell total. Observed
separation: run-18 bases measure 69-71% dominant, run-18 fight
cells 40-50%. The same dominance rule fixes the attention
events (under-attack / expansion), which used the same strict
single-colour test and also never fired live.

Run 19 lesson (2026-11-05, 1200s director-v6 run, 69 decisions):
v6's log looked like the director finally worked (24 fights, 19
fight_follows, 6 base checks, both safety exits fired) — but 14
frames of the video prove otherwise: 0 of 14 show a real battle,
even in Castle Age with Drake at 500-766 military. 4 of 14 are
empty ground, 5 of 14 are peaceful bases mislabelled as fights, 3
of 14 are correct base checks. The 19 fight_follows followed
villager/scout/eco movement, not combat. Motion alone cannot tell
combat from economy on the minimap — and the minimap itself is
polluted: Arabia's sand terrain (RGB ~208,149,82) buckets as
"yellow" (~38% of the diamond's pixels, 74-88 dominant-yellow
cells per scan), so every cell looks mixed and every base looks
like a fight. The base slot's late start has the same root: the
slot fired only from step 48 because base_cells truncated to the
top 6 dominant cells and the sand-yellow flood filled all 6 slots,
so the small early-game focus bases (green 47 px, blue 17 px)
never made the list — the step counter was fine, the precondition
was impossible. And the base-under-attack view (tail-10) had the
attack at the frame's edge because the director clicks the cell
centre, not the dots' centroid. So v7: (1) a MILITARY-SCORE fight
signal — OCR the score panel's Military column from the same probe
screenshot and track per-player military across scans; a fight
exists only where military is present AND changing (falling scores
= units dying = a fight happening now). It suppresses all fight
labels while every military is 0 (the whole early game) and
prioritises candidates whose players are losing military. When the
panel cannot be read, a clock phase gate (no fights before 10
game-minutes, reusing the calibrated clock crop) takes over — the
director never silently falls back to motion-only fights. (2)
CENTROID AIMING — the raw per-bucket pixel centroid within the
winning cell (sub-cell precision from the 120x120 scan), so the
action lands mid-frame; raids/attacks aim at the attackers, base
checks at the base colour. (3) DENSITY FLOOR — a follow target
must now pass the same fight-entry bars (balance/raid) as a fresh
fight: run 19's empty frame-08 cell won only via follow, which had
no balance bar. A pixel-cluster floor was TESTED and REJECTED: on
the real run-19 frames the densest-quadrant share of empty cells
(0.28-0.31) is indistinguishable from real bases (0.26-0.29) —
the sand flood makes everything equally "dense" — so the floor is
the balance bar on follow plus the military gate, not a cluster
threshold. (4) BASE REGISTRY — the slot filters bases by side
BEFORE truncating (the actual late-start fix) and keeps a
persistence registry of each focus colour's densest cell, so a
small early-game base still earns its slot from step 4.

How it sees: ffmpeg crops the minimap diamond (relative bounds,
same as calibration), scales it to a 12x12 grid, and classifies
each pixel into an AoE2 player-colour bucket by RGB dominance.
Thresholds are approximate — minimap colours vary with terrain
and lighting — so every decision is logged with its reason, and
the director NEVER clicks outside the diamond.

Wired into run_real_capture behind --director since runs 13-15;
without the flag the run-12 fixed tour behaves exactly as before.

Pure stdlib + ffmpeg only, like the rest of the helper.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

GRID = 12
SCALE = 120  # minimap crop is scaled to SCALE x SCALE before gridding
CELL = SCALE // GRID

# Candidate minimap diamond, normalized (same reference as calibration).
DIAMOND_NORM = (0.482, 0.822, 0.657, 0.998)

ROTATION_EVERY_S = 180  # revisit a new base at most every 3 minutes
FIGHT_MIN_BUCKETS = 2   # distinct player colours in one cell
FIGHT_MIN_PIXELS = 6    # total coloured pixels in the cell
FIGHT_MOVE_MIN = 8      # pixel-count change vs previous scan (a battle moves; a base does not)
BASE_MIN_PIXELS = 15    # single-colour pixels marking a base cluster
# v2 balance test (run 15 lesson): the second-largest bucket in a
# fight cell must clear both bars. Run-15 numbers: balanced mixes
# had second buckets of 42-55 pixels and 40-50% share; the step-15
# false fight was yellow 89, red 3, green 2 (second 3 pixels, 3%
# share); the largest pure-trace bucket anywhere in run 15 was 11
# pixels, and the smallest non-trace second share was 19% (step 12,
# dominant yellow). Synthetic genuine mixes measure second 18-27
# pixels, 30-33% share. So 15 pixels sits above every trace bucket
# and below every genuine second bucket, and 25% share sits between
# the 3% trace case and the 30%+ genuine floor, while also rejecting
# the dominant-yellow step-12 cell (19% share).
FIGHT_MIN_SECOND_PIXELS = 15  # second-largest bucket, absolute floor
FIGHT_MIN_SECOND_SHARE = 0.25  # second-largest bucket, share of cell total
# v15: minimum thresholds to dispatch a suspect visit when no active
# combat drop is observed.  Both colours must have >= 15 px (second >= 15)
# and total coloured pixels in the cell must reach 50.  Cuts out thin
# mid-map scout collisions and passing patrols without blocking real fights.
FIGHT_SUSPECT_MIN_PIXELS = 50         # min total pixels in cell to dispatch a suspect
FIGHT_SUSPECT_MIN_SECOND_PIXELS = 15  # min second-colour px to dispatch a suspect
# v3 stickiness (run 16 lesson): the director stays on a fight
# instead of hopping every tour step, and a visited fight cell
# never wins again this run. (v2's FIGHT_REPEAT_WINDOW_S is gone:
# run 16 proved a 600s window never blocks anything, since every
# repeat landed ~660s after the previous win.)
DIRECTOR_VERSION = 17
# v14 dynamic rhythm and fight cooldowns:
# A cell visited as a fight or suspect enters cooldown for this many seconds,
# preventing immediate re-triggering while allowing repeat clashes at the same choke point.
FIGHT_COOLDOWN_S = 90
# v13 wasted-view guard: keep camera target points inside a safe margin of the
# minimap diamond. The diamond perimeter has L1 distance |norm_x - 0.5| + |norm_y - 0.5| = 0.5.
# Clicking near or outside the boundary places the main camera over black void.
# DIAMOND_SAFE_MARGIN scales the maximum allowed L1 distance (0.5 * 0.80 = 0.40),
# pulling edge cells inward so the camera frames units without showing empty black space.
DIAMOND_SAFE_MARGIN = 0.80
# v7 military-score signal (run 19 lesson): score-panel geometry,
# fractions of the probe screenshot. Measured on 8 real run-19
# frames at 1440x900; the panel is a fixed layout (6 player rows,
# same order every frame). Row centres: first 791/900, pitch
# 12/900. Swatch (colour square with the player number): x
# 228-241/1440, y row_centre+1 to +5 (the lower half — the upper
# half catches the previous row's swatch, rows are 12 px apart).
# Military digits: x 448-482/1440, y row_centre +/- 6.
# v8 (run 20 lesson: the v7 per-row tesseract read NEVER produced
# a live reading, 0 of 27 steps): the row geometry was off by
# ~4 px AND the per-row crop itself is unreadable — see
# read_military_scores. The first row centre is 795/900, not
# 791/900 (measured on 12 real run-20 frames: OCR word-box
# centres sit ~4-5 px below the v7 centres on every row, and a
# luminance peak confirms row 0 at ~794-795). Pitch unchanged.
# The swatch read is unaffected by the correction (verified
# 12/12 run-20 frames with both the old and the new centres).
PANEL_ROW_Y0 = 0.8833       # first player row centre (795/900)
PANEL_ROW_PITCH = 0.01333   # row spacing (12/900)
PANEL_SWATCH_X0 = 0.1583    # swatch x (228/1440)
PANEL_SWATCH_X1 = 0.1674    # swatch x (241/1440)
PANEL_MIL_X0 = 0.3111       # Military digits x (448/1440)
PANEL_MIL_X1 = 0.3347       # Military digits x (482/1440)
PANEL_ROWS = 6
# v8 wide strip (the read path): the digit reader works on the
# whole panel strip, not one row at a time — x 300-560/1440 covers
# the Total Score, Military and Economy columns, so the OCR engine
# sees full text lines (player name + three numbers) instead of a
# lone glyph. The strip is extended 12 px past the first/last row
# so neither edge row sits on the crop boundary.
PANEL_WIDE_X0 = 0.2083      # wide strip left (300/1440)
PANEL_WIDE_X1 = 0.3889      # wide strip right (560/1440)
PANEL_STRIP_EXTEND_PX = 12  # source px past first/last row centre
PANEL_STRIP_SCALES = (4, 6)  # both always run: 6x cross-checks 4x and fills missing rows
# Clock phase gate (v7 fallback): when the panel cannot be read,
# no fight labels before this many game-seconds. 10 minutes: the
# first military in run 19 appeared at ~22:39 and no fight can
# exist before units are trained; Feudal fights before 10:00 are
# rare enough that suppressing them costs less than the false
# fights motion alone produces in the early game.
PHASE_GATE_S = 600
# v7 base registry (slot late-start fix): a cell counts for the
# registry at a lower floor than _dominant (8 px, not 15) — a
# Dark Age TC is small — but only once it PERSISTS: the same
# bucket at the same cell on 2 scans. A passing army never
# repeats at one cell; a base does.
REGISTRY_MIN_PIXELS = 8
REGISTRY_MIN_SHARE = 0.6
REGISTRY_CONFIRM_SCANS = 2
# A fight cell is 10x10 = 100 pixels at most (SCALE 120 / GRID 12).
# Run-16 base mixes cluster at 82-100 pixels, so hops between
# bases differ by under 20. A +40 margin means a switch during a
# grace scan only fires for a genuinely denser clash against a
# weak active cell — never for one base mix replacing another.
FIGHT_SWITCH_MARGIN = 40  # new-cell total minus active total, pixels
# Consecutive scans where the active cell no longer holds a mix
# before the director leaves it. 1 would drop a fight on a single
# noisy/stream-artefact scan; 2 means 120s of absence at test
# pace (60s steps) and 600s at standard pace (300s steps) — the
# cost of patience scales with the pace, and is documented here
# rather than hidden. The first miss is a grace scan: the camera
# still holds the fight spot while a stronger clash may pre-empt.
FIGHT_EXIT_MISSES = 2
# v4 focus + analyst checks.
KNOWN_BUCKETS = {"red", "blue", "green", "yellow", "cyan", "purple", "orange"}
BASE_CHECK_KINDS = ("eco_check", "production_check", "expansion_check")
OPPONENT_BASE_EVERY = 4  # at most 1 in 4 base visits may be opponent
# Attention floor (v4): an opposite colour appearing in a formerly
# CLEAN single-colour base cell needs only this many pixels to
# earn a look. Deliberately below the fight bar (15): a small raid
# must not need a full battle to deserve the camera. The
# single->mixed transition is what keeps this honest — ambient
# traces live in already-mixed cells, while a clean base cell
# gaining 6+ enemy pixels means units actually entered it.
ATTENTION_MIN_OPP_PIXELS = 6
# v9 attack gate (run 21 lesson): the attention floor alone
# cannot tell a raid from terrain. Run 21's base_under_attack
# fired 10x on the same two cells with an identical yellow 7 px
# while every military was 0 — a GOLD PILE inside the base cell
# (gold renders yellow on the minimap and never moves). An
# opposite-colour patch must MOVE or be military-backed before it
# counts as an attack: the opposite buckets' counts must change
# by at least this many pixels (rate-scaled by _bar) versus the
# previous scan — a raid moves, a gold pile does not — OR the
# attacking colour must actually have military. A static patch
# with zero military never produces base_under_attack; the cell
# stays an ordinary base, visitable by the base-check rotation.
ATTACK_MOVE_MIN = 4
# v5 bounds (run 17 lesson): the hold is earned every scan.
# FIGHT_HOLD_MAX caps consecutive fight_hold returns on one cell
# — a genuine fight rarely stays in one 10x10 minimap cell for
# more than ~4 tour steps, and a parked base must not keep the
# camera past that. The cap counts STEPS, so its wall-clock cost
# scales with the pace (3 min at test pace, 15 min at standard
# pace), the same convention as FIGHT_EXIT_MISSES.
FIGHT_HOLD_MAX = 3
# Static-mix demotion: a held fight whose bucket counts move by
# less than STATIC_MOVE_MIN (the same bar a fresh fight must
# clear to enter, FIGHT_MOVE_MIN) on STATIC_HOLDS_TO_DEMOTE
# consecutive holds is behaving like a base, not a battle — run
# 17's parked cell drifted by ~5 px per scan for 11 scans, while
# real fights move as units die and reinforcements arrive. Two
# consecutive static holds demote it; a single static scan does
# not (a siege can sit still for one scan). Demotion and the cap
# are complementary: demotion exits the truly static cells early,
# the cap is the backstop for jittery-but-parked ones.
STATIC_MOVE_MIN = 8
STATIC_HOLDS_TO_DEMOTE = 2
# Focus floor (run 17 lesson): a cell counts as focus only with
# at least this many focus-colour pixels. Run 17's first "focus
# fight" had ONE green pixel in a yellow/red cell; one pixel must
# not outrank every focus base check below it. 6 px matches the
# attention floor (ATTENTION_MIN_OPP_PIXELS) — the same "a real
# presence, not a trace" bar, applied symmetrically.
FOCUS_MIN_PIXELS = 6
# Guaranteed focus base-check slot (run 17 lesson): every
# BASE_CHECK_EVERY-th tour step is a focus base check, whatever
# the fight state — 0 of 20 visits were base checks in run 17,
# because the fake fight never released. 4 means a base check at
# least every 4 tour steps (every 4 min at test pace, 20 min at
# standard pace). The slot interrupts a fight for one step but
# never abandons it: the active fight resumes next step.
BASE_CHECK_EVERY = 4
# v6 motion (run 18 lesson): battles move; bases (even busy
# ones) are comparatively stable. MOTION_MIN is the per-scan
# bucket-count change that marks a cell as unambiguously moving,
# calibrated at the MOTION_BASE_DT_S reference interval. Run-18
# numbers (60s scans): genuine fight scans moved 8-21 px (peak
# 21, cell (4,8)); the parked base cell (4,4) never exceeded 13;
# run 17's park drifted ~5 px/scan. So 16 sits above every
# observed base drift and below the observed genuine-fight peak.
# Motion RANKS fights (most-changed first) and earns the hold
# extension and the follow — it does not gate: a cell below it
# can still win as a fight via the normal bars.
MOTION_MIN = 16
# Reference interval (seconds) the pixel-change bars are
# calibrated at. _bar() scales a bar by dt / this value, so the
# same fight reads the same at 15s, 30s, 60s or 120s sampling.
MOTION_BASE_DT_S = 60.0
# Dynamic hold (run 18 lesson): a fight that keeps moving earns
# up to FIGHT_HOLD_MAX_EXTENDED holds instead of FIGHT_HOLD_MAX;
# the extension lasts only while each hold keeps moving at or
# above MOTION_MIN (rate-scaled), and the absolute cap means the
# camera can never park 12 minutes again. The early-exit half of
# the dynamic hold is v5's static demotion (moved below the
# scaled STATIC_MOVE_MIN for STATIC_HOLDS_TO_DEMOTE holds) —
# unchanged.
FIGHT_HOLD_MAX_EXTENDED = 6
# Base dominance (slot-fix lesson, run 18): a base cell is one
# where a single bucket holds at least BASE_MIN_PIXELS and at
# least this share of the cell total. A real minimap cell is
# never single-colour (base + gold/trees/terrain), so the v4/v5
# strict single-colour test found no bases at all in live runs
# 17-18. Observed separation: run-18 bases 69-71% dominant,
# run-18 fight cells 40-50%.
BASE_DOMINANT_SHARE = 0.6
# v12 combat check (run 25 lesson): a minimap-motion + military call
# is a SUSPECT, not a fight. Run 25 called 6 fights and 6 holds; frame
# verification showed 0 pitched battles in 16 frames (0 in 80, runs
# 19-25). The minimap cannot tell combat from movement: frame 031
# even has Drake's whole purple army in shot, just standing there.
# A suspect is confirmed only by real combat evidence, from either
# leg below. A confirmed fight is held while evidence persists (see
# COMBAT_EVIDENCE_MISSES); the existing hold cap still bounds it.
# Evidence leg 1 — health bars in the main view. Calibrated on the
# 19 run-25 frames (tests/fixtures/run25/): a health bar is a VIVID
# red/green horizontal run, 15-40 px long, 2-6 rows tall, solid.
# Tilled farm soil (210,145,80) and thatch roofs (207,51,36) are
# brown-red, not vivid: a loose mask (r-g>60) counted 16 "bars" in
# frame 034 and 5 in frame 028, but RGB sampling showed all but two
# are soil/roof. The vivid masks below count exactly 2 red bars in
# frame 034 — the two the verifier saw over two buildings — and 0
# in all 18 other frames. Two bars is the bar: one damaged building
# keeps its bar long after combat ends, so a lone bar is not combat;
# two or more damaged entities in one view means a fight happened
# here. The green leg has no true positive in run 25 (0 vivid green
# bars in every frame) and is retained unproven, same rule, for
# symmetry — a future battle may damage own units.
COMBAT_BARS_MIN = 2
COMBAT_BAR_MIN_RUN = 15  # solid run length (px, 1440-reference) of one bar row
COMBAT_BAR_MAX_RUN = 40  # longer than a bar: two merged bars or a roof edge
COMBAT_BAR_MIN_ROWS = 2  # bar height, rows
COMBAT_BAR_MAX_ROWS = 6
COMBAT_VIEW = (0.0, 0.06, 0.84, 0.85)  # main view (x0, y0, x1, y1, fractions):
# no top resource bar, no bottom score/minimap panel, no right overlay
COMBAT_VIEW_REF_W = 1440  # bars are measured after scaling the crop to this width
# Evidence leg 2 — military drop. A single bucket's military falling
# by this much between consecutive COMPLETE stamps means units died.
# The total never fell in run 25 (production masked deaths: totals
# climbed 0 -> 2410 monotonically), so the leg is per-bucket, not
# total — a bucket falling while the total rises still fires. 50 is
# ~5-10% of a mid-game army (500-1000) and far above OCR-agreement
# noise (the v8 cross-check drops disputed rows rather than reading
# them wrong). Both stamps must be complete: a missing row must not
# fake a drop. A drop alone never locates a fight, so it promotes a
# fresh fight to confirmed only when the dropping bucket is IN the
# fight cell; anywhere else it confirms a suspect the camera is
# already looking at.
# v14: lowered from 50 to 15 to catch smaller early/mid skirmishes (Option 2C).
COMBAT_DROP_MIN = 15
# A confirmed fight is held while combat evidence persists; this
# many consecutive hold scans with NO evidence ends it (the battle
# ended or moved on). 2, not 1: one scan can miss (angle, JPEG)
# and a battle's drops are lumpy. A scan whose bars read FAILED
# (unknown) does not count as a miss — only a successful scan that
# found nothing does. The hold cap and static demotion still bound it.
COMBAT_EVIDENCE_MISSES = 2


# Sentinel for "caller did not supply this value" (distinct from None,
# which means "read it and got nothing"). Used by Director.next_target
# for the military/clock test hooks.
_UNSET = object()


def bucket(r: int, g: int, b: int):
    """AoE2 minimap player-colour bucket for one pixel, or None.

    Buckets are RGB-dominance approximations, ordered so the most
    specific matches win (yellow before orange, cyan before blue).
    Grey/low-saturation pixels (terrain, unexplored) return None.
    """
    if max(r, g, b) < 110:
        return None
    if max(r, g, b) - min(r, g, b) < 50:
        return None
    if r > 150 and g > 120 and b < 100:
        return "yellow"
    if r > 150 and 70 <= g <= 150 and b < 80:
        return "orange"
    if g > 110 and b > 110 and r < 100:
        return "cyan"
    if r > 100 and b > 100 and g < 90:
        return "purple"
    if r > 120 and r - g > 50 and r - b > 50:
        return "red"
    if g > 110 and g - r > 50 and g - b > 30:
        return "green"
    if b > 120 and b - r > 50 and b - g > 30:
        return "blue"
    return None


def scan_minimap(image_path: str, diamond=DIAMOND_NORM):
    """Grid of player-colour counts for the minimap diamond.

    Returns a GRID x GRID list of dicts {bucket: pixel_count}, or
    None when the scan itself fails. Rows are top-to-bottom,
    columns left-to-right, matching the diamond on screen.
    """
    try:
        probe = subprocess.run(["ffprobe", "-v", "error",
                                "-select_streams", "v:0",
                                "-show_entries", "stream=width,height",
                                "-of", "csv=p=0", image_path],
                               capture_output=True, text=True, timeout=30)
        parts = (probe.stdout or "").strip().splitlines()[0].split(",")
        full_w, full_h = int(parts[0]), int(parts[1])
        nx0, ny0, nx1, ny1 = diamond
        cw = int((nx1 - nx0) * full_w)
        ch = int((ny1 - ny0) * full_h)
        x0 = int(nx0 * full_w)
        y0 = int(ny0 * full_h)
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", image_path,
                              "-vf", f"crop={cw}:{ch}:{x0}:{y0},scale={SCALE}:{SCALE}",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, timeout=60)
        data = out.stdout
        row_bytes = SCALE * 3
        grid = [[{} for _ in range(GRID)] for _ in range(GRID)]
        for r in range(SCALE):
            row = data[r * row_bytes:(r + 1) * row_bytes]
            gr = min(GRID - 1, r // CELL)
            for px in range(SCALE):
                if abs(px + 0.5 - SCALE / 2.0) + abs(r + 0.5 - SCALE / 2.0) > 0.48 * SCALE:
                    continue
                i = px * 3
                bk = bucket(row[i], row[i + 1], row[i + 2])
                if bk is None:
                    continue
                cell = grid[gr][min(GRID - 1, px // CELL)]
                cell[bk] = cell.get(bk, 0) + 1
        return grid
    except Exception:
        return None


def scan_centroids(image_path: str, diamond=DIAMOND_NORM):
    """Per-bucket pixel centroids within each minimap cell, or None.

    Same ffmpeg pass as scan_minimap (SCALE 120), but instead of
    counts it accumulates, per cell per bucket, the mean pixel
    position. Returns a GRID x GRID list of dicts
    {bucket: (fx, fy, n)} where fx/fy are 0..1 within the cell
    and n is the pixel count. The director aims at these centroids
    (v7) instead of the cell centre, so the action — not the
    middle of a cell that happens to contain it — lands mid-frame.
    None when the scan fails; aiming then falls back to the centre.
    """
    try:
        probe = subprocess.run(["ffprobe", "-v", "error",
                                "-select_streams", "v:0",
                                "-show_entries", "stream=width,height",
                                "-of", "csv=p=0", image_path],
                               capture_output=True, text=True, timeout=30)
        parts = (probe.stdout or "").strip().splitlines()[0].split(",")
        full_w, full_h = int(parts[0]), int(parts[1])
        nx0, ny0, nx1, ny1 = diamond
        cw = int((nx1 - nx0) * full_w)
        ch = int((ny1 - ny0) * full_h)
        x0 = int(nx0 * full_w)
        y0 = int(ny0 * full_h)
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", image_path,
                              "-vf", f"crop={cw}:{ch}:{x0}:{y0},scale={SCALE}:{SCALE}",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, timeout=60)
        data = out.stdout
        row_bytes = SCALE * 3
        # acc[r][c][bucket] = [sum_x, sum_y, n] in cell-local px (0..9)
        acc = [[{} for _ in range(GRID)] for _ in range(GRID)]
        for r in range(SCALE):
            row = data[r * row_bytes:(r + 1) * row_bytes]
            gr = min(GRID - 1, r // CELL)
            ly = r - gr * CELL
            for px in range(SCALE):
                if abs(px + 0.5 - SCALE / 2.0) + abs(r + 0.5 - SCALE / 2.0) > 0.48 * SCALE:
                    continue
                i = px * 3
                bk = bucket(row[i], row[i + 1], row[i + 2])
                if bk is None:
                    continue
                gc = min(GRID - 1, px // CELL)
                lx = px - gc * CELL
                ent = acc[gr][gc].get(bk)
                if ent is None:
                    acc[gr][gc][bk] = [lx, ly, 1]
                else:
                    ent[0] += lx
                    ent[1] += ly
                    ent[2] += 1
        out_grid = [[{} for _ in range(GRID)] for _ in range(GRID)]
        for r in range(GRID):
            for c in range(GRID):
                for bk, (sx, sy, n) in acc[r][c].items():
                    out_grid[r][c][bk] = ((sx / n + 0.5) / CELL,
                                          (sy / n + 0.5) / CELL, n)
        return out_grid
    except Exception:
        return None


def _aim_centroid(centroids, r: int, c: int, buckets=None):
    """(fx, fy) centroid of the given buckets' pixels in cell (r, c).

    centroids is the scan_centroids map (or None). buckets is a set
    of bucket names to include, or None for all coloured pixels.
    Returns None when there is no centroid data for the cell — the
    caller then aims at the cell centre, as before.
    """
    if centroids is None:
        return None
    try:
        cell = centroids[r][c]
    except (IndexError, TypeError):
        return None
    sx = sy = n = 0
    for bk, (fx, fy, cnt) in cell.items():
        if buckets is not None and bk not in buckets:
            continue
        sx += fx * cnt
        sy += fy * cnt
        n += cnt
    if n == 0:
        return None
    return (sx / n, sy / n)


# ---- v12 combat check: health bars in the main view ----

def _is_vivid_red(r: int, g: int, b: int):
    """True for a health bar's red: vivid, almost no green or blue.

    A real bar in frame 034 reads (164, 4, 6). Tilled farm soil reads
    (210, 145, 80) and thatch roofs (207, 51, 36) — both brown-red
    with far too much green to be a bar. The g < 40 bar is what
    separates them; r - g > 80 keeps pale pink UI out.
    """
    return r > 120 and g < 40 and b < 60 and r - g > 80


def _is_vivid_green(r: int, g: int, b: int):
    """True for a health bar's green: vivid, almost no red or blue.

    Same shape as _is_vivid_red, mirrored. No green bar appears in
    any run-25 frame, so this leg is unproven live — it is retained
    so a future battle that damages own units still counts.
    """
    return g > 140 and r < 70 and b < 70 and g - r > 80


def _count_bars(data, w: int, h: int, is_bar_colour):
    """Count health bars in raw RGB24 bytes (w x h).

    A bar is a SOLID run of bar-colour pixels COMBAT_BAR_MIN_RUN to
    COMBAT_BAR_MAX_RUN long on COMBAT_BAR_MIN_ROWS to
    COMBAT_BAR_MAX_ROWS consecutive rows, each row's run overlapping
    the bar's x-range by >= 60%. Solidity is the discriminator:
    a roof or a field row is textured (its runs break), a bar is one
    flat rectangle. Pure, so tests can call it on synthetic bytes.
    """
    # Per-row solid runs: [(x0, x1)] of length in range.
    row_runs = []
    for y in range(h):
        base = y * w * 3
        runs = []
        x = 0
        while x < w:
            i = base + x * 3
            if is_bar_colour(data[i], data[i + 1], data[i + 2]):
                x0 = x
                x += 1
                while x < w:
                    j = base + x * 3
                    if not is_bar_colour(data[j], data[j + 1], data[j + 2]):
                        break
                    x += 1
                if COMBAT_BAR_MIN_RUN <= x - x0 <= COMBAT_BAR_MAX_RUN:
                    runs.append((x0, x - 1))
            else:
                x += 1
        row_runs.append(runs)
    # Group runs across adjacent rows into bars.
    found = []
    active = []  # [x0, x1, y0, last_y, rows]
    for y, runs in enumerate(row_runs):
        nxt = []
        for (x0, x1) in runs:
            m = None
            for a in active:
                ov = min(x1, a[1]) - max(x0, a[0]) + 1
                if ov >= 0.6 * min(x1 - x0 + 1, a[1] - a[0] + 1):
                    m = a
                    break
            if m is None:
                nxt.append([x0, x1, y, y, 1])
            else:
                m[0] = min(m[0], x0)
                m[1] = max(m[1], x1)
                m[3] = y
                m[4] += 1
                nxt.append(m)
        for a in active:
            if a not in nxt and COMBAT_BAR_MIN_ROWS <= a[4] <= COMBAT_BAR_MAX_ROWS:
                found.append(a)
        active = nxt
    for a in active:
        if COMBAT_BAR_MIN_ROWS <= a[4] <= COMBAT_BAR_MAX_ROWS:
            found.append(a)
    return len(found)


def scan_combat_bars(image_path: str, view=COMBAT_VIEW):
    """(red_bars, green_bars) in the main view, or None on failure.

    Same ffmpeg pattern as scan_minimap: ffprobe for the size, crop
    the main view (fractions, so a retina 2880x1800 probe and a
    1440x900 frame read the same), scale the crop to
    COMBAT_VIEW_REF_W wide so bar geometry is in reference pixels
    whatever the source size, raw RGB24 out. The view excludes the
    top resource bar, the bottom score/minimap panel and the right
    score overlay, so UI colours never count as bars. None when the
    image cannot be read — fail closed: no evidence, never a confirm.
    Calibrated on the 19 run-25 frames (tests/fixtures/run25/):
    frame 034 -> (2, 0), every other frame -> (0, 0).
    """
    try:
        probe = subprocess.run(["ffprobe", "-v", "error",
                                "-select_streams", "v:0",
                                "-show_entries", "stream=width,height",
                                "-of", "csv=p=0", image_path],
                               capture_output=True, text=True, timeout=30)
        parts = (probe.stdout or "").strip().splitlines()[0].split(",")
        full_w, full_h = int(parts[0]), int(parts[1])
        nx0, ny0, nx1, ny1 = view
        cw = int((nx1 - nx0) * full_w)
        ch = int((ny1 - ny0) * full_h)
        x0 = int(nx0 * full_w)
        y0 = int(ny0 * full_h)
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", image_path,
                              "-vf", f"crop={cw}:{ch}:{x0}:{y0},"
                                     f"scale={COMBAT_VIEW_REF_W}:-1",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, timeout=60)
        data = out.stdout
        ref_w = COMBAT_VIEW_REF_W
        ref_h = len(data) // (ref_w * 3)
        if ref_h < 1 or len(data) < ref_w * 3:
            return None
        return (_count_bars(data, ref_w, ref_h, _is_vivid_red),
                _count_bars(data, ref_w, ref_h, _is_vivid_green))
    except Exception:
        return None


def _combat_evidence(bars, drop):
    """(gate, detail) for one scan's combat evidence.

    bars is scan_combat_bars()'s (red, green) or None (unreadable);
    drop is the Director's drop dict or None (no complete stamps to
    compare). gate: "health_bars" (either colour >= COMBAT_BARS_MIN),
    "military_drop" (a bucket or the total fell >= COMBAT_DROP_MIN),
    "health_bars+military_drop", or "none". detail carries the legs
    that fired (bars counts and/or the drop) for the debug record.
    A lone bar is not evidence (one damaged building keeps its bar
    long after combat ends); a failed bars read is unknown, not zero
    — it contributes no evidence and the detail says so, so the
    holder can tell "scan failed" from "scan found nothing".
    """
    detail = {"bars": bars, "bars_known": bars is not None, "drop": drop}
    bars_hit = bars is not None and (bars[0] >= COMBAT_BARS_MIN
                                     or bars[1] >= COMBAT_BARS_MIN)
    drop_hit = (drop is not None
                and (drop.get("drop", 0) >= COMBAT_DROP_MIN
                     or drop.get("total_drop", 0) >= COMBAT_DROP_MIN))
    if bars_hit and drop_hit:
        return "health_bars+military_drop", detail
    if bars_hit:
        return "health_bars", detail
    if drop_hit:
        return "military_drop", detail
    return "none", detail


def parse_game_clock(text: str):
    """Parse an OCR clock string -> total seconds, or None.

    Accepts "00:49:40" and "49:40". Returns None for anything else —
    never invent a time from a failed OCR read. (Same parser as the
    helper's clock check; duplicated here so the director stays
    self-contained for the phase-gate fallback.)
    """
    m = re.search(r"(\d+):(\d+):(\d+)", text or "")
    if m:
        h, mi, s = (int(v) for v in m.groups())
        return h * 3600 + mi * 60 + s
    m = re.search(r"(\d+):(\d+)", text or "")
    if m:
        mi, s = (int(v) for v in m.groups())
        return mi * 60 + s
    return None


def _ocr_digits(crop_path: str):
    """One cropped number cell -> int, or None.

    tesseract --psm 7 (single line) with a digit whitelist, then an
    inverted second pass (the panel's highlighted row is white-on-tan
    while the others are dark-on-tan; the clock OCR needed the same
    two-pass shape on white-on-dark text). Mirrors the helper's
    clock OCR, which is proven live on this game's font.
    """
    if shutil.which("tesseract") is None:
        return None
    try:
        out = subprocess.run(["tesseract", crop_path, "stdout", "--psm", "7",
                              "-c", "tessedit_char_whitelist=0123456789"],
                             capture_output=True, text=True, timeout=30)
        m = re.search(r"\d+", out.stdout or "")
        if m:
            return int(m.group(0))
        # Second pass: inverted, so a white digit on tan reads too.
        inv = crop_path + ".inv.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", crop_path,
                        "-vf", "format=gray,negate", inv],
                       capture_output=True, timeout=30)
        out2 = subprocess.run(["tesseract", inv, "stdout", "--psm", "7",
                               "-c", "tessedit_char_whitelist=0123456789"],
                              capture_output=True, text=True, timeout=30)
        m2 = re.search(r"\d+", out2.stdout or "")
        if m2:
            return int(m2.group(0))
    except Exception:
        return None
    return None


def read_game_clock_secs(image_path: str):
    """Game clock in seconds from a probe screenshot, or None.

    Same crop as the helper's clock check (x 38-62%, y 0-6%, 3x
    scale, two tesseract passes) but operating on an existing image
    file instead of taking a new screenshot. Used only for the v7
    phase-gate fallback, when the military panel cannot be read.
    """
    if shutil.which("tesseract") is None:
        return None
    try:
        tmp = tempfile.mkdtemp(prefix="aoe2_director_clock_")
        crop = os.path.join(tmp, "clock.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", image_path,
                        "-vf", "crop=iw*0.24:ih*0.06:iw*0.38:0,scale=iw*3:ih*3,format=gray",
                        crop], check=True, timeout=30)
        out = subprocess.run(["tesseract", crop, "stdout", "--psm", "7"],
                             capture_output=True, text=True, timeout=30)
        secs = parse_game_clock(out.stdout)
        if secs is not None:
            return secs
        out_b = subprocess.run(["tesseract", crop, "stdout", "--psm", "6"],
                               capture_output=True, text=True, timeout=30)
        secs = parse_game_clock(out_b.stdout)
        if secs is not None:
            return secs
        inv = os.path.join(tmp, "clock_inv.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", image_path,
                        "-vf", "crop=iw*0.24:ih*0.06:iw*0.38:0,scale=iw*3:ih*3,format=gray,negate",
                        inv], check=True, timeout=30)
        out2 = subprocess.run(["tesseract", inv, "stdout", "--psm", "7",
                               "-c", "tessedit_char_whitelist=0123456789:"],
                              capture_output=True, text=True, timeout=30)
        return parse_game_clock(out2.stdout)
    except Exception:
        return None


def _panel_row_centres(full_h: int, panel_rows: int = PANEL_ROWS):
    """Player-row centres in pixels for an image of height full_h."""
    return [int(round((PANEL_ROW_Y0 + i * PANEL_ROW_PITCH) * full_h))
            for i in range(panel_rows)]


def _tesseract_words(image_path: str, psm: str = "6"):
    """OCR word boxes from one image -> [(text, x, y, conf)], or [].

    tesseract TSV output, --psm 6 (uniform block of text: the strip
    is a little table, not one line) with a digit whitelist. Only
    words containing a digit are returned; coordinates are the word
    box centres in the image's own pixels. Never raises: any
    failure (tesseract missing, bad image, timeout) is an empty
    list, and the caller falls back to the next read in the chain.
    """
    if shutil.which("tesseract") is None:
        return []
    try:
        out = subprocess.run(
            ["tesseract", image_path, "stdout", "--psm", psm, "tsv",
             "-c", "tessedit_char_whitelist=0123456789"],
            capture_output=True, text=True, timeout=30)
        words = []
        for line in (out.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) < 12 or parts[0] != "5":
                continue  # level 5 = word; skip header/blocks/lines
            try:
                left, top = int(parts[6]), int(parts[7])
                width, height = int(parts[8]), int(parts[9])
                conf = float(parts[10])
            except ValueError:
                continue
            text = parts[11].strip()
            if not text or not any(ch.isdigit() for ch in text):
                continue
            words.append((text, left + width / 2.0, top + height / 2.0,
                          conf))
        return words
    except Exception:
        return []


def _assign_words_to_rows(words, row_centres, pitch_px, mil_x_range,
                          scale, strip_y0):
    """Word boxes -> {row_index: int} for the Military column.

    words: (text, x_centre, y_centre, conf) in scaled strip pixels.
    Only words that are PURE digits and whose x-centre falls inside
    the Military column (mil_x_range, in scaled strip pixels) are
    considered — names, headers and the other two number columns
    are excluded by the x filter, and a word like '51I' is rejected
    rather than guessed. Each word goes to the nearest row centre
    within 0.45 of the row pitch; on a conflict (two words, one
    row) the higher-confidence word wins. A row with no word stays
    missing — never guessed, never zero.
    """
    assigned = {}
    for text, xc, yc, conf in words:
        if not text.isdigit():
            continue
        if not (mil_x_range[0] <= xc <= mil_x_range[1]):
            continue
        best, bestd = None, None
        for i, yc_row in enumerate(row_centres):
            cy = (yc_row - strip_y0) * scale
            dd = abs(yc - cy)
            if bestd is None or dd < bestd:
                bestd, best = dd, i
        if best is None or bestd > 0.45 * pitch_px * scale:
            continue
        prev = assigned.get(best)
        if prev is None or conf > prev[1]:
            assigned[best] = (int(text), conf)
    return {i: v for i, (v, _c) in assigned.items()}


def _read_swatches(image_path: str, full_w: int, full_h: int,
                   row_centres, panel_rows: int = PANEL_ROWS):
    """Colour swatch per player row -> [bucket or None] x panel_rows.

    One ffmpeg crop of the swatch strip; the mode bucket of each
    row's lower-half window (centre+1 to centre+5 — the upper half
    catches the previous row's swatch, rows are only 12 px apart).
    Pure pixels, no OCR: this half of the read is proven (12/12
    run-20 frames). Returns None on any failure.
    """
    swatches = [None] * panel_rows
    try:
        sx0 = int(PANEL_SWATCH_X0 * full_w)
        sx1 = int(PANEL_SWATCH_X1 * full_w)
        sy0 = row_centres[0] - 6
        sy1 = row_centres[-1] + 6
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", image_path,
                              "-vf", f"crop={sx1 - sx0}:{sy1 - sy0}:{sx0}:{sy0}",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, timeout=30)
        data = out.stdout
        sw = sx1 - sx0
        for i, yc in enumerate(row_centres):
            y_lo = (yc + 1) - sy0
            y_hi = (yc + 5) - sy0
            counts = {}
            for yy in range(max(0, y_lo), min(sy1 - sy0, y_hi + 1)):
                base = yy * sw * 3
                for xx in range(sw):
                    j = base + xx * 3
                    bk = bucket(data[j], data[j + 1], data[j + 2])
                    if bk is not None:
                        counts[bk] = counts.get(bk, 0) + 1
            if counts:
                swatches[i] = max(counts.items(), key=lambda kv: kv[1])[0]
    except Exception:
        return None
    return swatches


def _read_panel_strip(image_path: str, full_w: int, full_h: int,
                      row_centres, scale: int, word_reader=None):
    """One wide-strip read -> {row_index: int}.

    Crops the panel strip (Total Score + Military + Economy
    columns, extended past the first/last row so no edge row sits
    on the crop boundary), scales it, OCRs it as a text block and
    assigns the Military-column words to rows by the known row
    geometry. word_reader is (png_path, psm) -> [(text, x, y,
    conf)]; the default is _tesseract_words. Never raises: any
    failure is an empty dict.
    """
    try:
        tmp = tempfile.mkdtemp(prefix="aoe2_director_strip_")
        wx0 = int(PANEL_WIDE_X0 * full_w)
        wx1 = int(PANEL_WIDE_X1 * full_w)
        y0 = max(0, row_centres[0] - 6 - PANEL_STRIP_EXTEND_PX)
        y1 = min(full_h, row_centres[-1] + 7 + PANEL_STRIP_EXTEND_PX)
        strip = os.path.join(tmp, "strip_%d.png" % scale)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", image_path,
                        "-vf", f"crop={wx1 - wx0}:{y1 - y0}:{wx0}:{y0},"
                               f"scale=iw*{scale}:ih*{scale}",
                        strip], check=True, timeout=30)
        reader = word_reader or _tesseract_words
        words = reader(strip, "6")
        pitch_px = int(round(PANEL_ROW_PITCH * full_h))
        mx0 = int(PANEL_MIL_X0 * full_w) - wx0
        mx1 = int(PANEL_MIL_X1 * full_w) - wx0
        mil = (mx0 * scale, mx1 * scale)
        return _assign_words_to_rows(words, row_centres, pitch_px,
                                     mil, scale, y0)
    except Exception:
        return {}


def _read_panel_row_padded(image_path: str, full_w: int, full_h: int,
                           row_index: int, row_centres):
    """Last-resort read for one missing row -> int or None.

    The v7 per-row crop (one 34x13 px cell, 4x) reads NOTHING on
    real frames: an OCR engine cannot segment a margin-less
    sliver. The same crop pasted on a 2x white canvas DOES read
    (run-20 frames: 5/6 rows on the all-non-zero frame). So the
    fallback keeps the per-row crop but gives it margins. Uses
    the corrected row centre. Only ever fills a row the strips
    missed; never overrides a strip value.
    """
    try:
        tmp = tempfile.mkdtemp(prefix="aoe2_director_row_")
        mx0 = int(PANEL_MIL_X0 * full_w)
        mx1 = int(PANEL_MIL_X1 * full_w)
        yc = row_centres[row_index]
        y0 = max(0, yc - 6)
        y1 = min(full_h, yc + 7)
        crop = os.path.join(tmp, "row.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", image_path,
                        "-vf", f"crop={mx1 - mx0}:{y1 - y0}:{mx0}:{y0},"
                               f"scale=iw*4:ih*4",
                        crop], check=True, timeout=30)
        # Margins: paste the 4x crop centred on a 2x white canvas.
        padded = os.path.join(tmp, "row_padded.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", crop,
                        "-vf", "pad=iw*2:ih*2:(ow-iw)/2:(oh-ih)/2:white",
                        padded], check=True, timeout=30)
        return _ocr_digits(padded)
    except Exception:
        return None


def read_military_scores(image_path: str, word_reader=None, panel_rows: int = PANEL_ROWS):
    """Per-player Military scores from the score panel, or None.

    Returns ({bucket: military}, complete) where complete is True
    when all panel_rows rows read. The panel is a fixed layout
    (measured on 12 real run-20 frames): each row has a colour
    swatch (read from the image pixels, same bucket() as the
    minimap) and a Military number.
    Row order is the scoreboard order, top to bottom:
    polololiconte (red), Jonex2677 (yellow), Drake (purple),
    Rick (blue), Ken (green), Dr. Pork (cyan) — the swatch,
    not the order, is what maps a row to a bucket, so a
    reordered panel still reads correctly.
    v8 read chain (run 20 lesson: the v7 per-row tesseract read
    NEVER produced a live reading, 0 of 27 steps, because a
    34x13 px crop holds one ~8 px glyph plus slivers of the rows
    above and below, with no margins for an OCR engine to find a
    text line in — the same crops read 0/24 rows under RapidOCR,
    while the same digits pasted on a white canvas read 14/24,
    and the v7 row geometry was ~4 px too high on top of that):
    1. Wide strip at 4x AND at 6x — the whole panel strip (Total
       Score + Military + Economy) as one text block, Military
       words assigned to rows by the known row geometry. Both
       scales always run, and they cross-check each other: a row
       both scales agree on is trusted, a row only one scale
       reads is taken as-is, but a row the scales DISAGREE on is
       distrusted — on the run-20 frames the 4x strip misreads
       cyan's '119' as '611' (frames 33/34) while the 6x strip
       reads it right, and no resampling flag fixes both frames,
       so a disagreement means the glyphs are ambiguous and
       neither scale may be trusted alone.
    2. Padded per-row crops — for rows the strips disagree on or
       never read. A disputed row is adopted only when this
       independent read matches one of the two strip values;
       a never-read row takes whatever it returns.
    A row no pass resolves stays missing, never guessed: an
    unread row is unknown, not zero — and a WRONG value is worse
    than a missing one (a fake military drop reads as units
    dying, i.e. a phantom fight). Returns None when the image is
    unreadable or fewer than min_scores rows read — the caller uses
    the clock phase gate instead of trusting a partial panel.
    The tesseract-missing check applies only to the default
    reader: an injected word_reader (tests) is used as-is.
    On the 12 run-20 frames this chain reads 68 of 72 rows, all
    correct, 9 of 12 frames complete (RapidOCR proxy; tesseract
    itself is not installable in the test VM, so the padded
    fallback cannot adjudicate there — on the Mac it may recover
    the two disputed rows and the two never-read rows, for up to
    72/72. The live run is still the final proof — see run 21).
    """
    if word_reader is None and shutil.which("tesseract") is None:
        return None
    try:
        probe = subprocess.run(["ffprobe", "-v", "error",
                                "-select_streams", "v:0",
                                "-show_entries", "stream=width,height",
                                "-of", "csv=p=0", image_path],
                               capture_output=True, text=True, timeout=30)
        parts = (probe.stdout or "").strip().splitlines()[0].split(",")
        full_w, full_h = int(parts[0]), int(parts[1])
    except Exception:
        return None
    row_centres = _panel_row_centres(full_h, panel_rows=panel_rows)
    swatches = _read_swatches(image_path, full_w, full_h, row_centres, panel_rows=panel_rows)
    if swatches is None:
        return None
    strips = {}
    for scale in PANEL_STRIP_SCALES:
        strips[scale] = _read_panel_strip(image_path, full_w, full_h,
                                          row_centres, scale, word_reader)
    rows = {}
    disputed = {}
    for i in range(panel_rows):
        v4 = strips[PANEL_STRIP_SCALES[0]].get(i)
        v6 = strips[PANEL_STRIP_SCALES[1]].get(i)
        if v4 is not None and v6 is not None:
            if v4 == v6:
                rows[i] = v4
            else:
                disputed[i] = (v4, v6)
        elif v4 is not None:
            rows[i] = v4
        elif v6 is not None:
            rows[i] = v6
    # Adjudicate disputed rows and fill never-read rows with the
    # padded per-row read. A disputed row is adopted only when
    # the independent read matches one of the two strip values;
    # otherwise it stays unknown — a wrong value would fake a
    # military drop and a phantom fight, while a missing row is
    # simply unknown.
    for i in range(panel_rows):
        if i in rows or swatches[i] is None:
            continue
        val = _read_panel_row_padded(image_path, full_w, full_h,
                                     i, row_centres)
        if val is None:
            continue
        if i in disputed:
            if val in disputed[i]:
                rows[i] = val
        else:
            rows[i] = val
    scores = {}
    for i, val in rows.items():
        if swatches[i] is not None:
            scores[swatches[i]] = val
    min_scores = 2 if panel_rows <= 2 else (3 if panel_rows == 4 else 4)
    if len(scores) < min_scores:
        return None
    return scores, len(scores) == panel_rows


DEFAULT_TEAM_PATTERNS = {
    "Ken": ["ken", "grabsha", "grab"],
    "Rick": ["rick", "trick"],
    "Pork": ["pork", "dr."],
}


def detect_team_colors(image_path: str, team_patterns: dict | None = None) -> dict[str, str]:
    """Auto-detect team player colors by scanning player names and shield swatches.

    In AoE2 DE, player names appear in the score/player overlay on the right
    side of the screen (x >= 1180, y >= 550 on 1440x900). Each player row
    has a colored shield icon directly to the left (x ~ 1218..1240 on 1440x900).

    Returns a dict mapping player name ('Ken', 'Rick', 'Pork') to their detected
    minimap bucket color ('green', 'blue', 'cyan', etc.).
    """
    if not image_path or not os.path.exists(image_path):
        return {}
    if shutil.which("tesseract") is None:
        return {}
    patterns = team_patterns or DEFAULT_TEAM_PATTERNS
    try:
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                "-show_entries", "stream=width,height", "-of", "csv=p=0",
                                image_path],
                               capture_output=True, text=True, timeout=30)
        parts = (probe.stdout or "").strip().splitlines()[0].split(",")
        full_w, full_h = int(parts[0]), int(parts[1])

        out = subprocess.run(["tesseract", image_path, "stdout", "--psm", "11", "tsv"],
                             capture_output=True, timeout=30)
        player_rows = {}
        for line in out.stdout.decode("utf-8", errors="replace").splitlines():
            cols = line.split("\t")
            if len(cols) >= 12 and cols[0] == "5" and cols[11].strip():
                word = cols[11].strip().lower()
                left = int(cols[6])
                top = int(cols[7])
                height = int(cols[9])
                nl = left * 1440 // full_w
                nt = top * 900 // full_h
                if 1180 <= nl <= 1400 and 550 <= nt <= 850:
                    for player, pats in patterns.items():
                        if any(pat in word for pat in pats):
                            player_rows.setdefault(player, []).append(top + height / 2.0)

        if not player_rows:
            return {}

        sx0 = int(1218 * full_w / 1440)
        sx1 = int(1240 * full_w / 1440)
        sw = sx1 - sx0

        sy0 = int(550 * full_h / 900)
        sy1 = int(850 * full_h / 900)
        sh = sy1 - sy0

        crop = subprocess.run(["ffmpeg", "-v", "error", "-i", image_path,
                               "-vf", f"crop={sw}:{sh}:{sx0}:{sy0}",
                               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                              capture_output=True, timeout=30)
        raw = crop.stdout
        if len(raw) < sw * sh * 3:
            return {}

        team_colors = {}
        for player, y_list in player_rows.items():
            avg_y = int(round(sum(y_list) / len(y_list)))
            rel_y = avg_y - sy0
            counts = {}
            for dy in range(-4, 5):
                yy = rel_y + dy
                if 0 <= yy < sh:
                    row_off = yy * sw * 3
                    for xx in range(sw):
                        idx = row_off + xx * 3
                        bk = bucket(raw[idx], raw[idx + 1], raw[idx + 2])
                        if bk:
                            counts[bk] = counts.get(bk, 0) + 1
            if counts:
                team_colors[player] = max(counts.items(), key=lambda kv: kv[1])[0]
        return team_colors
    except Exception:
        return {}


def inspect_spectator_scoreboard(screenshot_path: str, ocr: bool = True) -> dict:
    """Inspect the in-game spectator scoreboard at replay start.

    Scans the bottom-left spectator panel swatch strip (x=228..242, y=795+i*12)
    to dynamically determine active player count (2 for 1v1, 4 for 2v2, 6 for 3v3,
    8 for 4v4) by bucket sampling contiguous player color swatches.

    When ocr is True, extracts player names from the bottom-left panel and the
    right-side overlay, matching Ken Grabshaw and teammates against
    DEFAULT_TEAM_PATTERNS to dynamically establish focus_colours without
    requiring manual command-line flags.

    Returns dict with keys:
      player_count: int (2, 4, 6, 8)
      players: list of {"row": int, "color": str, "name": str}
      focus_colours: set of str
    """
    if not screenshot_path or not os.path.exists(screenshot_path):
        return {"player_count": PANEL_ROWS, "players": [], "focus_colours": set()}

    full_w, full_h = None, None
    try:
        from PIL import Image
        im = Image.open(screenshot_path)
        full_w, full_h = im.size
    except Exception:
        im = None

    if full_w is None:
        try:
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                    "-show_entries", "stream=width,height", "-of", "csv=p=0",
                                    screenshot_path],
                                   capture_output=True, text=True, timeout=30)
            parts = (probe.stdout or "").strip().splitlines()[0].split(",")
            full_w, full_h = int(parts[0]), int(parts[1])
        except Exception:
            return {"player_count": PANEL_ROWS, "players": [], "focus_colours": set()}

    if full_w < 200 or full_h < 200:
        return {"player_count": PANEL_ROWS, "players": [], "focus_colours": set()}

    row_centres = [int(round((PANEL_ROW_Y0 + i * PANEL_ROW_PITCH) * full_h)) for i in range(8)]
    pitch = int(round(PANEL_ROW_PITCH * full_h))
    sx0 = int(PANEL_SWATCH_X0 * full_w)
    sx1 = int(PANEL_SWATCH_X1 * full_w)

    # 1. Bottom-left spectator panel swatch strip scanning
    swatches = []
    if im is not None:
        for i in range(8):
            yc = row_centres[i]
            counts = {}
            for yy in range(yc + 1, yc + 6):
                for xx in range(sx0, sx1):
                    if 0 <= xx < full_w and 0 <= yy < full_h:
                        bk = bucket(*im.getpixel((xx, yy))[:3])
                        if bk is not None:
                            counts[bk] = counts.get(bk, 0) + 1
            if counts and max(counts.values()) >= 8:
                swatches.append((i, max(counts.items(), key=lambda kv: kv[1])[0]))
            else:
                break
    else:
        try:
            sy0 = row_centres[0] - 6
            sy1 = row_centres[7] + 6
            out = subprocess.run(["ffmpeg", "-v", "error", "-i", screenshot_path,
                                  "-vf", f"crop={sx1 - sx0}:{sy1 - sy0}:{sx0}:{sy0}",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                 capture_output=True, timeout=30)
            data = out.stdout
            sw = sx1 - sx0
            for i in range(8):
                yc = row_centres[i]
                y_lo = (yc + 1) - sy0
                y_hi = (yc + 5) - sy0
                counts = {}
                for yy in range(max(0, y_lo), min(sy1 - sy0, y_hi + 1)):
                    base = yy * sw * 3
                    for xx in range(sw):
                        j = base + xx * 3
                        bk = bucket(data[j], data[j + 1], data[j + 2])
                        if bk is not None:
                            counts[bk] = counts.get(bk, 0) + 1
                if counts and max(counts.values()) >= 8:
                    swatches.append((i, max(counts.items(), key=lambda kv: kv[1])[0]))
                else:
                    break
        except Exception:
            pass

    count = len(swatches)
    if count >= 8:
        player_count = 8
    elif count >= 6:
        player_count = 6
    elif count >= 4:
        player_count = 4
    elif count >= 2:
        player_count = 2
    else:
        player_count = count if count > 0 else PANEL_ROWS

    swatches = swatches[:player_count]
    swatch_map = dict(swatches)

    # 2. Player name detection & team pattern matching
    row_names = {i: "" for i in range(player_count)}
    matched_patterns = {}  # persona -> row_idx
    focus_colours = set()

    if ocr and shutil.which("tesseract"):
        x0 = int(0.15 * full_w)
        x1 = int(0.32 * full_w)
        y0 = max(0, row_centres[0] - pitch)
        y1 = min(full_h, row_centres[min(player_count - 1, 7)] + pitch)

        crop_path = os.path.join(tempfile.gettempdir(), f"aoe2_sb_panel_{os.getpid()}.png")
        try:
            if im is not None:
                crop_im = im.crop((x0, y0, x1, y1))
                crop_im.save(crop_path)
            else:
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", screenshot_path,
                                "-vf", f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0}", crop_path],
                               check=True, timeout=30)

            for psm in ("6", "11"):
                out = subprocess.run(["tesseract", crop_path, "stdout", "--psm", psm, "tsv"],
                                     capture_output=True, text=True, timeout=30)
                for line in out.stdout.splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 12 and parts[0] == "5" and parts[11].strip():
                        text = parts[11].strip()
                        top = int(parts[7])
                        height = int(parts[9])
                        ymid = y0 + top + height / 2.0
                        closest_row = min(range(player_count), key=lambda r: abs(ymid - row_centres[r]))
                        if abs(ymid - row_centres[closest_row]) <= pitch * 0.75:
                            if not row_names[closest_row]:
                                row_names[closest_row] = text
                            else:
                                if text not in row_names[closest_row]:
                                    row_names[closest_row] += " " + text
        except Exception:
            pass
        finally:
            try:
                os.unlink(crop_path)
            except OSError:
                pass

        for r, name in row_names.items():
            lower = name.lower()
            for pkey, pats in DEFAULT_TEAM_PATTERNS.items():
                if any(pat in lower for pat in pats):
                    matched_patterns[pkey] = r

        # Right-side overlay fallback / cross-check
        if len(matched_patterns) < 2:
            try:
                out_right = subprocess.run(["tesseract", screenshot_path, "stdout", "--psm", "11", "tsv"],
                                           capture_output=True, text=True, timeout=30)
                for line in out_right.stdout.splitlines():
                    cols = line.split("\t")
                    if len(cols) >= 12 and cols[0] == "5" and cols[11].strip():
                        word = cols[11].strip().lower()
                        left = int(cols[6])
                        top = int(cols[7])
                        height = int(cols[9])
                        nl = left * 1440 // full_w
                        nt = top * 900 // full_h
                        if 1180 <= nl <= 1400 and 550 <= nt <= 850:
                            for pkey, pats in DEFAULT_TEAM_PATTERNS.items():
                                if pkey not in matched_patterns and any(pat in word for pat in pats):
                                    ymid = top + height / 2.0
                                    sx0_r = int(1218 * full_w / 1440)
                                    sx1_r = int(1240 * full_w / 1440)
                                    counts = {}
                                    if im is not None:
                                        for dy in range(-4, 5):
                                            yy = int(round(ymid)) + dy
                                            for xx in range(sx0_r, sx1_r):
                                                if 0 <= xx < full_w and 0 <= yy < full_h:
                                                    bk = bucket(*im.getpixel((xx, yy))[:3])
                                                    if bk:
                                                        counts[bk] = counts.get(bk, 0) + 1
                                    if counts:
                                        color = max(counts.items(), key=lambda kv: kv[1])[0]
                                        for r, c in swatches:
                                            if c == color:
                                                matched_patterns[pkey] = r
                                                break
            except Exception:
                pass

    focus_rows = set()
    for pkey, r in matched_patterns.items():
        focus_rows.add(r)

    # In team games, players in the same half of scoreboard are teammates
    if player_count >= 4 and focus_rows:
        team_size = player_count // 2
        for r in list(focus_rows):
            team_idx = r // team_size
            for tr in range(team_idx * team_size, (team_idx + 1) * team_size):
                focus_rows.add(tr)

    for r in focus_rows:
        if r in swatch_map:
            focus_colours.add(swatch_map[r])

    players_list = []
    for r, color in swatches:
        name_str = row_names.get(r, "")
        for pkey, p_row in matched_patterns.items():
            if p_row == r:
                name_str = f"{pkey} ({name_str})" if name_str else pkey
                break
        players_list.append({
            "row": r,
            "color": color,
            "name": name_str
        })

    return {
        "player_count": player_count,
        "players": players_list,
        "focus_colours": focus_colours
    }


class MilitaryTracker:
    """Per-bucket military scores across scans (v7).

    A falling military score means units are dying: a fight is
    happening now, involving those players. The director uses this
    to (a) suppress all fight labels while every military is 0 —
    the whole early game, where motion alone invented fights out
    of villagers — and (b) rank fight candidates whose players are
    losing military above higher-motion eco cells.
    Unknown is never treated as zero: a bucket absent from a read
    keeps its last known value for the loss comparison, and the
    total-zero gate requires a COMPLETE read (all panel_rows rows) with
    every score 0.
    """

    def __init__(self, panel_rows: int = PANEL_ROWS):
        self.panel_rows = panel_rows
        self.prev = None     # (scores, complete) or None
        self.current = None  # (scores, complete) or None

    def update(self, read):
        """Feed a read_military_scores() result (or None) -> state dict.

        State: known, complete, total, total_zero, losing
        {bucket: drop}, scores {bucket: military}.
        """
        self.prev = self.current
        self.current = read
        return self.state()

    def state(self):
        if self.current is None:
            return {"known": False, "complete": False, "total": 0,
                    "total_zero": False, "losing": {}, "scores": {}}
        scores, complete = self.current
        total = sum(scores.values())
        losing = {}
        if self.prev is not None:
            prev_scores, _ = self.prev
            for bk, cur in scores.items():
                if bk in prev_scores and cur < prev_scores[bk]:
                    losing[bk] = prev_scores[bk] - cur
        return {"known": True, "complete": complete, "total": total,
                "total_zero": bool(complete and total == 0),
                "losing": losing, "scores": dict(scores)}


def _military_log(state):
    """Compact military state for a decision's debug record.

    Only the facts the log needs to explain a fight decision:
    total military, whether every score is 0, and which buckets
    are losing military (with the drop). Unknown state logs as
    {"known": False} — the reader is told the signal was absent,
    not that military was zero.
    """
    if not state.get("known"):
        return {"known": False}
    out = {"total": state.get("total", 0),
           "total_zero": bool(state.get("total_zero"))}
    if state.get("losing"):
        out["losing"] = dict(state["losing"])
    return out


def _bar(base_px, dt_s):
    """A pixel-change bar scaled to the actual scan gap.

    Bars are calibrated at MOTION_BASE_DT_S (60s): a base drifts
    ~5 px per 60s scan, a fight 8-21 px. Sample twice as fast
    and both numbers roughly halve, so an absolute bar would
    either miss real fights (fast sampling) or admit bases (slow
    sampling). Scaling by dt / 60 keeps the same fight/base
    separation at any cadence. The 4 px floor (v10, run 22 lesson)
    stops stream noise alone counting as movement at very short
    gaps: run 22 step 3 fired on a gold pile whose opposite-bucket
    delta was only 3, because the old 3 px floor let the pile's
    ~3 px minimap jitter through on a short scan gap. dt <= 0 or
    missing means "unknown", treated as the reference interval.
    """
    if dt_s is None or dt_s <= 0:
        dt_s = MOTION_BASE_DT_S
    return max(4.0, base_px * dt_s / MOTION_BASE_DT_S)


def _cell_delta(cell, prev_cell):
    """Bucket-count change between two scans of one cell.

    0 with no baseline. The same metric FIGHT_MOVE_MIN uses at
    fight entry and the static demotion uses on holds.
    """
    if prev_cell is None:
        return 0
    return sum(abs(cell.get(bk, 0) - prev_cell.get(bk, 0))
               for bk in set(cell) | set(prev_cell))


def _dominant(cell):
    """(bucket, count) of the dominant colour, or None.

    A base cell on a real minimap is never single-colour (see the
    slot-fix lesson): dominance is one bucket with at least
    BASE_MIN_PIXELS and at least BASE_DOMINANT_SHARE of the cell
    total. Returns None for thin, empty and balanced cells.
    """
    total = sum(cell.values())
    if total < BASE_MIN_PIXELS:
        return None
    bk, n = max(cell.items(), key=lambda kv: kv[1])
    if n >= BASE_MIN_PIXELS and n / total >= BASE_DOMINANT_SHARE:
        return bk, n
    return None


def _is_live_fight_mix(cell):
    """True when a cell currently holds a balanced fight mix.

    Second bucket >= FIGHT_MIN_SECOND_PIXELS AND >=
    FIGHT_MIN_SECOND_SHARE of the total — the same balance bar
    _fight_status uses. A dominant cell with only traces of a
    second colour (a base with a passing army, or a fight already
    won) is NOT a live fight mix: the camera may visit it as a
    base. This is the discriminator between the run-18 (4,4)
    replay — green 73 / yellow 21 at the slot step, second share
    22% < 25%, a base the slot legitimately checks while the hold
    resumes after — and the dynamic-hold fight cell red 58 /
    yellow 37, second share 39%, a live fight the slot must never
    "check" as a base.
    """
    total = sum(cell.values())
    if total < FIGHT_MIN_PIXELS or len(cell) < FIGHT_MIN_BUCKETS:
        return False
    second = sorted(cell.values(), reverse=True)[1]
    return (second >= FIGHT_MIN_SECOND_PIXELS
            and second / total >= FIGHT_MIN_SECOND_SHARE)


def _is_hot_fight_mix(cell, prev_cell, dt_s=60.0):
    """True when a cell is a balanced fight mix that is STILL MOVING.

    The slot's discriminator: a live fight mix that has gone quiet
    (delta below the scaled MOTION_MIN) is a base with a passing
    army or a fight already won — the static demotion treats it the
    same way — so the slot may check it as a base. A live mix that
    is still churning is a battle, and the slot must never label it
    a base check. The balance bar alone is too fragile at the
    boundary (run-18 (4,4) at 15s sampling: green 73 / yellow 25,
    second share 25.5%, is a base; the dynamic-hold cell red 58 /
    yellow 37, 39%, is a fight — 0.5% apart on share, but 2 px vs
    26 px on motion). Unknown motion (no previous scan) fails
    closed: a live mix counts as hot.
    """
    if not _is_live_fight_mix(cell):
        return False
    if prev_cell is None:
        return True
    return _cell_delta(cell, prev_cell) >= _bar(MOTION_MIN, dt_s)


def _is_raid(cell, focus_colours, military=None):
    """True when a cell holds a real focus presence plus at least
    ATTENTION_MIN_OPP_PIXELS of an opponent colour: a raid.

    Unmapped focus has no opponents, so never a raid. A raid is
    a first-class focus fight even below the 15 px fight bar — a
    few knights hitting villagers may never reach 15 px of the
    second colour in one cell, yet a raid is exactly what a
    review needs to see (raid defence, villager losses). It still
    must have MOVED (the static check in _fight_status applies
    first): a stale mixed cell is not a raid.

    v7 military gate: when military is known, the raiding
    (opponent) colour must actually have military — a raid with
    no army is impossible — and no raid exists at all while every
    military is 0. Unknown military never blocks (v6 behaviour).
    """
    if focus_colours is None:
        return False
    if military is not None and military.get("total_zero"):
        return False
    focus_px = sum(n for bk, n in cell.items() if bk in focus_colours)
    opp = [(bk, n) for bk, n in cell.items() if bk not in focus_colours]
    if not opp:
        return False
    opp_bk, opp_px = max(opp, key=lambda kv: kv[1])
    if military is not None and military.get("known"):
        scores = military.get("scores", {})
        # A known-zero raider cannot be raiding; an unread raider
        # is unknown, not zero, so it still counts.
        if opp_bk in scores and scores[opp_bk] <= 0:
            return False
    # v16: a raid requires a real focus base/eco presence (>= BASE_MIN_PIXELS, 15px),
    # not a lone scouting unit (6-14px) riding through enemy territory.
    # A raid is enemy attacking a focus base, not a focus scout passing an enemy army.
    return (focus_px >= BASE_MIN_PIXELS
            and opp_px >= ATTENTION_MIN_OPP_PIXELS)


def _fight_status(cell, prev_cell, excluded, focus_colours=None, dt_s=60.0,
                   military=None):
    """Rejection reason for one cell as a fight, or None if clean.

    Reasons: "thin" (too few buckets/pixels), "baseline" (no
    previous scan — the first scan only establishes the baseline),
    "no_military" (v7: military is known and no bucket in this cell
    has any — a clash needs an army; villagers and scouts are not
    a fight), "static" (moved less than the scaled FIGHT_MOVE_MIN),
    "repeat" (this cell already won as a fight this run — v3
    never-again rule), "unbalanced" (a dominant colour plus
    traces, not a clash — unless it is a raid: a real focus
    presence plus >= 6 px of an opponent colour, which counts as
    a fight even below the balance bars).
    Unknown military (None) never rejects: v6 behaviour.
    """
    total = sum(cell.values())
    if len(cell) < FIGHT_MIN_BUCKETS or total < FIGHT_MIN_PIXELS:
        return "thin"
    if prev_cell is None:
        return "baseline"
    if military is not None and military.get("known"):
        # total_zero is the all-players-zero case — including the
        # phase gate, which carries no per-bucket scores (it stands
        # in for "every military is 0" while the panel is unreadable
        # and the game is early). No fight can exist while every
        # military is 0, whatever the mix looks like.
        if military.get("total_zero"):
            return "no_military"
        scores = military.get("scores", {})
        # Blocked only when EVERY bucket in the cell is KNOWN to
        # have zero military. An unread bucket is unknown, not
        # zero, so it never blocks. total_zero is the stronger
        # all-players-zero case, handled the same way here.
        if all(bk in scores and scores[bk] <= 0 for bk in cell):
            return "no_military"
    moved = _cell_delta(cell, prev_cell)
    if moved < _bar(FIGHT_MOVE_MIN, dt_s):
        return "static"
    if excluded:
        return "repeat"
    counts = sorted(cell.values(), reverse=True)
    second = counts[1]
    if (second < FIGHT_MIN_SECOND_PIXELS
            or second / total < FIGHT_MIN_SECOND_SHARE):
        if _is_raid(cell, focus_colours, military):
            return None
        return "unbalanced"
    return None


def _cell_holds(cell):
    """True when a cell still holds a fight mix (v3 persistence).

    Deliberately looser than fight entry: no movement requirement
    (a siege or static battle may barely change between two 60s
    scans) and no share bar (a fight being won goes lopsided).
    What it does require is a real mix — at least two buckets, a
    non-trivial total, and a second bucket above the trace floor
    — so that one army leaving (second bucket collapsing to
    traces) ends the hold. A single noisy scan does not end a
    fight on its own: Director counts misses (see FIGHT_EXIT_MISSES).
    """
    total = sum(cell.values())
    if len(cell) < FIGHT_MIN_BUCKETS or total < FIGHT_MIN_PIXELS:
        return False
    second = sorted(cell.values(), reverse=True)[1]
    return second >= FIGHT_MIN_SECOND_PIXELS


def fight_cells(grid, prev_grid=None, exclude_cells=None,
                focus_colours=None, dt_s=60.0, military=None):
    """Cells with a real, balanced, moved mix of player colours.

    Run 14 lesson: a mixed cell alone is NOT a fight. A base's
    surroundings read as a mix too (gold yellow + forest green +
    a few red pixels), and a base never moves — run 14 picked the
    same cell 4 times and the camera sat on a peaceful TC,
    villagers, and sheep at game 7:05. So a fight must also have
    MOVED since the previous scan: the bucket counts in the cell
    must have changed by at least the scaled FIGHT_MOVE_MIN. On
    the first scan (prev_grid None) there is no baseline, so no
    cell counts as a fight — that scan only establishes the
    baseline, and the tour rotates/sweeps.

    Run 15 lessons (v2): a cell in exclude_cells — one that won
    as a fight recently — is never a fight again while excluded,
    however mixed it looks; and a dominant colour plus traces
    (run-15 step 15: yellow 89, red 3, green 2) is a base, not a
    clash, so the second-largest bucket must clear
    FIGHT_MIN_SECOND_PIXELS and FIGHT_MIN_SECOND_SHARE — unless
    it is a raid (v6: focus presence plus >= 6 px of an opponent
    colour). Returns fight cells most-changed first.

    Run 16 lesson (v3): exclude_cells is now the whole run's
    visited-fight set, not a time window. A 600s window failed
    because every run-16 repeat landed ~660s after the previous
    win; only a never-again rule stops a base from re-winning
    forever.

    Run 18 lesson (v6): battles move, so candidates rank by
    CHANGE, not density — moving cells (delta >= scaled
    MOTION_MIN) first, then by delta, then by density. A static
    mixed cell can still win (motion ranks, it does not gate),
    but a genuinely moving clash outranks a busy base.

    Run 19 lesson (v7): motion is not enough — villagers and
    scouts move too, and 0 of 14 verified frames showed a battle.
    When military is known, a fight must involve a bucket that
    HAS military (see _fight_status "no_military"), and candidates
    rank combat-first: a cell whose players are LOSING military
    (units dying = a fight happening now) outranks a higher-motion
    eco cell. Unknown military (None) keeps the v6 ranking.
    """
    found = []
    excluded = exclude_cells or ()
    losing = set((military or {}).get("losing", {}))
    for r in range(GRID):
        for c in range(GRID):
            cell = grid[r][c]
            prev_cell = prev_grid[r][c] if prev_grid is not None else None
            if _fight_status(cell, prev_cell, (r, c) in excluded,
                             focus_colours, dt_s, military) is not None:
                continue
            found.append((sum(cell.values()), r, c, dict(cell),
                          _cell_delta(cell, prev_cell),
                          bool(set(cell) & losing)))
    motion_bar = _bar(MOTION_MIN, dt_s)
    found.sort(key=lambda f: (f[5], f[4] >= motion_bar, f[4], f[0]),
               reverse=True)
    return [(t, r, c, cell) for (t, r, c, cell, _, _) in found]


def ambiguous_mix(grid, prev_grid, exclude_cells=None,
                  focus_colours=None, dt_s=60.0, military=None):
    """True when some cell moved enough to look like a fight but
    was rejected only for being a repeat winner or unbalanced —
    i.e. a base-like mix, not a clash. Static, thin, and baseline
    cells are NOT ambiguous: they never looked like fights in the
    first place, so they keep the old fall-through behaviour.
    Used by choose_target to demote such cells to base rotation
    instead of calling them fights (base-first priority).
    """
    if prev_grid is None:
        return False
    excluded = exclude_cells or ()
    for r in range(GRID):
        for c in range(GRID):
            cell = grid[r][c]
            if _fight_status(cell, prev_grid[r][c],
                             (r, c) in excluded,
                             focus_colours, dt_s, military) in ("repeat", "unbalanced"):
                return True
    return False


def base_cells(grid, player_map=None):
    """Dense dominant-colour cells (bases), densest first.

    v6 (slot-fix lesson): a base is a DOMINANT cell, not a pure
    one — one bucket with >= BASE_MIN_PIXELS and >=
    BASE_DOMINANT_SHARE of the cell total (see _dominant). The
    v4/v5 strict single-colour test found no bases at all in
    live runs 17-18, so no base check of any kind ever fired.
    v7 (run 19 lesson): ALL dominant cells are returned, densest
    first — the old top-6 truncation starved the base slot, because
    Arabia's sand terrain buckets as "yellow" and filled all 6
    slots, so the small early-game focus bases never made the list
    and the slot first fired at step 48. Callers filter by side
    BEFORE truncating, so a focus base is never crowded out by
    terrain. player_map is an optional {colour_bucket: player_name}
    mapping (from the replay's player colours, when known).
    Entries carry the name as a 5th element, or None when
    unmapped — the director rotates through cells either way, but
    with a map it can say WHOSE base it is visiting, which is
    what "follow the right people" needs. On GeForce the colours
    are not yet mapped, so rotation is spatial until the mapping
    source lands.
    """
    found = []
    for r in range(GRID):
        for c in range(GRID):
            dom = _dominant(grid[r][c])
            if dom is not None:
                bk, n = dom
                name = (player_map or {}).get(bk)
                found.append((n, r, c, bk, name))
    found.sort(reverse=True)
    return found


# ---- v4 focus plumbing ----

def _in_side(bk, focus_colours, want_focus):
    """True when bucket bk belongs to the requested side.

    focus_colours None means UNMAPPED: every bucket is focus and
    no bucket is opponent — the opponent rules are disabled and
    all players are treated as the focus team.
    """
    if focus_colours is None:
        return want_focus
    return (bk in focus_colours) if want_focus else (bk not in focus_colours)


def _is_focus_cell(cell, focus_colours):
    """True when a cell holds a real focus-team presence.

    Unmapped (None) counts every non-empty cell as focus. Mapped:
    the focus colours in the cell must total at least
    FOCUS_MIN_PIXELS — one stray pixel (run 17: a single green
    pixel in a yellow/red cell) does not make the cell a focus
    fight and must not outrank the focus base checks below it.
    """
    if focus_colours is None:
        return bool(cell)
    return (sum(n for bk, n in cell.items() if bk in focus_colours)
            >= FOCUS_MIN_PIXELS)


def split_fights(fights, focus_colours):
    """Split densest-first fight cells into (focus, opponent).

    Order within each side is preserved. Unmapped focus puts
    every fight on the focus side and none on the opponent side.
    """
    focus_fights = [f for f in fights if _is_focus_cell(f[3], focus_colours)]
    opponent_fights = [f for f in fights if f not in focus_fights]
    return focus_fights, opponent_fights


def _attack_confirmed(cell, prev_cell, opp_buckets, military=None, dt_s=60.0,
                      attack_watch=None, watch_key=None):
    """(confirmed, debug): is an opposite-colour patch a real attack?

    v11 (run 23 gold-pile lesson): the patch must KEEP MOVING or be
    MILITARY-BACKED. Run 23 step 3 fired again on the same gold-pile
    cell as run 22 — attack_motion 4, exactly at v10's raised 4 px
    floor, military 0. The pile's minimap jitter varies 3-4 px run
    to run, so a single scan over the bar cannot separate it from a
    raid. A motion-only patch now fires only when it met the bar on
    TWO CONSECUTIVE scans (attack_watch, keyed by (cell, defender,
    raider), records whether the previous scan met the bar); a
    military-backed patch still fires on the first scan. A static
    patch with zero military is terrain, never an attack. Unknown
    military never confirms and never blocks: motion decides alone
    (the two-scan rule). The debug record carries the motion delta
    and the gate that fired, so the log shows WHY the camera looked.
    opp_buckets are the opposite-side buckets that triggered the
    attention floor — same-side movement (a teammate passing
    through) must not confirm an attack. With no watch (a lone
    direct call) there is no previous scan, so motion alone never
    confirms — only military backing can fire.
    """
    delta = sum(abs(cell.get(bk, 0) - prev_cell.get(bk, 0))
                for bk in opp_buckets)
    debug = {"attack_motion": delta}
    moved = delta >= _bar(ATTACK_MOVE_MIN, dt_s)
    raider = None
    if opp_buckets:
        raider = max(opp_buckets, key=lambda bk: cell.get(bk, 0))
    key = (watch_key, raider) if watch_key is not None else None
    # Read the previous scan's verdict BEFORE recording this one.
    persisted = False
    if attack_watch is not None and key is not None:
        persisted = bool(attack_watch.get(key))
        attack_watch[key] = moved
    if military is not None and military.get("known"):
        if not military.get("total_zero"):
            scores = military.get("scores", {})
            if raider is not None and raider in scores and scores[raider] > 0:
                debug["attack_gate"] = "military"
                debug["attack_raider"] = raider
                return True, debug
    if moved and persisted:
        # v15: suppress motion gate in Dark Age / early game phase gate.
        # While the clock gate is active (< PHASE_GATE_S), moving patches
        # are terrain jitter (gold piles, forest chops), not real raids.
        # Run 27 had 9/33 steps fire as base_under_attack via motion during
        # phase gate with military total 0 — all wasted Dark Age moves.
        if military is not None and military.get("phase_gated"):
            return False, debug
        debug["attack_gate"] = "motion"
        return True, debug
    return False, debug


def _side_attention(grid, prev_grid, focus_colours, want_focus,
                    dt_s=60.0, military=None, attack_watch=None):
    """Event cells for one side: under-attack, then new expansions.

    Under attack: the previous scan showed a dense dominant cell
    of this side (v6: dominant, not single-colour — the strict
    test never fired live, same slot-fix lesson), and now that
    colour mixes with an opposite colour above the attention
    floor (a raiding party need not clear the full fight balance
    bar to deserve a look — if it did clear it, the fight branch
    above already won).
    v11 (run 23 gold-pile lesson): the opposite patch must also be
    a real attack — it KEPT MOVING across two consecutive scans, or
    the attacking colour has military (see _attack_confirmed). One
    scan over the bar is a gold pile's jitter as often as a raid. A
    static patch with zero military is terrain (gold renders
    yellow and never moves) and earns no visit at all; the cell
    stays an ordinary base for the rotation.
    New expansion: the previous scan showed no dense dominant
    cell here, and now a dense dominant cell of this side appears
    (a new TC, castle, or forward base).
    Returns [(kind, r, c, debug)] with under-attack first, each
    group densest first. Empty when prev_grid is None.
    """
    if prev_grid is None:
        return []
    attacks = []
    expansions = []
    for r in range(GRID):
        for c in range(GRID):
            cell = grid[r][c]
            prev = prev_grid[r][c]
            prev_dom = _dominant(prev)
            if prev_dom is not None:
                pbk, pn = prev_dom
                if _in_side(pbk, focus_colours, want_focus):
                    # Opposite colour above the trace floor in this cell now?
                    opp_bks = []
                    for bk, n in cell.items():
                        if bk == pbk:
                            continue
                        if focus_colours is None:
                            if want_focus:
                                opp_bks.append(bk)
                        elif _in_side(bk, focus_colours, not want_focus):
                            opp_bks.append(bk)
                    opp = [cell[bk] for bk in opp_bks]
                    if opp and max(opp) >= ATTENTION_MIN_OPP_PIXELS:
                        # v11 gate: moved twice running, or
                        # military-backed — otherwise this is terrain
                        # (run 21's gold pile: yellow 7, unmoving,
                        # military 0; run 23's: jitter 4 on one scan).
                        confirmed, gate_dbg = _attack_confirmed(
                            cell, prev, opp_bks, military, dt_s,
                            attack_watch, (r, c, pbk))
                        if confirmed:
                            attacks.append((sum(cell.values()), r, c,
                                            {"cell": (r, c), "colours": dict(cell),
                                             "pixels": sum(cell.values()),
                                             "colour": pbk, **gate_dbg}))
            if prev_dom is None:
                dom = _dominant(cell)
                if dom is not None:
                    bk, n = dom
                    if _in_side(bk, focus_colours, want_focus):
                        expansions.append((n, r, c,
                                           {"cell": (r, c), "colour": bk,
                                            "pixels": n}))
    attacks.sort(reverse=True)
    expansions.sort(reverse=True)
    out = [("under_attack", r, c, dbg) for _, r, c, dbg in attacks]
    out += [("expansion", r, c, dbg) for _, r, c, dbg in expansions]
    return out


def _follow_cell(grid, prev_grid, active_cell, active_delta,
                 exclude_cells, dt_s=60.0, military=None, focus_colours=None):
    """Neighbour the fight moved to, or None.

    The fight moved: chase it. A neighbour counts when it is a
    plausible fight cell (mixed, non-trivial), has never won as
    a fight this run, and is moving harder than the cell we're on
    (delta >= the scaled MOTION_MIN and above the active cell's
    delta). The most-changed such neighbour wins. Returns
    (r, c, cell, delta) or None.

    v7 density floor (run 19 lesson): the old follow test was only
    "mixed + non-trivial + moving", so a dominant sand cell with
    a passing scout won as a follow — run 19's empty frame-08
    cell (yellow 55, blue 2, red 8) was exactly that: 90%
    dominant, traces of a second colour, moving. A follow target
    must now pass the same fight-entry bars as a fresh fight
    (_fight_status: balance or raid, plus the military gate), not
    just be mixed and moving. A lone scout can no longer drag
    the camera to empty ground. Raids stay followable: the
    focus_colours are passed through so the raid exception in
    _fight_status can admit a below-bar raid neighbour.
    """
    if prev_grid is None:
        return None
    r0, c0 = active_cell
    motion_bar = _bar(MOTION_MIN, dt_s)
    best = None
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            r, c = r0 + dr, c0 + dc
            if not (0 <= r < GRID and 0 <= c < GRID):
                continue
            if (r, c) in (exclude_cells or ()):
                continue
            cell = grid[r][c]
            # v7: a follow target is a fight, not just a mixed
            # moving cell — it must clear the entry bars (balance
            # or raid, military gate) against the previous scan.
            if _fight_status(cell, prev_grid[r][c], False,
                             focus_colours, dt_s, military) is not None:
                continue
            delta = _cell_delta(cell, prev_grid[r][c])
            if delta >= motion_bar and delta > active_delta:
                if (best is None or delta > best[3]
                        or (delta == best[3]
                            and sum(cell.values()) > sum(best[2].values()))):
                    best = (r, c, dict(cell), delta)
    return best


def focus_attention(grid, prev_grid, focus_colours, dt_s=60.0, military=None,
                    attack_watch=None):
    """Focus-team attention events (under attack, then expansions).

    dt_s / military feed the v11 attack gate (see
    _attack_confirmed): an under-attack event needs a patch that
    kept moving across two scans, or a military-backed opposite
    patch — not just a trace above the floor. attack_watch is the
    caller-held persistence dict (see _attack_confirmed).
    """
    return _side_attention(grid, prev_grid, focus_colours, True, dt_s,
                           military, attack_watch)


def opponent_relevant_bases(grid, prev_grid, focus_colours, dt_s=60.0, military=None,
                            attack_watch=None):
    """Opponent bases worth an occasional look, or [].

    Relevant means only: under attack by the focus team, or a new
    expansion/castle. When focus is unmapped there are no
    opponents, so this is always empty. Relevance alone does not
    grant a visit — the 1-in-4 cap in choose_target still applies.
    The v11 attack gate applies here too (a static gold patch in
    an opponent base is not an attack by the focus team).
    """
    if focus_colours is None:
        return []
    return _side_attention(grid, prev_grid, focus_colours, False, dt_s,
                           military, attack_watch)


def opponent_base_allowed(base_visits, opponent_base_visits):
    """True when the next base visit may be an opponent base.

    Cap: after the visit, opponent visits must still be at most
    1 in OPPONENT_BASE_EVERY base visits. The first base visit
    can never be an opponent (1*4 <= 1 is false); after 3 focus
    visits the 4th may be opponent, then again after 3 more.
    """
    return ((opponent_base_visits + 1) * OPPONENT_BASE_EVERY
            <= base_visits + 1)


def cell_to_point(r: int, c: int, diamond, screen_w: int, screen_h: int,
                  centroid=None, safe_margin: float = DIAMOND_SAFE_MARGIN):
    """Centre of a grid cell as a logical screen point — or the
    centroid point when centroid=(fx, fy) is given (0..1 within the
    cell, from scan_centroids). v7: the director clicks where the
    dots actually are, not the middle of a cell that happens to
    contain them (run 19's tail-10 attack sat at the frame's edge
    because the click was the cell centre). Without a centroid the
    point is the cell centre, as before.
    v13 wasted-view guard: clamps normalized coordinates within
    safe_margin of the minimap diamond so the camera never aims into
    black edge terrain.
    """
    nx0, ny0, nx1, ny1 = diamond
    fx, fy = centroid if centroid is not None else (0.5, 0.5)
    norm_x = (c + fx) / GRID
    norm_y = (r + fy) / GRID
    if safe_margin is not None and safe_margin > 0:
        max_dist = 0.5 * safe_margin
        dx = norm_x - 0.5
        dy = norm_y - 0.5
        dist = abs(dx) + abs(dy)
        if dist > max_dist and dist > 0:
            scale = max_dist / dist
            norm_x = 0.5 + dx * scale
            norm_y = 0.5 + dy * scale
    x = nx0 + norm_x * (nx1 - nx0)
    y = ny0 + norm_y * (ny1 - ny0)
    return (int(round(x * screen_w)), int(round(y * screen_h)))


def sweep_points(diamond, screen_w: int, screen_h: int):
    """Old spread tour, expressed inside the diamond (fallback only)."""
    rel = [(0.14, 0.50), (0.50, 0.50), (0.86, 0.50), (0.50, 0.14)]
    nx0, ny0, nx1, ny1 = diamond
    return [(int(round((nx0 + fx * (nx1 - nx0)) * screen_w)),
             int(round((ny0 + fy * (ny1 - ny0)) * screen_h)))
            for fx, fy in rel]


def _annotate_fight(debug, cell, focus_colours, prev_cell=None, military=None):
    """Add motion + raid flags to a fight debug record (in place).

    "motion" is the cell's bucket-count change vs the previous
    scan — the log shows whether the camera followed movement or
    a static mix. "raid" marks a fight won via the raid exception
    (focus presence plus >= 6 px of an opponent colour, below the
    15 px balance bar). v7: "military_losing" lists the buckets in
    this cell whose military fell since the last scan — the
    combat confirmation — when the military signal is known.
    """
    if prev_cell is not None:
        debug["motion"] = _cell_delta(cell, prev_cell)
    if _is_raid(cell, focus_colours, military):
        debug["raid"] = True
    if military is not None and military.get("known"):
        losing = [bk for bk in cell if bk in military.get("losing", {})]
        if losing:
            debug["military_losing"] = sorted(losing)
    return debug


def choose_target(grid, diamond, screen_w: int, screen_h: int,
                  rotation_index: int, rotation_due: bool, sweep_index: int,
                  prev_grid=None, player_map=None, exclude_cells=None,
                  active_cell=None, last_point=None,
                  focus_colours=None, base_check_index=0,
                  base_visits=0, opponent_base_visits=0, dt_s=60.0,
                  military=None, centroids=None, attack_watch=None):
    """Pure target choice. Returns (point, reason, debug).

    rotation_index/sweep_index are caller-held counters; the
    caller advances rotation_index only when a base target is
    actually used, and sweep_index only for sweep targets.
    prev_grid is the previous scan (None on the first scan).
    player_map is an optional {colour: player_name} mapping.
    exclude_cells is the run's visited-fight set: cells in it
    never win as fights again (v3 never-again rule).
    active_cell is the fight the camera is already on (v3
    stickiness): while its mix holds it wins again as
    "fight_hold", whatever else the grid holds — unless focus is
    mapped, the active mix is opponent-only, and a fresh focus
    fight exists, which pre-empts it (a focus fight outranks an
    opponent fight). If the active mix no longer holds, this pure
    function treats it as cleared and falls through; the stateful
    Director adds the grace/margin rules on top.
    last_point is where the camera already is: when there is no
    fight and no base to visit, the choice is "hold" at that
    point (the tour loop clicks nothing) instead of a sweep
    point. Sweep survives only when there is no last point yet
    — the very first placement, when holding is meaningless.
    focus_colours is None when unmapped (all players focus) or
    a set of focus-team buckets. base_check_index cycles the
    check kind of focus base visits (eco/production/expansion).
    base_visits / opponent_base_visits enforce the 1-in-4
    opponent-base cap.

    V4 order: sticky focus fight > fresh focus fight > focus
    attention (under attack, then expansion) > purposeful focus
    base check > opponent fight > relevant opponent base (capped)
    > sweep (v6: the old "hold last spot" is gone — Vincent's
    direction 2026-11-05 is to keep moving, so a quiet step tours
    to the next sweep point instead of parking). A base check
    never interrupts a fight, and an opponent base never
    interrupts any focus-team item. (V5 exception, stateful only:
    the Director's guaranteed base-check slot interrupts a fight
    for one step every BASE_CHECK_EVERY steps, and its hold cap /
    static-mix demotion end a hold — none of that lives in this
    pure function, which has no step counter. V6, also stateful:
    fight following and the dynamic-hold extension live in the
    Director; the pure function exposes the follow decision for
    an already-active fight.)
    dt_s is the seconds between this scan and the previous one;
    change bars scale by it (see _bar). It defaults to the 60s
    reference interval.
    military is the MilitaryTracker state dict (or None = unknown):
    when known it gates fights (no_military) and ranks
    combat-confirmed candidates first. centroids is the
    scan_centroids map (or None): every returned point aims at the
    relevant dots' centroid inside the winning cell (v7) instead
    of the cell centre — raids/attacks aim at the attackers, base
    checks at the base colour, fights at the whole clash.
    attack_watch is the caller-held v11 persistence dict for
    base_under_attack: _attack_confirmed records whether each
    (cell, defender, raider) patch met the motion bar on the
    previous scan, and a motion-only patch fires only on the
    second consecutive scan over the bar. The Director owns one
    dict per run; a lone call without it behaves as a first scan.
    """
    def _pt(r, c, buckets=None):
        """Screen point for cell (r, c), aimed at the given buckets' centroid."""
        cent = _aim_centroid(centroids, r, c, buckets)
        return cell_to_point(r, c, diamond, screen_w, screen_h, cent)
    # 0. Sticky active fight (with focus pre-emption and v6 follow).
    if active_cell is not None:
        r, c = active_cell
        cell = grid[r][c]
        if _cell_holds(cell):
            if (focus_colours is not None
                    and not _is_focus_cell(cell, focus_colours)):
                fresh = fight_cells(grid, prev_grid, exclude_cells,
                                    focus_colours, dt_s, military)
                ff, _ = split_fights(fresh, focus_colours)
                if ff:
                    total, fr, fc, fcell = ff[0]
                    dbg = {"cell": (fr, fc), "colours": fcell,
                           "pixels": total, "focus": True,
                           "focus_preempt": True}
                    if prev_grid is not None:
                        _annotate_fight(dbg, fcell, focus_colours,
                                        prev_grid[fr][fc], military)
                    return (_pt(fr, fc), "fight", dbg)
            # v6: the fight moved next door — chase it.
            if prev_grid is not None:
                active_delta = _cell_delta(cell, prev_grid[r][c])
                nxt = _follow_cell(grid, prev_grid, (r, c), active_delta,
                                   exclude_cells, dt_s, military,
                                   focus_colours)
                if nxt is not None:
                    fr, fc, fcell, fdelta = nxt
                    dbg = {"cell": (fr, fc), "colours": fcell,
                           "pixels": sum(fcell.values()), "motion": fdelta,
                           "from_cell": (r, c),
                           "focus": _is_focus_cell(fcell, focus_colours)}
                    if _is_raid(fcell, focus_colours, military):
                        dbg["raid"] = True
                    if military is not None and military.get("known"):
                        losing = [bk for bk in fcell
                                  if bk in military.get("losing", {})]
                        if losing:
                            dbg["military_losing"] = sorted(losing)
                    return (_pt(fr, fc), "fight_follow", dbg)
            dbg = {"cell": (r, c), "colours": dict(cell),
                   "pixels": sum(cell.values()),
                   "focus": _is_focus_cell(cell, focus_colours)}
            if prev_grid is not None:
                dbg["motion"] = _cell_delta(cell, prev_grid[r][c])
            return (_pt(r, c), "fight_hold", dbg)
    # 1. Fresh fights, focus first. Motion ranks: the most-changed
    # mixed cell wins (fight_cells sorts moving first); v7: a cell
    # whose players are losing military outranks a higher-motion
    # eco cell, and no fight exists at all while military is 0.
    fights = fight_cells(grid, prev_grid, exclude_cells,
                         focus_colours, dt_s, military)
    focus_fights, opponent_fights = split_fights(fights, focus_colours)
    if focus_fights:
        total, r, c, cell = focus_fights[0]
        dbg = {"cell": (r, c), "colours": cell, "pixels": total,
               "focus": True}
        if prev_grid is not None:
            _annotate_fight(dbg, cell, focus_colours, prev_grid[r][c],
                            military)
        return (_pt(r, c), "fight", dbg)
    # 2. Focus attention events (fire even when rotation not due).
    for kind, r, c, dbg in focus_attention(grid, prev_grid, focus_colours,
                                           dt_s, military, attack_watch):
        reason = "base_under_attack" if kind == "under_attack" else "base_expansion"
        dbg = dict(dbg)
        dbg["focus"] = True
        if kind == "under_attack":
            # v7: aim at the ATTACKERS (every colour except the base
            # colour), not the base centre — run 19's tail-10 attack
            # sat at the frame's edge because the click was the
            # cell centre.
            base_bk = dbg.get("colour")
            attackers = {bk for bk in dbg.get("colours", {})
                         if bk != base_bk}
            return (_pt(r, c, attackers or None), reason, dbg)
        return (_pt(r, c, {dbg["colour"]} if dbg.get("colour") else None),
                reason, dbg)
    # 3. Purposeful focus base checks at quiet times.
    all_bases = base_cells(grid, player_map)
    focus_bases = [b for b in all_bases
                   if _in_side(b[3], focus_colours, True)]
    if focus_bases and (rotation_due
                        or ambiguous_mix(grid, prev_grid, exclude_cells,
                                         focus_colours, dt_s, military)):
        n, r, c, bk, name = focus_bases[rotation_index % len(focus_bases)]
        kind = BASE_CHECK_KINDS[base_check_index % len(BASE_CHECK_KINDS)]
        debug = {"cell": (r, c), "colour": bk, "pixels": n,
                 "check": kind, "focus": True}
        if name:
            debug["player"] = name
        return (_pt(r, c, {bk}), "base_" + kind, debug)
    # 4. Opponent fights: context, below every focus-team item.
    if opponent_fights:
        total, r, c, cell = opponent_fights[0]
        dbg = {"cell": (r, c), "colours": cell, "pixels": total,
               "focus": False}
        if prev_grid is not None:
            _annotate_fight(dbg, cell, focus_colours, prev_grid[r][c],
                            military)
        return (_pt(r, c), "fight", dbg)
    # 5. Opponent bases: relevant AND within the 1-in-4 cap only.
    if opponent_base_allowed(base_visits, opponent_base_visits):
        for kind, r, c, dbg in opponent_relevant_bases(grid, prev_grid, focus_colours,
                                                       dt_s, military,
                                                       attack_watch):
            dbg = dict(dbg)
            dbg["focus"] = False
            dbg["relevant"] = kind
            if kind == "under_attack":
                base_bk = dbg.get("colour")
                attackers = {bk for bk in dbg.get("colours", {})
                             if bk != base_bk}
                return (_pt(r, c, attackers or None),
                        "base_opponent_check", dbg)
            return (_pt(r, c, {dbg["colour"]} if dbg.get("colour") else None),
                    "base_opponent_check", dbg)
    # 6. Move on: no fight, no attention, no opponent context.
    # v16: if focus bases exist, tour to the next focus base (eco, prod, expansion)
    # instead of visiting arbitrary empty sweep points. Sweep is strictly a fallback
    # when no bases exist on the minimap (e.g. scan failure or very early blank load).
    if focus_bases:
        n, r, c, bk, name = focus_bases[rotation_index % len(focus_bases)]
        kind = BASE_CHECK_KINDS[base_check_index % len(BASE_CHECK_KINDS)]
        debug = {"cell": (r, c), "colour": bk, "pixels": n,
                 "check": kind, "focus": True}
        if name:
            debug["player"] = name
        return (_pt(r, c, {bk}), "base_" + kind, debug)
    pts = sweep_points(diamond, screen_w, screen_h)
    pt = pts[sweep_index % len(pts)]
    return (pt, "sweep", {"sweep_index": sweep_index % len(pts)})


class Director:
    """Stateful director: call next_target() with a fresh screenshot
    whenever the tour is due. A fight, once won, is sticky: the
    camera stays on its cell while the mix holds, and a cell that
    won as a fight never wins again this run (visited_fights).
    Leaving a fight takes FIGHT_EXIT_MISSES consecutive scans
    where the cell no longer holds a mix; the first miss is a
    grace scan (camera still holds the spot), during which only
    a new clash stronger by FIGHT_SWITCH_MARGIN may pre-empt it —
    except a fresh focus fight pre-empts an opponent-only active
    fight immediately, at any margin. Focus fights, attention and
    base checks outrank opponent fights and opponent bases (at
    most 1 in 4 base visits, relevant only). Bases rotate only
    when no fight is active or fresh; with nothing to visit, the
    director holds the last spot. A failed scan keeps the active
    fight (a failed screenshot is not evidence the fight ended)
    and falls back to sweep, labelled as before.

    V5 bounds on the hold (run 17 lesson: a 12-minute park on a
    static base mix): at most FIGHT_HOLD_MAX consecutive holds
    on one cell; a hold whose mix moves less than STATIC_MOVE_MIN
    on STATIC_HOLDS_TO_DEMOTE consecutive holds is demoted as a
    base, not a fight; and every BASE_CHECK_EVERY-th step is a
    guaranteed focus base check, whatever the fight state (the
    interrupted fight resumes on the next step — it is not
    abandoned). A forced exit is flagged on the fresh decision's
    debug record as forced_exit {"cell", "why"} so the log shows
    WHY the camera left the cell. A focus cell needs at least
    FOCUS_MIN_PIXELS of focus colours (one pixel is not a focus
    presence).

    V6 bounds and motion (run 18 lesson: key battles still
    missed — ~4 minutes per spot, one snapshot per step, no
    following, small raids invisible): fresh fights rank by
    CHANGE (most-changed mixed cell first, moving cells above
    the scaled MOTION_MIN first); a fight that moves to a
    neighbouring cell is FOLLOWED (fight_follow); a raid (focus
    presence plus >= 6 px of an opponent colour) is a
    first-class focus fight below the 15 px bar; the hold is
    dynamic — a fight that keeps moving earns up to
    FIGHT_HOLD_MAX_EXTENDED holds, one that goes quiet is
    dropped early by the static demotion. All change bars scale
    with the actual seconds between the two scans being compared
    (_bar), so the same fight reads the same at 15s, 30s, 60s
    or 120s sampling. And the v5 slot is FIXED: bases are defined
    by dominance (>= BASE_MIN_PIXELS and >= BASE_DOMINANT_SHARE
    of the cell), not single-colour purity — the strict test
    found no bases at all in live runs 17-18, so the slot never
    fired. Quiet steps now MOVE (next sweep point) instead of
    holding the last spot.

    V7 military signal (run 19 lesson: 0 of 14 verified frames
    showed a battle — motion follows villagers, not combat):
    the score panel's Military column is OCR'd from the same
    probe screenshot and tracked per player. A fight exists only
    where military is present AND changing: falling scores mean
    units dying, i.e. a fight happening now. While every military
    is 0, no fight/fight_follow/raid label is issued at all; when
    military is known, fight candidates rank combat-first (a cell
    whose players are losing military outranks a higher-motion
    eco cell). When the panel cannot be read, the clock phase gate
    takes over (no fights before PHASE_GATE_S game-seconds); when
    neither can be read, the director behaves as v6 and the log
    says the signal is unavailable. The camera also aims at the
    dots' centroid inside the winning cell (raids/attacks at the
    attackers), and follow targets must pass the fight-entry bars
    (the run-19 empty frame-08 cell won only via follow, which had
    no balance bar). The base slot filters by side before
    truncating and keeps a persistence registry of each focus
    colour's home base, so the slot fires from step 4 even when
    the current scan's bases are small.

    V12 combat check (run 25 lesson: 0 pitched battles in 16
    verified frames, 0 in 80 over runs 19-25, despite 6 fight
    calls and 6 holds — minimap motion plus military total cannot
    tell combat from massing): a minimap-motion + military call
    is a SUSPECT, not a fight. The director moves there once to
    look; on the next scan the new view is checked for combat
    evidence. Evidence is either leg: (a) HEALTH BARS in the main
    view — >= COMBAT_BARS_MIN vivid red or green solid bars
    (15-40 px, 2-6 rows) in the main view, calibrated on the 19
    run-25 frames (frame 034 gives exactly 2 red bars, all other
    frames 0); or (b) MILITARY DROP — a single bucket's military
    falling >= COMBAT_DROP_MIN between consecutive COMPLETE stamps
    (totals never fall in run 25 — production masks deaths — so
    the leg is per-bucket; a missing row never fakes a drop).
    Evidence confirms the fight (fight_confirmed, combat_gate
    names the leg); no evidence kills the suspect
    (no_combat_evidence) and the cell stays visited, never
    re-fired. A drop in a bucket IN the fresh cell promotes it
    to confirmed without the look. A confirmed fight is held
    while evidence persists; COMBAT_EVIDENCE_MISSES consecutive
    hold scans with a successful bars read finding nothing end
    it (a failed bars read is unknown, not a miss). The bars
    read runs only when a suspect is pending or a fight is
    active. Fail closed throughout: unknown evidence is a
    suspect, never a confirm.
    """

    def __init__(self, screen_w: int, screen_h: int, diamond=DIAMOND_NORM,
                 player_map=None, focus_colours=None,
                 military_reader=None, clock_reader=None,
                 panel_rows: int = PANEL_ROWS):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.diamond = diamond
        self.player_map = player_map
        # None = unmapped: all players treated as focus, opponent
        # rules disabled. A set = focus-team buckets from
        # --focus-colours; never guessed, never hardcoded.
        self.focus_colours = (set(focus_colours)
                              if focus_colours is not None else None)
        self.panel_rows = panel_rows
        # v7 readers (injectable for tests): military_reader and
        # clock_reader take an image path and return a
        # read_military_scores() result / game-clock seconds.
        # Defaults read the panel/clock from the probe screenshot.
        if military_reader is not None:
            self.military_reader = military_reader
        else:
            self.military_reader = lambda path: read_military_scores(path, panel_rows=self.panel_rows)
        self.clock_reader = clock_reader or read_game_clock_secs
        self.military_tracker = MilitaryTracker(panel_rows=panel_rows)
        self.military_state = self.military_tracker.state()
        self._phase_gated = False  # True when the clock gate is suppressing fights
        self.base_registry = {}  # bucket -> {"cell", "sightings", "pixels"}
        self._centroids = None  # scan_centroids map for the current step
        self.last_rotation_t = None
        self.rotation_index = 0
        self.sweep_index = 0
        self.prev_grid = None
        self._attack_watch = {}  # v11: (cell, defender, raider) -> met bar last scan
        self.suspect_cell = None  # v12: (r, c) fight moved to, awaiting confirmation
        self.suspect_since_step = 0  # step the suspect was set
        self._prev_complete_scores = None  # v12: scores of the last COMPLETE military read
        self._combat_bars = None  # v12: (red, green) bars this scan, or None (unread)
        self._combat_drop = None  # v12: drop dict this scan, or None
        self._combat_misses = 0  # v12: consecutive confirmed holds with no evidence
        self.active_cell = None  # (r, c) fight the camera is on, or None
        self.active_miss = 0  # consecutive scans the active mix failed to hold
        self.active_last_total = 0  # active cell total at its last holding scan
        self.active_holds = 0  # consecutive fight_hold returns on this cell (v5 cap)
        self.active_last_mix = None  # bucket counts at the last holding scan (v5 static check)
        self.active_static_streak = 0  # consecutive holds moved < STATIC_MOVE_MIN
        self.active_high_streak = 0  # consecutive holds moved >= MOTION_MIN (v6 extension)
        self._last_scan_t = None  # now_s of the previous next_target call (v6 dt)
        self.step_count = 0  # tour decisions this run (v5 guaranteed slot)
        self.visited_fights = set()  # every fight-winning cell this run
        self.fight_cooldowns = {}  # v14: (r, c) -> last_visited_now_s
        self.fight_cooldown_s = FIGHT_COOLDOWN_S  # cooldown window in seconds (Option 3A)
        self.last_point = None  # point of the last fight/base/sweep move
        self.base_check_index = 0  # cycles eco/production/expansion checks
        self.base_visits = 0  # base-check + opponent-check visits
        self.opponent_base_visits = 0  # subset of base_visits

    def _clear_active(self):
        """Drop the active fight and all per-fight hold state."""
        self.active_cell = None
        self.active_miss = 0
        self.active_holds = 0
        self.active_last_mix = None
        self.active_static_streak = 0
        self.active_high_streak = 0
        self.suspect_cell = None  # v12: no suspect survives a fight exit
        self._combat_misses = 0  # v12: evidence misses reset with the fight

    def _point(self, r, c, buckets=None):
        """Screen point for cell (r, c), aimed at the given buckets' centroid."""
        cent = _aim_centroid(self._centroids, r, c, buckets)
        return cell_to_point(r, c, self.diamond, self.screen_w,
                             self.screen_h, cent)

    def _update_base_registry(self, grid):
        """Remember each focus colour's densest base-like cell (v7).

        A cell counts when one bucket holds >= REGISTRY_MIN_PIXELS
        and >= REGISTRY_MIN_SHARE of the cell total — a lower floor
        than _dominant, so a Dark Age TC registers — and the entry
        is confirmed only after the SAME bucket is seen at the SAME
        cell on REGISTRY_CONFIRM_SCANS scans. A passing army never
        repeats at one cell; a base does. The registry is the
        slot's fallback when the current scan shows no dominant
        focus base (the run-19 late start: the slot had nothing to
        visit until bases grew large enough).
        A cell NEVER registers as a base when it holds a live
        fight mix (_is_live_fight_mix: a balanced clash) — a fight
        cell is often dominant (one side winning) and persists at
        one cell for many scans, so without this the registry
        learns the fight itself as a base and the slot "checks"
        the fight it is meant to interrupt (regression caught by
        the dynamic-hold test: the fight cell red 58 / yellow 37
        registered as a base). A cell that won as a fight but has
        since gone base-like (second colour faded below the bar)
        may register again — it is a base now.
        """
        seen = {}
        for r in range(GRID):
            for c in range(GRID):
                cell = grid[r][c]
                if _is_live_fight_mix(cell):
                    continue  # a clash, not a base
                total = sum(cell.values())
                if total < REGISTRY_MIN_PIXELS:
                    continue
                bk, n = max(cell.items(), key=lambda kv: kv[1])
                if n < REGISTRY_MIN_PIXELS or n / total < REGISTRY_MIN_SHARE:
                    continue
                if not _in_side(bk, self.focus_colours, True):
                    continue
                if bk not in seen or n > seen[bk][0]:
                    seen[bk] = (n, (r, c))
        for bk, (n, cell) in seen.items():
            ent = self.base_registry.get(bk)
            if ent is not None and ent["cell"] == cell:
                ent["sightings"] += 1
                ent["pixels"] = n
            else:
                self.base_registry[bk] = {"cell": cell, "sightings": 1,
                                          "pixels": n}

    def _registered_bases(self):
        """All CONFIRMED registry focus bases.

        Confirmed = seen at the same cell on REGISTRY_CONFIRM_SCANS
        scans. Returns list of (pixels, r, c, bucket).
        """
        bases = []
        for bk, ent in self.base_registry.items():
            if ent["sightings"] < REGISTRY_CONFIRM_SCANS:
                continue
            bases.append((ent["pixels"], ent["cell"][0], ent["cell"][1], bk))
        bases.sort(key=lambda b: b[3])
        return bases

    def _registered_base(self):
        """Densest CONFIRMED registry focus base, or None.

        Confirmed = seen at the same cell on REGISTRY_CONFIRM_SCANS
        scans. Returns (pixels, r, c, bucket) or None.
        """
        bases = self._registered_bases()
        if not bases:
            return None
        return max(bases, key=lambda b: b[0])

    def _hold_cap(self):
        """Effective hold cap (v6 dynamic hold).

        Extended while the fight keeps moving hard; the plain
        cap otherwise. The extension lasts only while the motion
        lasts — the moment a hold comes in below MOTION_MIN, the
        cap is 3 again and a fight already held past it exits.
        """
        if self.active_high_streak >= 1:
            return FIGHT_HOLD_MAX_EXTENDED
        return FIGHT_HOLD_MAX

    def _mix_moved(self, cell):
        """Bucket-count change vs the active cell's last holding scan.

        Same metric as FIGHT_MOVE_MIN at fight entry. No baseline
        yet returns the entry bar itself, so it never demotes.
        """
        if self.active_last_mix is None:
            return FIGHT_MOVE_MIN
        prev = self.active_last_mix
        return sum(abs(cell.get(bk, 0) - prev.get(bk, 0))
                   for bk in set(cell) | set(prev))

    def _guaranteed_base_check(self, grid, dt_s=60.0):
        """A focus base check for the guaranteed slot, or None.

        Returns (point, reason, debug) or None when no focus base
        is visible. The caller does the rotation bookkeeping.
        v7: the current scan's dominant focus bases come first
        (base_cells now returns ALL dominant cells, filtered by
        side before truncating — the run-19 late-start fix); when
        the scan shows none, the persistence registry supplies the
        densest confirmed focus base instead, so the slot fires
        from step 4 even while bases are still small. A candidate
        is skipped when it is a HOT live fight mix
        (_is_hot_fight_mix, balance bar AND motion): the slot must
        never label a churning battle a base check, but a dominant
        cell whose fight has gone quiet is a base and may be
        checked — including the active fight cell, whose hold
        resumes on the next step (run-18 (4,4) behaviour).
        """
        all_bases = base_cells(grid, self.player_map)
        focus_bases = [b for b in all_bases
                       if _in_side(b[3], self.focus_colours, True)
                       and not _is_hot_fight_mix(
                           grid[b[1]][b[2]],
                           self.prev_grid[b[1]][b[2]]
                           if self.prev_grid is not None else None,
                           dt_s)]
        if focus_bases:
            n, r, c, bk, name = focus_bases[self.rotation_index % len(focus_bases)]
            kind = BASE_CHECK_KINDS[self.base_check_index % len(BASE_CHECK_KINDS)]
            debug = {"cell": (r, c), "colour": bk, "pixels": n,
                     "check": kind, "focus": True, "guaranteed": True}
            if name:
                debug["player"] = name
            pt = self._point(r, c, {bk})
            return pt, "base_" + kind, debug
        reg = self._registered_base()
        if reg is not None:
            n, r, c, bk = reg
            # The registry is memory: re-validate against the
            # CURRENT scan before visiting — a base that has since
            # become a hot live fight mix is not a base check, and
            # the slot must not "check" the fight cell.
            cell = grid[r][c]
            prev_cell = (self.prev_grid[r][c]
                         if self.prev_grid is not None else None)
            if _is_hot_fight_mix(cell, prev_cell, dt_s):
                return None
            kind = BASE_CHECK_KINDS[self.base_check_index % len(BASE_CHECK_KINDS)]
            name = (self.player_map or {}).get(bk)
            debug = {"cell": (r, c), "colour": bk, "pixels": n,
                     "check": kind, "focus": True, "guaranteed": True,
                     "registry": True}
            if name:
                debug["player"] = name
            pt = self._point(r, c, {bk})
            return pt, "base_" + kind, debug
        return None

    def _drop_for_scan(self):
        """Drop evidence for the current scan, or None.

        Compares the current COMPLETE military state against the last
        complete stamp and returns {"bucket", "drop", "total_drop"}:
        "drop" is the largest single-bucket fall (0 when no bucket
        fell), "total_drop" the fall in the total (0 when it rose).
        Both stamps must be complete — a missing row must not fake
        a drop, and the phase-gate stand-in (complete False) never
        counts. The last complete stamp persists across incomplete
        scans (the drop is between consecutive COMPLETE stamps, not
        necessarily consecutive scans). Updates the stored stamp
        when the current state is complete.
        """
        state = self.military_state
        if not state.get("known") or not state.get("complete"):
            return None
        scores = state["scores"]
        drop = None
        if self._prev_complete_scores is not None:
            per = {bk: self._prev_complete_scores[bk] - cur
                   for bk, cur in scores.items()
                   if bk in self._prev_complete_scores
                   and cur < self._prev_complete_scores[bk]}
            total_drop = (sum(self._prev_complete_scores.values())
                          - sum(scores.values()))
            best = max(per, key=per.get) if per else None
            drop = {"bucket": best,
                    "drop": per.get(best, 0) if best else 0,
                    "total_drop": max(0, total_drop)}
        self._prev_complete_scores = dict(scores)
        return drop

    def _classify_fight(self, cell, colours, debug, now_s=0.0):
        """v12/v14: classify a fresh fight cell as suspect or confirmed.

        Returns (reason, debug). A cell is confirmed outright only
        when a bucket IN THIS CELL just dropped by >= COMBAT_DROP_MIN
        (the drop locates the fight, so no look is needed first);
        otherwise it is a suspect — the camera moves there once to
        look, and the next scan confirms or kills it. Sets the run
        state: a confirm sets the active-fight fields, a suspect
        clears any active fight and records the suspect cell. The
        cell joins visited_fights and fight_cooldowns either way:
        a suspect visit is the one look, and the cell cools down for
        FIGHT_COOLDOWN_S before it can be chosen again.
        Callers keep their own debug fields (switched, focus_preempt,
        motion); this only adds combat_gate/combat_evidence.
        """
        debug = dict(debug)
        drop = self._combat_drop
        if (drop is not None and drop.get("bucket") in colours
                and drop["drop"] >= COMBAT_DROP_MIN):
            debug["combat_gate"] = "military_drop"
            debug["combat_evidence"] = {"drop": drop,
                                         "bars": self._combat_bars}
            self._clear_active()
            self.active_cell = cell
            self.active_miss = 0
            self.active_last_total = debug["pixels"]
            self.active_last_mix = dict(colours)
            self.active_static_streak = 0
            self.active_high_streak = 0
            self.active_holds = 0
            self._combat_misses = 0
            self.visited_fights.add(cell)
            self.fight_cooldowns[cell] = now_s
            return "fight_confirmed", debug
        debug["combat_gate"] = "suspect"
        debug["combat_evidence"] = None
        self._clear_active()
        self.suspect_cell = cell
        self.suspect_since_step = self.step_count
        self.visited_fights.add(cell)
        self.fight_cooldowns[cell] = now_s
        return "fight_suspect", debug

    def next_target(self, image_path: str, now_s: float,
                    military_scores=_UNSET, game_clock_s=_UNSET):
        """One tour decision from a fresh probe screenshot.

        military_scores / game_clock_s are test hooks: pass a
        read_military_scores() result (or None) and a game-clock
        reading in seconds to use them directly instead of reading
        the probe image. When omitted, both are read from the probe
        screenshot (military panel, then clock for the phase gate).
        """
        grid = scan_minimap(image_path, self.diamond)
        if grid is None:
            pts = sweep_points(self.diamond, self.screen_w, self.screen_h)
            pt = pts[self.sweep_index % len(pts)]
            self.sweep_index += 1
            self.last_point = pt
            return pt, "sweep_scan_failed", {}
        # v7: centroids for aiming (best-effort — a failed centroid
        # scan falls back to cell-centre aiming, as before).
        try:
            self._centroids = scan_centroids(image_path, self.diamond)
        except Exception:
            self._centroids = None
        # v7: military signal + phase gate. The military read is the
        # primary signal; the clock gate applies only when the panel
        # cannot be read. Both are read from the same probe
        # screenshot the minimap scan already uses.
        self._phase_gated = False
        if military_scores is _UNSET:
            try:
                military_scores = self.military_reader(image_path)
            except Exception:
                military_scores = None
        self.military_state = self.military_tracker.update(military_scores)
        if not self.military_state["known"]:
            clock_s = game_clock_s
            if clock_s is _UNSET:
                try:
                    clock_s = self.clock_reader(image_path)
                except Exception:
                    clock_s = None
            if clock_s is not None and clock_s < PHASE_GATE_S:
                # Phase gate: the panel is unreadable AND the game is
                # early, so behave as if every military is 0 — no
                # fight labels. (The military tracker is untouched:
                # the gate is a per-step suppression, not a reading.)
                self._phase_gated = True
                self.military_state = {"known": True, "complete": False,
                                       "total": 0, "total_zero": True,
                                       "losing": {}, "scores": {},
                                       "phase_gated": True}
        # v7: the base registry learns every scan (persistence is
        # what makes a small early-game base visitable by the slot).
        self._update_base_registry(grid)
        self.step_count += 1
        # v6: seconds since the previous scan. Change bars scale
        # by this (see _bar): the tour step is 30s at test pace
        # and 15s inside a fight, so a 60s-calibrated bar would
        # misread fast sampling. First call (or a non-positive
        # gap, e.g. two calls stamped the same second in a test)
        # uses the 60s reference interval; gaps over 600s clamp
        # there so a stalled loop cannot inflate the bars without
        # bound.
        if self._last_scan_t is None or now_s <= self._last_scan_t:
            dt_s = MOTION_BASE_DT_S
        else:
            dt_s = min(now_s - self._last_scan_t, 600.0)
        self._last_scan_t = now_s
        forced_exit = None
        # v12: combat evidence for this scan. The bars read runs
        # only when a suspect is pending or a fight is active — on
        # a quiet step the current view is not a fight cell, so its
        # bars would be evidence about the wrong place (and the
        # ffmpeg pass is saved). The drop is pure dict math on the
        # military stamps, so it runs every scan: it is what lets a
        # fresh fight promote straight to confirmed. A failed scan
        # never reaches here (sweep_scan_failed returns first), so
        # a suspect survives a bad screenshot.
        if self.suspect_cell is not None or self.active_cell is not None:
            try:
                self._combat_bars = scan_combat_bars(image_path)
            except Exception:
                self._combat_bars = None
        else:
            self._combat_bars = None
        self._combat_drop = self._drop_for_scan()
        # v14 fight cooldowns: cells whose cooldown has not expired
        cooling = {c for c, t in self.fight_cooldowns.items()
                   if now_s - t < self.fight_cooldown_s}
        if self.active_cell is not None:
            cooling.add(self.active_cell)
        # v12: a pending suspect is resolved on the very next scan.
        # Evidence -> the fight is CONFIRMED (the camera is already
        # looking at the cell, so it stays). No evidence -> the
        # suspect dies and the step falls through to the normal
        # decision, flagged as forced_exit so the log shows why the
        # camera left. The cell stays in visited_fights and cools down
        # for FIGHT_COOLDOWN_S: it had its one look. A confirming suspect
        # pre-empts the base slot below (a confirmed fight outranks a
        # base check); a dying suspect does not — the slot may still
        # fire this step.
        if self.suspect_cell is not None:
            gate, evidence = _combat_evidence(self._combat_bars,
                                              self._combat_drop)
            if gate != "none":
                r, c = self.suspect_cell
                cell = grid[r][c]
                dbg = {"cell": (r, c), "colours": dict(cell),
                       "pixels": sum(cell.values()),
                       "focus": _is_focus_cell(cell, self.focus_colours),
                       "combat_gate": gate, "combat_evidence": evidence,
                       "suspect_step": self.suspect_since_step}
                if self.prev_grid is not None:
                    _annotate_fight(dbg, cell, self.focus_colours,
                                    self.prev_grid[r][c],
                                    self.military_state)
                self._clear_active()
                self.active_cell = (r, c)
                self.active_miss = 0
                self.active_last_total = sum(cell.values())
                self.active_last_mix = dict(cell)
                self.active_static_streak = 0
                self.active_high_streak = 0
                self.active_holds = 0
                self._combat_misses = 0
                self.visited_fights.add((r, c))
                self.fight_cooldowns[(r, c)] = now_s
                cooling.add((r, c))
                pt = self._point(r, c)
                self.last_point = pt
                self.prev_grid = grid
                if self.military_state.get("known"):
                    dbg = dict(dbg)
                    dbg["military"] = _military_log(self.military_state)
                if self._phase_gated:
                    dbg = dict(dbg)
                    dbg["phase_gated"] = True
                return pt, "fight_confirmed", dbg
            forced_exit = {"cell": self.suspect_cell,
                           "why": "no_combat_evidence",
                           "bars": self._combat_bars,
                           "drop": self._combat_drop}
            self.fight_cooldowns[self.suspect_cell] = now_s
            cooling.add(self.suspect_cell)
            self.suspect_cell = None
        # v5 guaranteed focus base-check slot (run 17 lesson): every
        # BASE_CHECK_EVERY-th step is a focus base check, whatever
        # the fight state. Base checks starved for a whole run
        # (0 of 20 in run 17) cannot happen again. An interrupted
        # fight is NOT abandoned — active_cell is left alone, so
        # the next step resumes the hold where it left off.
        if self.step_count % BASE_CHECK_EVERY == 0:
            slot = self._guaranteed_base_check(grid, dt_s)
            if slot is not None:
                pt, reason, debug = slot
                self.rotation_index += 1
                self.last_rotation_t = now_s
                self.base_check_index += 1
                self.base_visits += 1
                # v6: the slot scan still observes the active
                # fight's cell — refresh the mix baseline so the
                # next hold compares against this scan, not the
                # pre-slot one (and so its dt is one step, not two).
                if self.active_cell is not None:
                    ar, ac = self.active_cell
                    self.active_last_mix = dict(grid[ar][ac])
                    self.active_last_total = sum(grid[ar][ac].values())
                self.last_point = pt
                self.prev_grid = grid
                return pt, reason, debug
        # 1. Sticky fight: hold while the mix holds; grace + margin
        #    pre-emption while it fades; clear only after
        #    FIGHT_EXIT_MISSES consecutive misses. A fresh focus
        #    fight pre-empts an opponent-only active fight at once.
        if self.active_cell is not None:
            r, c = self.active_cell
            cell = grid[r][c]
            # v7: a fight whose players all have zero military is
            # over (everyone died) — leave it, whatever the mix
            # still shows. total_zero needs a COMPLETE panel read,
            # so one bad OCR row cannot kill a real fight.
            if self.military_state.get("total_zero"):
                forced_exit = {"cell": (r, c), "why": "no_military"}
                self._clear_active()
            elif _cell_holds(cell):
                if (self.focus_colours is not None
                        and not _is_focus_cell(cell, self.focus_colours)):
                    fresh = fight_cells(grid, self.prev_grid,
                                        cooling,
                                        self.focus_colours, dt_s,
                                        self.military_state)
                    ff, _ = split_fights(fresh, self.focus_colours)
                    if ff:
                        total, fr, fc, fcell = ff[0]
                        # Previous-scan cell FIRST: prev_grid is
                        # reassigned below, and the motion flag must
                        # compare against the previous scan, not this one.
                        prev_cell = (self.prev_grid[fr][fc]
                                     if self.prev_grid is not None else None)
                        self.prev_grid = grid
                        dbg = {"cell": (fr, fc), "colours": fcell,
                               "pixels": total, "focus": True,
                               "switched": True, "focus_preempt": True}
                        _annotate_fight(dbg, fcell, self.focus_colours,
                                        prev_cell, self.military_state)
                        # v12/v14: fresh fight is suspect or confirmed
                        reason, dbg = self._classify_fight((fr, fc), fcell, dbg, now_s=now_s)
                        pt = self._point(fr, fc)
                        self.last_point = pt
                        return pt, reason, dbg
                # v6: the fight moved next door — chase it instead
                # of holding a cell the battle left.
                if self.prev_grid is not None:
                    active_delta = _cell_delta(cell, self.prev_grid[r][c])
                    nxt = _follow_cell(grid, self.prev_grid, (r, c),
                                       active_delta, cooling,
                                       dt_s, self.military_state,
                                       self.focus_colours)
                    if nxt is not None:
                        fr, fc, fcell, fdelta = nxt
                        self.active_cell = (fr, fc)
                        self.active_miss = 0
                        self.active_last_total = sum(fcell.values())
                        self.active_last_mix = dict(fcell)
                        self.active_static_streak = 0
                        self.active_high_streak = 0
                        self.active_holds = 0
                        self.visited_fights.add((fr, fc))
                        self.fight_cooldowns[(fr, fc)] = now_s
                        cooling.add((fr, fc))
                        pt = self._point(fr, fc)
                        self.last_point = pt
                        self.prev_grid = grid
                        dbg = {"cell": (fr, fc), "colours": fcell,
                               "pixels": sum(fcell.values()),
                               "motion": fdelta, "from_cell": (r, c),
                               "focus": _is_focus_cell(fcell,
                                                       self.focus_colours)}
                        if _is_raid(fcell, self.focus_colours,
                                    self.military_state):
                            dbg["raid"] = True
                        if self.military_state.get("known"):
                            losing = [bk for bk in fcell
                                      if bk in self.military_state.get("losing", {})]
                            if losing:
                                dbg["military_losing"] = sorted(losing)
                        return pt, "fight_follow", dbg
                # v5: the hold is earned every scan, not assumed.
                # A fight's mix must keep moving (a base's economy
                # pixels sit still — run 17's 12-minute park), and
                # no cell may be held more than the cap. Either
                # failure forces an exit: the cell is already in
                # visited_fights, so it can never re-win as a
                # fight; the fresh decision below runs in the same
                # call, flagged on its debug record as forced_exit.
                # v6 dynamic hold: the bars scale by dt_s, and a
                # hold that keeps moving at or above MOTION_MIN
                # extends the cap to FIGHT_HOLD_MAX_EXTENDED — but
                # only while the motion lasts.
                moved = self._mix_moved(cell)
                if moved < _bar(STATIC_MOVE_MIN, dt_s):
                    self.active_static_streak += 1
                else:
                    self.active_static_streak = 0
                if moved >= _bar(MOTION_MIN, dt_s):
                    self.active_high_streak += 1
                else:
                    self.active_high_streak = 0
                self.active_last_mix = dict(cell)
                # v12: a confirmed fight is held while combat
                # evidence persists. Count this scan: evidence resets
                # the misses; a successful bars read that found
                # nothing (and no drop) is a miss; a FAILED bars read
                # is unknown, not a miss — a broken scanner must not
                # kill a real fight (the cap is the backstop).
                gate, evidence = _combat_evidence(self._combat_bars,
                                                  self._combat_drop)
                if gate != "none":
                    self._combat_misses = 0
                elif evidence.get("bars_known"):
                    self._combat_misses += 1
                if self.active_holds >= self._hold_cap():
                    forced_exit = {"cell": (r, c), "why": "hold_cap",
                                   "holds": self.active_holds,
                                   "cap": self._hold_cap()}
                    self._clear_active()
                elif self.active_static_streak >= STATIC_HOLDS_TO_DEMOTE:
                    forced_exit = {"cell": (r, c), "why": "static_mix",
                                   "streak": self.active_static_streak}
                    self._clear_active()
                elif self._combat_misses >= COMBAT_EVIDENCE_MISSES:
                    forced_exit = {"cell": (r, c),
                                   "why": "no_combat_evidence",
                                   "misses": self._combat_misses}
                    self._clear_active()
                else:
                    self.active_miss = 0
                    self.active_holds += 1
                    self.active_last_total = sum(cell.values())
                    pt = self._point(r, c)
                    self.last_point = pt
                    self.prev_grid = grid
                    dbg = {"cell": (r, c), "colours": dict(cell),
                           "pixels": sum(cell.values()),
                           "motion": moved,
                           "focus": _is_focus_cell(cell, self.focus_colours),
                           "combat_gate": gate if gate != "none"
                                          else "persisting",
                           "combat_evidence": evidence if gate != "none"
                                              else None,
                           "combat_misses": self._combat_misses}
                    if self.military_state.get("known"):
                        losing = [bk for bk in cell
                                  if bk in self.military_state.get("losing", {})]
                        if losing:
                            dbg["military_losing"] = sorted(losing)
                    return pt, "fight_hold", dbg
            if self.active_cell is None:
                # v5 forced exit above: skip the miss logic and
                # fall through to a fresh decision this same call.
                pass
            elif self.active_miss + 1 < FIGHT_EXIT_MISSES:
                # The mix failed: the fight is fading, so the
                # extension is gone too (no motion to measure).
                self.active_high_streak = 0
                fresh = fight_cells(grid, self.prev_grid,
                                    cooling,
                                    self.focus_colours, dt_s,
                                    self.military_state)
                ff, _ = split_fights(fresh, self.focus_colours)
                if (self.focus_colours is not None
                        and not _is_focus_cell(cell, self.focus_colours)
                        and ff):
                    total, fr, fc, fcell = ff[0]
                    # Previous-scan cell FIRST: prev_grid is
                    # reassigned below, and the motion flag must
                    # compare against the previous scan, not this one.
                    prev_cell = (self.prev_grid[fr][fc]
                                 if self.prev_grid is not None else None)
                    self.prev_grid = grid
                    dbg = {"cell": (fr, fc), "colours": fcell,
                           "pixels": total, "focus": True,
                           "switched": True, "focus_preempt": True}
                    _annotate_fight(dbg, fcell, self.focus_colours,
                                    prev_cell, self.military_state)
                    reason, dbg = self._classify_fight((fr, fc), fcell, dbg, now_s=now_s)
                    pt = self._point(fr, fc)
                    self.last_point = pt
                    return pt, reason, dbg
                if fresh:
                    total, fr, fc, fcell = fresh[0]
                    if total >= self.active_last_total + FIGHT_SWITCH_MARGIN:
                        # Previous-scan cell FIRST: prev_grid is
                        # reassigned below, and the motion flag must
                        # compare against the previous scan, not this one.
                        prev_cell = (self.prev_grid[fr][fc]
                                     if self.prev_grid is not None else None)
                        self.prev_grid = grid
                        dbg = {"cell": (fr, fc), "colours": fcell,
                               "pixels": total, "switched": True}
                        _annotate_fight(dbg, fcell, self.focus_colours,
                                        prev_cell, self.military_state)
                        reason, dbg = self._classify_fight((fr, fc), fcell, dbg, now_s=now_s)
                        pt = self._point(fr, fc)
                        self.last_point = pt
                        return pt, reason, dbg
                # v5: the hold cap bounds grace holds too — a cell
                # already held to the cap does not earn a grace
                # step on top of it.
                if self.active_holds >= self._hold_cap():
                    forced_exit = {"cell": (r, c), "why": "hold_cap",
                                   "holds": self.active_holds,
                                   "cap": self._hold_cap()}
                    self._clear_active()
                else:
                    self.active_miss += 1
                    self.active_holds += 1
                    pt = self._point(r, c)
                    self.last_point = pt
                    self.prev_grid = grid
                    return pt, "fight_hold", {
                        "cell": (r, c), "colours": dict(cell),
                        "pixels": sum(cell.values()),
                        "misses": self.active_miss, "grace": True,
                        "focus": _is_focus_cell(cell, self.focus_colours)}
            else:
                self.fight_cooldowns[(r, c)] = now_s
                cooling.add((r, c))
                self._clear_active()
        # 2. Fresh decision (no active fight): v4 order in
        #    choose_target — focus fight, focus attention, focus
        #    base check, opponent fight, capped relevant opponent
        #    base, sweep (v6: the old "hold" is gone — a quiet step
        #    tours on). A v5 forced exit lands here in the same
        #    call, flagged on the debug record so the log shows WHY
        #    the camera left the cell.
        if forced_exit is not None:
            fcell = forced_exit.get("cell")
            if fcell is not None:
                self.fight_cooldowns[fcell] = now_s
                cooling.add(fcell)
        rotation_due = (self.last_rotation_t is None
                        or now_s - self.last_rotation_t >= ROTATION_EVERY_S)
        pt, reason, debug = choose_target(
            grid, self.diamond, self.screen_w, self.screen_h,
            self.rotation_index, rotation_due, self.sweep_index,
            self.prev_grid, self.player_map, cooling,
            active_cell=None, last_point=self.last_point,
            focus_colours=self.focus_colours,
            base_check_index=self.base_check_index,
            base_visits=self.base_visits,
            opponent_base_visits=self.opponent_base_visits,
            dt_s=dt_s, military=self.military_state,
            centroids=self._centroids, attack_watch=self._attack_watch)
        # v15: filter out thin fight suspects (scouting/patrols).
        # A fresh fight without immediate drop evidence must have total >= 60
        # and second >= 15 to justify a suspect visit. Otherwise cool down the cell
        # and re-choose target so camera prioritizes base checks or real action.
        while reason == "fight":
            drop = self._combat_drop
            has_drop = (drop is not None and drop.get("bucket") in debug.get("colours", {})
                        and drop["drop"] >= COMBAT_DROP_MIN)
            counts = sorted(debug.get("colours", {}).values(), reverse=True)
            second = counts[1] if len(counts) > 1 else 0
            total = debug.get("pixels", sum(counts))
            is_early_scout = self._phase_gated and not has_drop
            if is_early_scout or (not has_drop and (total < FIGHT_SUSPECT_MIN_PIXELS or second < FIGHT_SUSPECT_MIN_SECOND_PIXELS)):
                fcell = debug.get("cell")
                if fcell is not None:
                    self.fight_cooldowns[fcell] = now_s
                    cooling.add(fcell)
                pt, reason, debug = choose_target(
                    grid, self.diamond, self.screen_w, self.screen_h,
                    self.rotation_index, rotation_due, self.sweep_index,
                    self.prev_grid, self.player_map, cooling,
                    active_cell=None, last_point=self.last_point,
                    focus_colours=self.focus_colours,
                    base_check_index=self.base_check_index,
                    base_visits=self.base_visits,
                    opponent_base_visits=self.opponent_base_visits,
                    dt_s=dt_s, military=self.military_state,
                    centroids=self._centroids, attack_watch=self._attack_watch)
                continue
            break
        # v17: if choose_target fell back to sweep, tour registered focus bases instead
        if reason == "sweep":
            reg_bases = self._registered_bases()
            if reg_bases:
                n, r, c, bk = reg_bases[self.rotation_index % len(reg_bases)]
                cell = grid[r][c]
                prev_cell = (self.prev_grid[r][c]
                             if self.prev_grid is not None else None)
                if not _is_hot_fight_mix(cell, prev_cell, dt_s):
                    kind = BASE_CHECK_KINDS[self.base_check_index % len(BASE_CHECK_KINDS)]
                    name = (self.player_map or {}).get(bk)
                    debug = {"cell": (r, c), "colour": bk, "pixels": n,
                             "check": kind, "focus": True, "registry": True}
                    if name:
                        debug["player"] = name
                    pt = self._point(r, c, {bk})
                    reason = "base_" + kind
        if forced_exit is not None:
            debug = dict(debug)
            debug["forced_exit"] = forced_exit
        # v7: stamp the military state on the fresh decision so the
        # log shows why a fight was or was not allowed. The phase
        # gate is stamped independently: a phase-gated step carries
        # BOTH the stand-in military state and the phase_gated flag.
        if self.military_state.get("known"):
            debug = dict(debug)
            debug["military"] = _military_log(self.military_state)
        if self._phase_gated:
            debug = dict(debug)
            debug["phase_gated"] = True
        self.prev_grid = grid
        if reason == "fight":
            # v12: a fresh fight is a suspect until combat evidence
            # confirms it (or a drop in one of its buckets promotes
            # it outright). _classify_fight sets the active/suspect
            # state and stamps the combat_gate/combat_evidence
            # debug fields. The cell joins visited_fights either
            # way: a suspect had its one look.
            reason, debug = self._classify_fight(debug["cell"],
                                                 debug["colours"], debug,
                                                 now_s=now_s)
            self.last_point = pt
        elif reason in ("base_eco_check", "base_production_check",
                        "base_expansion_check"):
            self.rotation_index += 1
            self.last_rotation_t = now_s
            self.base_check_index += 1
            self.base_visits += 1
            self.last_point = pt
        elif reason == "base_opponent_check":
            self.rotation_index += 1
            self.last_rotation_t = now_s
            self.base_visits += 1
            self.opponent_base_visits += 1
            self.last_point = pt
        elif reason == "sweep":
            self.sweep_index += 1
            self.last_point = pt
        # "fight_hold", "base_under_attack" and "base_expansion"
        # leave rotation/check counters alone: attention is
        # event-driven, not rotation. (Attention visits do update
        # last_point below.)
        if reason in ("base_under_attack", "base_expansion"):
            self.last_point = pt
        return pt, reason, debug
