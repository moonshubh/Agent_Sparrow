# Contributing Guidelines

Last updated: 2026-02-12

---

## Commit Messages

- **Short, imperative, scoped** — describe what the commit does
- **Use conventional prefixes** (required for Release Please automation):

| Type | Description | Version Bump |
|------|-------------|--------------|
| `feat` | New feature | Minor (0.x.0) |
| `fix` | Bug fix | Patch (0.0.x) |
| `feat!` or `fix!` | Breaking change | Major (x.0.0) |
| `refactor` | Code restructuring | Patch |
| `perf` | Performance improvement | Patch |
| `docs` | Documentation only | None |
| `test` | Adding tests | None |
| `chore` | Maintenance | None |
| `ci` | CI/CD changes | None |

- **Use scopes** to organize the changelog:

```
feat(zendesk): add ticket tagging functionality
fix(auth): resolve token refresh race condition
refactor(middleware): simplify rate limiting logic
docs(api): update endpoint reference
```

Common scopes: `zendesk`, `agent`, `frontend`, `auth`, `api`, `feedme`, `middleware`, `memory`

---

## Pull Request Checklist

- [ ] Concise description of changes
- [ ] Linked issue/ticket (if applicable)
- [ ] Tests pass: `pnpm test`, `pytest`
- [ ] Linting passes: `pnpm lint`, `ruff check .`
- [ ] Type checking passes: `pnpm typecheck`, `mypy app/`
- [ ] Screenshots/GIFs for UI changes
- [ ] Environment/migration impacts documented
- [ ] Docs artifacts refreshed if deps/models changed: `python scripts/refresh_ref_docs.py`
- [ ] Docs consistency passes: `python scripts/validate_docs_consistency.py`
- [ ] Changes focused (avoid unrelated modifications)

---

## Branch Naming

Use descriptive branch names with a prefix:

```
feat/add-user-auth
fix/session-race-condition
refactor/extract-json-helpers
docs/update-architecture
```

---

## Decision Capture

When making architectural decisions, add a record to `docs/design-docs/`:

```markdown
## Decision: [Title]
**Date**: YYYY-MM-DD
**Context**: What prompted this decision
**Decision**: What we chose
**Rationale**: Why this over alternatives
**Status**: Active | Superseded by [link]
```

---

## Release Workflow

Agent Sparrow uses **GitHub Flow** with **Release Please** for automated changelog generation.

### Flow

```
main (protected, always deployable)
  ├── Create feature branch → Make commits → Push & Open PR
  ├── Review & Merge PR (squash recommended)
  ├── Release Please creates/updates "Release PR"
  └── Merge Release PR when ready → Version tag + CHANGELOG + Railway deploy
```

### Step-by-Step

1. **Start**: `git checkout main && git pull && git checkout -b feature/my-feature`
2. **Commit**: Use conventional commits (see table above)
3. **Push**: `git push -u origin feature/my-feature` → Open PR on GitHub
4. **Merge**: Squash and merge (clean linear history)
5. **Release PR**: Release Please auto-creates — accumulates changes across PRs
6. **Release**: Merge the Release PR when ready to cut a release

### Version Files (auto-updated by Release Please)

| File | Purpose |
|------|---------|
| `frontend/package.json` | Frontend version field |
| `app/__version__.py` | Python-accessible version |
| `CHANGELOG.md` | Human-readable release notes |
| `.release-please-manifest.json` | Release Please version tracking |

### Configuration Files

| File | Purpose |
|------|---------|
| `release-please-config.json` | Changelog sections, extra files |
| `.release-please-manifest.json` | Current version tracker |
| `.github/workflows/release-please.yml` | GitHub Action workflow |

### Manual Version Override

```bash
git commit --allow-empty -m "chore: release 2.0.0" -m "Release-As: 2.0.0"
git push origin main
```

---

## Feedback Loop

Per our [core beliefs](core-beliefs.md), every bug, review comment, or user complaint should become at least one of:

1. A **documentation update** in `docs/`
2. A **test case** preventing recurrence
3. A **lint rule** or CI check enforcing the fix

The loop: `observe → capture → encode → enforce`
