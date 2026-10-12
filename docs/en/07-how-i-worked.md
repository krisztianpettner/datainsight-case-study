**English** · [Magyar](../hu/07-how-i-worked.md) · [↑ README](../../README.md)

# How I worked — the shepherd role

> **In one sentence:** AI agents wrote the code; my job was to decide where it should go, to fence
> the field, and to check — every day, against evidence — that it went there.

## The division of labour

| who | did what |
|---|---|
| **AI agents** (Claude: a lead model, a coding model, fast scout models) | wrote the code, the tests and most of the documents; searched the codebase; drafted plans; reviewed each other |
| **me** | designed the architecture — first of all the pipeline bridge across the three machines; set the goal of the day, the constraints that must never break, and the gates every change had to pass; made the decisions; read the evidence; said no |

The agents typed the 249,000 lines. The design they implement is mine, and I am accountable for
every one of them — that is the role this repository documents.

## What I decided myself

| decision | where it lives |
|---|---|
| the three-machine pipeline bridge: public relay → NAS hand-over → on-prem processing → masked status back, with no inbound API to the PC | [Data path](03-data-path.md#the-bridge--how-it-fails-safely), ADR-14 |
| the tax-authority QR code as the oracle, and *never guess* — a missing value beats a wrong one | [Parsing engine](02-parsing-engine.md), ADR-02, ADR-05 |
| a per-field identity gate, strict first, loosened only on measured evidence | `src/parsing/identity/`, ADR-06 |
| the owner pays, the accountant uses it free and earns no commission | [Two-sided product](05-two-sided-product.md), ADR-10 |
| refactor only behind a bit-exact baseline; record "designed vs built" in every chapter | [Platform](04b-platform.md), every chapter |
| the PII gate applies to the AI that builds the system | ADR-12 |

## The five things the shepherd holds

| | what it meant in practice |
|---|---|
| **Direction** | Every session opened with a *main focus* (the strategic goal) and a *sub focus* (today's task), plus what must not be touched today and what "done" means. Each change was checked against both. |
| **Constraints** | A written constitution: no cloud processing, the owner pays and the accountant does not, zero tolerance on tenant isolation, pilot first. Plus code rules: never delete features to fix an error, never weaken a test to make it pass, destructive database operations only with explicit confirmation. |
| **Gates** | Mechanical checkpoints instead of good intentions — see below. |
| **Review** | A *devil's advocate* agent reviewed plans before coding and changes before commit; a *contract* agent compared frontend calls with backend endpoints; a *legal* agent reviewed anything touching personal data. |
| **Measurement** | Claims became facts only when measured — and the measurement itself was audited (see [Metrics](08-metrics.md)). |

## Gates — enforced by the tooling, not by memory

Discipline that depends on remembering wears out. So the rules that mattered most were moved into
the tools:

- **The day-opening gate.** A hook blocked every code edit, every commit and every outbound send
  until the opening routine had run: current state, recent commits, yesterday's recommendation,
  memory-index health. The gate decides from a seal, not from "I've read it".
- **The PII gate.** Client invoice content never reached a model — not pasted, not as a file, not
  through a sub-agent. Debugging used pseudonymised copies only.
- **The layering rule for new routes,** with a devil's-advocate review at plan time and again
  before commit.
- **Pre-commit documentation check:** every design document must carry status, type, owner and a
  review date.
- **Recall from my own words.** On every message a hook searched ~300 decision and lesson notes for
  what was relevant and put it in front of the agent — as a *hint to verify*, never as evidence.

## Memory — so that nothing is decided twice

| layer | what it held |
|---|---|
| state files | where we are, what is pending — read head-first, every session |
| itineraries | the plan for tomorrow, ending with "**I recommend**" — the next session starts from it instead of re-asking |
| session logs | 182 dated logs: decisions, files, test results |
| decision & lesson notes | ~300: 116 lessons about *how to work*, 149 project facts, 34 references |
| architecture documents | 70, each with status and a review date |
| knowledge-base indexes | generated maps of documents, code and test data, so an agent looks things up instead of reading 1,000 files |

## Skills — repeatable procedures, written once

Nine project skills turned recurring work into procedures with fixed steps and fixed outputs, so
results from different days could be compared: the confidence-gate change protocol (with the
golden set run on every change), the eight-phase failure lab for the parsing engine, the
feature-to-data-model harmonisation survey, a cold-start QA run with Portuguese personas, three
outreach routines (daily check, list building, send day), a code-review checklist, and the
development workflow itself.

## Lessons about leading AI agents

These became written rules because each one cost something first.

1. **Label every brake.** When I hesitate, the reason must be named: *measured* (there is
   evidence — stop), *missing* (we don't know — go, and measure), or *rule* (a written rule —
   obey or change it consciously). An unlabelled "let's be careful" carries no information.
2. **A sub-agent's verdict is a hypothesis.** Scouts search by text; they cannot tell live code from
   dead code. Twice a scout declared an unused path "active". Findings are checked against the source.
3. **Falsify before fixing.** For every finding, write down what would disprove it — and look for that first.
4. **A silent zero lies.** A query against the wrong database returns zero rows and looks like
   success. A scan with the wrong method finds zero open ports. Zero needs its own proof.
5. **Half-wired is dead.** The most expensive pattern of the project: a feature built but never
   connected end to end, working in tests and absent in production.
6. **An underpowered experiment is not a negative result.** 120 delivered first contacts and no reply says "too
   small to tell", not "the message is wrong".
7. **Read first, code second.** The fastest way to break a mature system is to change it before
   reading what it already does.

## What I would tell another architect leading AI agents

- Write the constraints down before the first prompt; the agents will optimise for whatever you leave out.
- Move every rule that matters into a gate. Your attention is the scarcest resource on the team.
- Keep a record of *why*, not only of *what* — the agents forget, and so will you.
- Measure the measurement.
