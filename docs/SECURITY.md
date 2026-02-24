# SECURITY

Last updated: 2026-02-23

## Security Baseline

- No secrets in repository.
- Validate untrusted inputs at every boundary.
- Enforce authn/authz checks on protected mutations.
- Use parameterized DB operations.
- Keep logs free of secrets and sensitive user data.

## Mandatory Review Requirement

Every task must include a dedicated security review pass using the
`security-best-practices` skill as part of the 3-pass review loop.

## Minimum Verification Checklist

- [ ] Auth and authorization behavior unchanged or explicitly migrated
- [ ] No new data leakage paths in APIs/logs/events
- [ ] Sensitive config keys handled safely
- [ ] New endpoints covered by at least smoke-level contract checks
- [ ] Findings recorded in review reports

## Internal Diagnostics

- `/security-status` is treated as an internal diagnostics endpoint and requires
  `X-Internal-Token`.
- Do not expose diagnostics endpoints anonymously in production.

## Related

- `docs/reviewers/security-reviewer.md`
- `scripts/harness/review_loop.py`
