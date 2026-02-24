# PLANS

Last updated: 2026-02-23

## Purpose

Execution planning is first-class and repository-native.

## Plan Lifecycle

- New work starts in `exec-plans/active/`.
- Completed plans move to `exec-plans/completed/`.
- Deferred low-severity findings and debt go to `exec-plans/tech-debt-tracker.md`.

## Required Plan Content

- Goal and scope
- Decision log
- Implementation checklist
- Test and validation criteria
- Rollout and rollback notes

## Review Integration

Every completed task must include review-loop output under `reports/reviews/` and,
if needed, debt records in `exec-plans/tech-debt-tracker.md`.
