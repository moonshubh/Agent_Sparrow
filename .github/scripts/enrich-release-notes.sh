#!/usr/bin/env bash
# enrich-release-notes.sh
#
# Extracts CodeRabbit summaries from merged PRs since the last release tag
# and builds enriched release notes.
#
# Modes:
#   MODE=pr      — Update a release-please PR body (for human reviewers)
#   MODE=release — Update a GitHub release body (after release-please creates it)
#
# Required env vars:
#   GH_TOKEN       — GitHub token with repo + PR write scope
#   REPO           — owner/repo (e.g. moonshubh/Agent_Sparrow)
#   MODE           — "pr" or "release"
#
# Mode-specific env vars:
#   PR_NUMBER      — (MODE=pr) The release-please PR number to update
#   TAG_NAME       — (MODE=release) The release tag to update
#   VERSION        — (MODE=release) The version string
#
# Usage:
#   MODE=pr      PR_NUMBER=54 .github/scripts/enrich-release-notes.sh
#   MODE=release TAG_NAME=v0.2.3 VERSION=0.2.3 .github/scripts/enrich-release-notes.sh

set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${REPO:?REPO is required}"
: "${MODE:?MODE is required (pr or release)}"

# ---------------------------------------------------------------------------
# 1. Find the previous release tag
#    In MODE=release the newest tag is the one just created, so we need
#    the second entry. In MODE=pr the newest tag is the previous release.
# ---------------------------------------------------------------------------
if [ "$MODE" = "release" ]; then
  # Skip index 0 (the just-created release) and take index 1
  LAST_TAG=$(gh release list --repo "$REPO" --limit 2 --json tagName -q '.[1].tagName // empty' 2>/dev/null || echo "")
else
  LAST_TAG=$(gh release list --repo "$REPO" --limit 1 --json tagName -q '.[0].tagName // empty' 2>/dev/null || echo "")
fi

LAST_TAG_DATE="1970-01-01T00:00:00Z"
if [ -n "$LAST_TAG" ]; then
  LAST_TAG_DATE=$(gh release view "$LAST_TAG" --repo "$REPO" --json publishedAt -q '.publishedAt')
  echo "Previous release: $LAST_TAG ($LAST_TAG_DATE)"
else
  echo "::warning::No previous release tag found. Using all merged PRs."
fi

# ---------------------------------------------------------------------------
# 2. Collect merged PRs to main since the last release
#    Exclude release-please PRs via label filter
# ---------------------------------------------------------------------------
echo "Fetching merged PRs since ${LAST_TAG:-beginning}..."

# Fetch PRs as JSON, filter in jq for safety (no shell interpolation in bodies)
# Write to temp file to avoid echo corrupting JSON escape sequences in PR bodies
TMPDIR="${RUNNER_TEMP:-/tmp}"
RAW_PRS="$TMPDIR/release-prs-raw.json"
FILTERED_PRS="$TMPDIR/release-prs-filtered.json"
trap 'rm -f "$RAW_PRS" "$FILTERED_PRS" "$TMPDIR/release-notes.json" "$TMPDIR/release-body.md"' EXIT

gh pr list \
  --repo "$REPO" \
  --state merged \
  --base main \
  --limit 50 \
  --json number,title,mergedAt,body,labels > "$RAW_PRS"

# Filter in a separate jq call to avoid shell quoting issues with dates
jq --arg since "$LAST_TAG_DATE" '
  [.[] |
    select(.mergedAt > $since) |
    select((.labels | map(.name) | any(. == "autorelease: pending" or . == "autorelease: tagged")) | not)
  ] | sort_by(.mergedAt)
' "$RAW_PRS" > "$FILTERED_PRS"

PR_COUNT=$(jq 'length' "$FILTERED_PRS")
echo "Found $PR_COUNT merged PRs since last release"

if [ "$PR_COUNT" -eq 0 ]; then
  echo "No merged PRs found. Skipping enrichment."
  exit 0
fi

# ---------------------------------------------------------------------------
# 3. Extract CodeRabbit summaries using jq (safe from shell injection)
# ---------------------------------------------------------------------------
# Process all PRs in jq to avoid shell interpretation of PR body contents.
# jq extracts CodeRabbit sections and categorizes by title pattern.
NOTES_JSON=$(jq --arg repo "$REPO" '
  def extract_coderabbit_section(header):
    # Find lines between a **Header** and the next **Header** or end
    split("\n") as $lines |
    ($lines | to_entries | map(select(.value | test("\\*\\*" + header + "\\*\\*"))) | .[0].key // null) as $start |
    if $start == null then []
    else
      ($lines[$start+1:] | to_entries |
        # Only match indented bullets (not section headers like "* **Bug Fixes**")
        reduce .[] as $item (
          {items: [], done: false};
          if .done then .
          elif ($item.value | test("^\\* \\*\\*")) then .done = true
          elif ($item.value | test("^\\s+\\*")) then
            .items += [$item.value | gsub("^\\s+\\*\\s*"; "")]
          else .
          end
        ) | .items
      )
    end;

  def has_coderabbit:
    .body // "" | test("Summary by CodeRabbit");

  def coderabbit_block:
    (.body // "") |
    split("Summary by CodeRabbit") |
    if length > 1 then .[1] | split("end of auto-generated comment") | .[0]
    else ""
    end;

  def is_fix_title:
    .title | test("^[Ff]ix|[Bb]ug.?[Ff]ix|[Hh]otfix|[Ss]tabiliz");

  def is_feat_title:
    .title | test("^[Ff]eat|^[Aa]dd |^[Ii]mplement|^[Ii]ntroduce");

  def pr_ref:
    "([#\(.number)](https://github.com/\($repo)/pull/\(.number)))";

  def first_line_summary:
    (.body // "") | split("\n") | map(select(length > 0 and (test("^##|^<|^---") | not))) | .[0] // "";

  {features: [], bug_fixes: [], improvements: []} as $init |

  reduce (.[]) as $pr ($init;
    ($pr | has_coderabbit) as $has_cr |
    (if $has_cr then ($pr | coderabbit_block) else "" end) as $cr_block |

    # Extract CodeRabbit sections
    (if $has_cr then $cr_block | extract_coderabbit_section("New Features") else [] end) as $feat_items |
    (if $has_cr then $cr_block | extract_coderabbit_section("Bug Fixes") else [] end) as $fix_items |
    (if $has_cr then
      (($cr_block | extract_coderabbit_section("Improvements")) +
       ($cr_block | extract_coderabbit_section("Enhancements")))
    else [] end) as $improve_items |

    ($pr | is_fix_title) as $is_fix |
    ($pr | is_feat_title) as $is_feat |
    ($pr | pr_ref) as $ref |
    ($pr | first_line_summary) as $summary |

    # Categorize: use CodeRabbit sections if available, else use title pattern
    if ($feat_items | length > 0) then
      .features += [{
        title: $pr.title,
        ref: $ref,
        items: $feat_items
      }]
    elif $is_feat then
      .features += [{
        title: $pr.title,
        ref: $ref,
        summary: $summary
      }]
    else . end |

    if ($fix_items | length > 0) then
      .bug_fixes += [{
        title: $pr.title,
        ref: $ref,
        items: $fix_items
      }]
    elif ($is_fix and ($feat_items | length == 0)) then
      .bug_fixes += [{
        title: $pr.title,
        ref: $ref,
        summary: $summary
      }]
    else . end |

    if ($improve_items | length > 0) and ($is_fix | not) and ($is_feat | not) then
      .improvements += [{
        title: $pr.title,
        ref: $ref,
        items: $improve_items
      }]
    else . end |

    # Uncategorized: no CodeRabbit sections and no title pattern match → features
    if ($is_fix | not) and ($is_feat | not) and
       ($feat_items | length == 0) and ($fix_items | length == 0) and ($improve_items | length == 0) then
      .features += [{
        title: $pr.title,
        ref: $ref,
        summary: $summary
      }]
    else . end
  )
' "$FILTERED_PRS")

# ---------------------------------------------------------------------------
# 4. Format the notes as markdown (still in jq for safety)
# ---------------------------------------------------------------------------
NOTES_FILE="$TMPDIR/release-notes.json"
printf '%s' "$NOTES_JSON" > "$NOTES_FILE"

format_section() {
  local section_key="$1"
  local section_title="$2"
  jq -r --arg key "$section_key" --arg title "$section_title" '
    .[$key] as $items |
    if ($items | length) == 0 then ""
    else
      "\n### \($title)\n" +
      ([$items[] |
        if .items and (.items | length > 0) then
          "* **\(.title)** \(.ref)\n" +
          ([.items[] | "  - \(.)"] | join("\n"))
        elif .summary and (.summary | length > 0) then
          "* **\(.title)** — \(.summary) \(.ref)"
        else
          "* **\(.title)** \(.ref)"
        end
      ] | join("\n"))
    end
  ' "$NOTES_FILE"
}

FEATURES_MD=$(format_section "features" "Features")
FIXES_MD=$(format_section "bug_fixes" "Bug Fixes")
IMPROVEMENTS_MD=$(format_section "improvements" "Improvements")

# ---------------------------------------------------------------------------
# 5. Determine version and compose enriched body
# ---------------------------------------------------------------------------
if [ "$MODE" = "pr" ]; then
  : "${PR_NUMBER:?PR_NUMBER is required for MODE=pr}"
  VERSION=$(gh pr view "$PR_NUMBER" --repo "$REPO" --json title -q '.title' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "next")
  COMPARE_BASE="${LAST_TAG:-main}"
elif [ "$MODE" = "release" ]; then
  : "${TAG_NAME:?TAG_NAME is required for MODE=release}"
  : "${VERSION:?VERSION is required for MODE=release}"
  COMPARE_BASE="${LAST_TAG:-main}"
else
  echo "::error::MODE must be 'pr' or 'release'"
  exit 1
fi

ENRICHED_BODY=":robot: I have created a release *beep* *boop*
---

## [${VERSION}](https://github.com/${REPO}/compare/${COMPARE_BASE}...v${VERSION}) ($(date -u +%Y-%m-%d))
${FEATURES_MD}${FIXES_MD}${IMPROVEMENTS_MD}

---
This PR was generated with [Release Please](https://github.com/googleapis/release-please). Release notes enriched from [CodeRabbit](https://coderabbit.ai) PR summaries."

# ---------------------------------------------------------------------------
# 6. Apply the enriched body (write to file first to avoid shell quoting issues)
# ---------------------------------------------------------------------------
BODY_FILE="$TMPDIR/release-body.md"
printf '%s' "$ENRICHED_BODY" > "$BODY_FILE"

if [ "$MODE" = "pr" ]; then
  echo "Updating PR #${PR_NUMBER} with enriched release notes..."
  gh pr edit "$PR_NUMBER" --repo "$REPO" --body-file "$BODY_FILE"
  echo "Done. PR #${PR_NUMBER} updated."
elif [ "$MODE" = "release" ]; then
  echo "Updating release ${TAG_NAME} with enriched release notes..."
  gh release edit "$TAG_NAME" --repo "$REPO" --notes-file "$BODY_FILE"
  echo "Done. Release ${TAG_NAME} updated."
fi

# ---------------------------------------------------------------------------
# 7. Output the enriched body for downstream steps
# ---------------------------------------------------------------------------
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    echo "body<<ENRICHED_EOF"
    printf '%s\n' "$ENRICHED_BODY"
    echo "ENRICHED_EOF"
  } >> "$GITHUB_OUTPUT"
fi

echo "::notice::Release notes enriched with CodeRabbit summaries from $PR_COUNT PRs"
