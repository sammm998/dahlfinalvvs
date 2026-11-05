# Dahl: what it is, what it costs, and where the AI actually sits

A reference for two readers at once. Part I is the business picture — what the thing does, what a drawing
costs us to run, what a customer pays, and where the margin comes from. Part II is the engineering underneath
it, in the detail a developer needs.

Every number here is measured, and each one says where it was measured. Nothing is estimated silently. Where a
figure is unvalidated, it is marked unvalidated.

---

# Part I — The business picture

## 1. What it is, in one page

Dahl reads a Swedish HVAC pipe drawing and produces a quantity take-off: how many metres of each pipe
designation the drawing contains, with the evidence for every metre kept.

An estimator uploads a vector PDF. The system reads the sheet's own designation list, follows each leader line
to the pipe it points at, walks that pipe through bends and branches, and measures it in the drawing's own
scale. What comes out is a table — designation, DN, count, horizontal, vertical, total, state — where every row
can be opened to show which label was read, which leader was followed, and which drawn strokes were measured.

One principle governs the whole engine, and it is the reason the product exists:

> **Ambiguous is a valid answer. Wrong certainty is not.**

A pipe is never named because a label happens to lie near it. Identity comes only from a leader line the
draughtsman actually drew. Where the drawing does not say, the reading says it does not say, and the row stands
as ambiguous rather than quietly becoming a number someone will price.

This matters commercially because the alternative failure mode is invisible. A take-off that is silently 8 %
short does not look wrong; it looks like a take-off. An estimator who cannot check it has to redo it.

## 2. What a drawing costs us to run

Measured over **296 sheets**, each read in its own process, with CPU time, peak memory, path count and model
questions recorded per sheet (`engine/tools/cost_run.py`; raw data in `results/2026-09-12-kostnad/`).

| | kr per sheet |
|---|---:|
| Median sheet | **0.03** |
| Sheets with open cases (39 % of them) | **0.45** |
| Mean across all sheets | **0.31** |
| Densest sheet measured (1 084 301 paths, 1 422 s CPU, 2 526 MB peak) | **6.36** |

Where the money goes, on a sheet that asks questions: **model calls ≈ 88 %, CPU ≈ 4 %, storage ≈ 8 %.** On the
median sheet — which asks nothing — it is essentially all CPU, and it is three öre.

The cost model is a least-squares fit over those sheets, not a guess:

```
CPU seconds   ≈ 17.4 + 1.47 per thousand paths      at 1.03 kr per used core-hour
questions     ≈ 1.7  + 0.048 per thousand paths     at ~0.105 kr per question, two readers
storage       ≈ 0.03 kr per sheet                   median 10 MB of output, twelve months
```

The core-hour price itself is an assumption made explicit: a 1 200 kr/month VM with 4 vCPU at 40 %
utilisation. All assumptions live in one place (`cost_report.ASSUMPTIONS`) so that changing one changes every
number that depends on it.

**The practical conclusion: a drawing costs us öre, not kronor.** The expensive sheets are the ones dense
enough to ask many questions, and they are rare.

## 3. What a customer pays, and the margin

Credits, priced per sheet by paper format, with a surcharge for ink-dense sheets:

| | credits |
|---|---:|
| A3, A2 | 1.0 |
| A1 | 2.0 |
| A0 | 3.0 |
| A0+ | 4.0 |
| Ink surcharge, per started 30 000 paths beyond the first | +0.5 (capped at 3.0) |
| A second look with vision, per page | 1.0 |
| A new account, to try with | 5.0 free |

| package | credits | kr | kr/credit |
|---|---:|---:|---:|
| Start | 25 | 249 | 9.96 |
| Kontor | 100 | 890 | 8.90 |
| Projekt | 500 | 3 900 | 7.80 |
| Storkund | 2 000 | 12 900 | 6.45 |

A typical A1 sheet is 2 credits ≈ 15–20 kr of revenue against ~0.03 kr of cost. **The gross margin per sheet
is roughly 97–98 %**, and that is the right conclusion rather than an arithmetic error: this is a compute
product whose marginal cost is a few seconds of one core. The real costs are development and support, which
are fixed, not per sheet.

A reading that produced no metres at all is refunded automatically, so a re-read with a hand-entered scale
costs the customer once. Everything around the reading — the project analysis, the costing and tender, the
measuring tool, the CAD room, exports and the academy — costs no credits.

### Three things that are wrong or unvalidated today

Stated plainly, because a margin table that hides them is worth less than one that does not:

1. **`llm_kr_per_question = 0.052` in `backend/app/credits.py` is a single-reader figure.** The panel now runs
   two readers, and the measured cost is **0.105 kr**. The admin margin table and
   `results/2026-09-12-kostnad/PRISSÄTTNING.md` therefore understate model cost by about 2× on that line. It
   does not change the conclusion — öre, not kronor — but it is not the measured number, and it should be
   corrected.
2. **A2 and A0 are priced but never measured.** The corpus is 284 A1 sheets, 11 A3 and one A0+; it contains no
   A2 and no A0 at all. Those two rows of both the price list and the margin table are unvalidated. The margin
   table also prices a typical A1 at 18 000 paths, where the measured A1 median is **11 661**.
3. **The conversational agent's model spend is unmetered and unpriced.** No credits call sits on any agent
   endpoint, while the pricing page advertises the surrounding tooling as included. Vision has no refund path
   either, and a refunded reading returns 100 % of the credits although the CPU and any model questions were
   already spent.

---

# Part II — How it is built

## 4. The tech stack, exactly

**Three processes, one boundary that holds.** The engine never imports the service; the service never reaches
into the engine's internals; the browser never computes a metre.

| | what | size |
|---|---|---|
| **Engine** | Python 3.11. `pymupdf`, `shapely`, `numpy`, `scipy` — four dependencies, and no more. | 68 modules, 20 228 lines |
| **Service** | FastAPI + SQLAlchemy 2 + Pydantic 2. SQLite (WAL) or PostgreSQL. | 30 modules, 13 927 lines, 39 tables |
| **Room** | React 18.3.1, Vite 5.4.6, TypeScript 5.5.4, react-router 6.26.2, pdfjs-dist 4.7.76, three 0.186.0, gsap, lenis. | 125 files, 26 735 lines |
| **Tests** | pytest. | 114 files, 13 928 lines, 807 tests |

One two-stage Docker image builds the web app and serves it from the API. One CI workflow runs the same
commands a developer runs. Deployment is Railway; the service reports its own persistence state at
`/api/version` so that the most common deployment mistake — a database in the container's own filesystem that
vanishes on the next deploy — announces itself instead of looking like an empty database.

The optional `rapidocr-onnxruntime` is the only extra, and it is off by default. See §7.

## 5. How a drawing is read

Twelve stages, in the order the engine actually runs them. Each names its module.

1. **Open as vectors** (`pdf/extract.py`) — every stroke with its pen, colour, layer and dash pattern. A
   scanned PDF is rejected with a reason: there is nothing to measure on pixels.
2. **Profile the sheet** (`profile/`) — which pens, text sizes, dash patterns, leader styles and pipe styles
   *this* sheet uses. Nothing is a fixed threshold for a drawing office's house style; it is derived per sheet.
3. **Rebuild the text** (`text/`) — where it is real text, read it; where CAD drew the letters as strokes,
   reassemble strokes into characters, characters into rows, rows into designations.
4. **Read the legend** (`semantics/legend.py`) — system codes, materials, components, line types. Used where
   present; the reading works when it is absent, incomplete, or on another sheet.
5. **Designation and DN** (`semantics/grammar.py`) — the sheet's own grammar for designations: where the
   dimension sits, how it is written, what is a pipe name and what is a room number.
6. **The real leader** (`semantics/leaders.py`) — for each designation, the leader line the draughtsman drew —
   straight, broken, in several parts — followed to its tip. Never nearest-distance.
7. **What the tip touches** (`semantics/attachment.py`) — a pipe, a marker, a fitting, or nothing. **A contact
   is not a connection until it is verified.**
8. **Follow the pipe** (`pipes/`) — through bends, branches, export gaps and dash patterns, only across
   verified physical connections. A crossing is not a connection.
9. **Every stop gets a reason** (`pipes/frontier.py`) — sixteen reason codes, all written out. No pipe ends
   silently.
10. **Measure once** (`measure/`) — two parallel lines drawing one pipe are one pipe; doubled geometry is not
    counted twice. Scale comes from the title block, the scale bar or the dimensioning — never an assumption.
11. **Quantity with evidence** (`output/`) — designation, DN, count, horizontal, vertical, total, state.
    Vertical without a height statement is *unknown*, not zero.
12. **Review and correct** (the room) — the ambiguous stands apart. Corrections are saved as corrections; they
    never move a metre silently.

## 6. Where AI comes in, and where it is forbidden

This is the part most people get wrong about this system, in both directions.

**The measuring path contains no language model at all.** Every metre comes from geometry, leaders and rules
written in Python. Nothing in that path reaches the network. If you unplugged every model tomorrow, the engine
would still produce the same metres on the same drawings — the gate runs that measure accuracy are run with
the second reader **off**.

A model can appear at exactly four optional, key-gated points. None of them can produce a number.

**a. The second reader / panel** (`engine/tools/readers.py`). Only for cases the engine itself marked
AMBIGUOUS, and only among candidates the drawing put forward. The answer is verified character for character
against the candidate list, then checked again at the point of use. With two readers configured (Astra and
Claude), a case is settled **only when both name the same candidate**; if they disagree it stays ambiguous, and
that is the intended behaviour, not a failure. Measured worth: on a 33-sheet gate, its theoretical ceiling was
179.5 m of 6 245 m — **2.9 %**.

**b. Vision.** The page plus the reading's own overlay, with a grid the caller drew. The model may only name a
tile that the caller drew. It returns findings, never measurements: there is no `apply()`, and no path from a
finding to a quantity.

**c. The conversational agent.** The model chooses which tool to call; every number in the answer comes out of
the engine's artifacts. Twenty read-only tools, plus six `foresla_` ("propose") tools that propose and never
write. A figure without evidence becomes "it does not say so in the document set".

**d. OCR** (`rapidocr-onnxruntime`) — the only trained artefact anywhere in the system, third-party, off by
default. Used as an independent cross-check of the text and to name characters the stroke recogniser could
not. Measured on three sheets: 0 of 59, 0 of 30 and 3 of 24 unknown characters resolved; quantities identical
in all three; ~16 s per sheet.

### The part that looks like machine learning and is not

Character recognition on CAD drawings *looks* like the canonical ML problem, and it is not solved that way
here. There is **no trained model, no weights, and no sklearn, torch or tensorflow anywhere in the repository.**

What actually happens: the sheet's stroked letters are assembled into glyph shapes, and each shape is compared
by **chamfer matching** against reference alphabets rendered procedurally — Hershey simplex and duplex, the
PDF base-14 skeletons (Helvetica, Courier, Times), and, when the PDF embeds its own font, that font's own
outlines. A match below an explicit distance threshold (`UNKNOWN_THRESHOLD = 0.14`) is accepted; anything above
it becomes `?` and stays `?`. An unknown character is never repaired from an expected word.

The consequence is the point: the recogniser has no training distribution to be outside of, and no confidence
score that drifts. It either matches a shape the drawing itself contains, or it says it does not know.

The route agents and review agents are likewise deterministic Python. The judge that arbitrates between them
explicitly calls no model.

## 7. How the learning works — and why it is not training

Corrections do teach the system, under a rule narrow enough to state in a sentence:

> A lesson may do exactly one thing: settle a case the engine **itself** marked ambiguous, in favour of an
> answer a human already gave in the same situation, among candidates the drawing itself offers.

"The same situation" is not a similarity score. It is an exact match on a six-part fingerprint, all six parts
read from the drawing: the pen the geometry is drawn with, how the sheet draws its leader, the reason the
engine gave for stopping, the *shape* of the designation (letters and punctuation, not the digits), the local
topology as three counts, and the shape of the candidate set. Fewer than six is not the same situation — two
sheets that merely resemble each other are two different drawings.

A lesson may never create a stretch, never name geometry no leader reached, never change something the engine
is certain about, and never outvote the drawing. A situation answered two different ways by two people is
**dropped, not majority-voted.**

That is why it is not training: there is no gradient, no distribution, no generalisation beyond an exact
fingerprint match. It is a memo, not a model.

**What a human cannot teach it today** — and this is where the next work is:

| | metres | teachable today |
|---|---:|---|
| ambiguous cases (bundles, stacked labels) | 442 | **yes** — this is exactly what the lesson is for |
| unowned geometry drawn in the right pen | 1 520 | no — no ambiguous case to attach to |
| rows that are too long or too short | 3 125 (net 582) | no — the engine is certain |

A human can therefore see an error the system cannot learn from. Correcting an ambiguous case is worth much
more than correcting a confident one, and the interface should say so.

## 8. How we know it works

59 sheets with known reference quantities, measured three ways:

| instrument | what it compares |
|---|---|
| `facit_metrics.py` | row against row — metres per designation against the reference |
| `pipe_audit.py` | run against pipe — every measured stretch against every physical pipe |
| `markup_metrics.py` | stretch against stretch — the estimator's own measuring lines, on the marked drawings |

Current state (gate76, 59 sheets, 11 399 reference metres):

```
COVERAGE 79.19 %   FALSE OWNERSHIP 15.70 %   DESIGNATION RECALL 87.72 %   PRECISION 78.45 %
extent: FULL 177 · PARTIAL 197 · OVER 174 · MISSED 154 · WRONG 86   (of 788 rows)
```

**The discipline matters more than the numbers.** Every change is run blind across the whole corpus first, the
source is frozen and hashed, and only then is the reference opened. The reference may be used for validation,
root-cause analysis and generalisation testing — never inside detection logic. A contamination scanner walks
every production module before each run and refuses if any of the reference's vocabulary has leaked in.

The discipline has teeth: **four of the last seven changes were reverted for measuring worse.** Two proposed
rules were tested against the marked drawings and rejected — counting hatched metres (the estimator measures
0.1–1.2 % of their metres inside hatching, so excluding them is right), and letting an unowned chain take its
single named neighbour's name (right on 38.7 % of the metres, wrong on 54.7 %).

## 9. What it does not do

Cross-referenced in full in [`LIMITATIONS.md`](LIMITATIONS.md). The short list: no scanned drawings; no
invented vertical metres without a height statement; no DN transition without drawn evidence; no split of a
shared run between the codes that share it; no bridging of a gap in a curved dashed line; and no bundle label
resolved when the drawing gives nothing to resolve it with.

---

*Swedish companions: [`SYSTEMET.md`](SYSTEMET.md) (the system in full), [`ARCHITECTURE.md`](ARCHITECTURE.md),
[`INLARNING.md`](INLARNING.md) (learning and the human in the loop), [`SPRAK.md`](SPRAK.md) (the glossary this
document's terminology comes from), [`RAILWAY.md`](RAILWAY.md) (deployment).*
