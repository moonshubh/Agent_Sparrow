# Core Beliefs — Agent-First Operating Principles

Last verified: 2026-02-12

These principles govern how we build and maintain Agent Sparrow. They are stable
and change infrequently. When a decision conflicts with a core belief, the belief
wins unless explicitly overridden in a design doc.

---

## 1. Agents execute, humans steer

Agents (Codex, Claude Code) write and modify code. Humans specify intent, validate
outcomes, and design the environments that make agent work reliable. When an agent
struggles, the fix is never "try harder" — it's "what capability, context, or
constraint is missing?"

## 2. Repository is the single source of truth

Anything not in the repository effectively doesn't exist for agents. Decisions
made in Slack, meetings, or mental models must be captured in `docs/` or code
comments. Knowledge in people's heads is illegible to the system.

## 3. AGENTS.md is a map, not an encyclopedia

Keep AGENTS.md short (~150-200 lines). It serves as a table of contents pointing to
deeper sources of truth in `docs/`, code, and schemas. Giant instruction files
crowd out the task, rot fast, and become non-guidance.

## 4. Progressive disclosure over upfront overload

Agents start with a small, stable entry point (AGENTS.md) and follow pointers to
deeper docs only when relevant. Don't inject everything into context — let agents
navigate intentionally to what they need.

## 5. Enforce boundaries, allow autonomy within them

Strict rules at architectural boundaries (API contracts, dependency directions,
security, type safety). Freedom in implementation details within those boundaries.
This mirrors platform engineering: enforce centrally, execute locally.

## 6. Prefer boring technology

Composable, stable, well-documented tools (FastAPI, Next.js, Supabase, LangGraph)
are easier for agents to model. When evaluating dependencies, favor libraries with
stable APIs and strong training-data representation over cutting-edge alternatives.

## 7. Encode taste into tooling, not instructions

When documentation falls short, promote the rule into code (linters, CI checks,
type constraints). Human taste is captured once and enforced continuously on every
line of code, rather than relying on agents to remember prose.

## 8. Corrections are cheap, waiting is expensive

With high agent throughput, short-lived PRs and follow-up fixes are preferable to
blocking merge gates. Fix forward, don't block on perfection.

## 9. Technical debt is a high-interest loan

Pay it down continuously in small increments (hardening sprints, cleanup PRs)
rather than letting it compound. Bad patterns spread fast in agent-generated code
because agents replicate existing patterns.

## 10. Feedback loops close the gap

Review comments, bug reports, and user feedback must flow back into the repository
as documentation updates, test cases, or tooling rules. The loop is:
`observe → capture → encode → enforce`.

---

## Verification

| Belief | Last verified | Verified by |
|--------|--------------|-------------|
| 1. Agents execute, humans steer | 2026-02-12 | Harness engineering adoption |
| 2. Repo is source of truth | 2026-02-12 | CLAUDE.md + AGENTS.md review |
| 3. AGENTS.md as map | 2026-02-12 | Restructured per OpenAI guidance |
| 4. Progressive disclosure | 2026-02-12 | New doc structure adopted |
| 5. Enforce boundaries | 2026-02-12 | Existing strict TS + ruff checks |
| 6. Boring technology | 2026-02-12 | Stack review (FastAPI/Next/Supa) |
| 7. Encode taste into tooling | 2026-02-12 | Existing lint + CI pipeline |
| 8. Corrections are cheap | 2026-02-12 | PR velocity confirms |
| 9. Debt as high-interest loan | 2026-02-12 | Hardening sprints pattern |
| 10. Feedback loops | 2026-02-12 | New workflow adopted |
