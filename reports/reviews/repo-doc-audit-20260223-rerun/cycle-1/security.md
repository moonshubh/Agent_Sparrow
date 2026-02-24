# Security Review

Summary: Security checks found issues

| ID | Severity | Status | Path | Title |
|---|---|---|---|---|
| SEC-SECRETS-001 | high | open | ./.env.local | Potential committed secret file detected: ./.env.local |
| SEC-SECRETS-001 | high | open | ./.env | Potential committed secret file detected: ./.env |
| SEC-SECRETS-001 | high | open | ./frontend/.env.local | Potential committed secret file detected: ./frontend/.env.local |

## Raw Command Output

```text
{"summary": "Security checks found issues", "findings": [{"id": "SEC-SECRETS-001", "severity": "high", "title": "Potential committed secret file detected: ./.env.local", "path": "./.env.local", "status": "open"}, {"id": "SEC-SECRETS-001", "severity": "high", "title": "Potential committed secret file detected: ./.env", "path": "./.env", "status": "open"}, {"id": "SEC-SECRETS-001", "severity": "high", "title": "Potential committed secret file detected: ./frontend/.env.local", "path": "./frontend/.env.local", "status": "open"}]}
```
