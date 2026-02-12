# Technical Debt Tracker

Last updated: 2026-02-12

Track known debt, prioritize paydown, prevent compound interest.

---

## Active Debt

| ID | Domain | Description | Severity | Added | Owner |
|----|--------|------------|----------|-------|-------|
| TD-001 | Backend | mypy strict compliance blocked by pre-existing baseline | Medium | 2026-02-09 | — |
| TD-002 | Memory UI | Automated test coverage is weakest domain | High | 2026-02-12 | — |
| TD-003 | Zendesk | No automated E2E for ticket processing lifecycle | Medium | 2026-02-12 | — |
| TD-004 | Frontend | Ensure `docs/frontend-architecture.md` and `docs/frontend-reference.md` stay aligned with current component/path usage | Low | 2026-02-12 | — |
| TD-005 | Frontend | Chat component test coverage sparse | Medium | 2026-02-12 | — |

## Resolved Debt

| ID | Domain | Description | Resolved | How |
|----|--------|------------|----------|-----|
| — | FeedMe | Status-transition race condition | 2026-02-10 | Processing stays `processing` until downstream completion |
| — | FeedMe | Rate-limiter lifecycle under Celery | 2026-02-10 | Scoped to process+thread identity |
| — | Memory UI | Inline image resize freeze | 2026-02-09 | Pointer lifecycle cleanup guards |
| — | Memory UI | Feedback confidence step inconsistency | 2026-02-09 | Fixed 5% steps in UI + DB RPC |

## Paydown Cadence

- Review this tracker weekly during planning
- Each hardening sprint should target at least one High-severity item
- When debt is resolved, move to Resolved table with date and method
