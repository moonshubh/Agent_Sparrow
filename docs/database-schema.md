# Database Schema

Last updated: 2026-02-12

> Supabase PostgreSQL + pgvector schema overview.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Schemas and Extensions](#2-schemas-and-extensions)
3. [Table Families (Quick Map)](#3-table-families-quick-map)
4. [Schema Reference](database-schema-reference.md)

---

## 1. Overview

### Database Architecture

Agent Sparrow uses **Supabase** (managed PostgreSQL) with:
- **pgvector** for embedding storage and similarity search (3072 dimensions)
- **Row Level Security (RLS)** on all application tables
- **JSONB** for flexible metadata storage
- **Automatic timestamps** via triggers

### Schema Organization

| Schema | Purpose |
|--------|---------|
| `public` | Application data (chat, FeedMe, LangGraph, KB, Zendesk) |
| `auth` | Supabase Auth system tables |
| `storage` | Supabase Storage metadata |
| `extensions` | PostgreSQL extensions |

---

## 2. Schemas and Extensions

### Installed Extensions

| Extension | Version | Purpose |
|-----------|---------|---------|
| `vector` | 0.8.0 | Vector embeddings and ANN indexes |
| `pg_trgm` | 1.6 | Trigram full-text search |
| `pg_stat_statements` | 1.11 | Query statistics |
| `uuid-ossp` | 1.1 | UUID generation |
| `pgcrypto` | 1.3 | Cryptographic functions |
| `btree_gin` | 1.3 | GIN support for common types |
| `hypopg` | 1.4.1 | Hypothetical indexes |
| `index_advisor` | 0.2.0 | Index recommendations |
| `pg_graphql` | 1.5.11 | GraphQL support |

---

## 3. Table Families (Quick Map)

Use this quick map to route into detailed table definitions in `docs/database-schema-reference.md`.

| Family | Detailed Section |
|--------|------------------|
| Chat system | `1.1` |
| FeedMe document processing | `1.2` |
| Knowledge base | `1.3` |
| LangGraph persistence | `1.4` |
| Zendesk integration | `1.5` |
| Global knowledge and feedback | `1.6` |
| Authentication and API keys | `1.7` |
| Workspace store | `1.8` |
| System tables | `1.9` |
| Vector search | `2` |
| Row-level security | `3` |
| Functions and triggers | `4` |
| Migration history | `5` |

## Additional References

- Full table-level schema details: `docs/database-schema-reference.md`
