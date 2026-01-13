---
name: kb-creator
description: Knowledge Base article creation skill. Use when user asks to create, draft, or write KB articles, documentation, or help content. Also activates for "document this feature" requests.
---

# KB Article Creator Skill

## Article Types

### 1. How-To Guide
**Purpose**: Step-by-step instructions for completing a specific task
**Structure**:
- Title: "How to [action] [object]"
- Brief overview (1-2 sentences)
- Prerequisites
- Numbered steps with screenshots
- Expected outcome
- Troubleshooting tips

### 2. Feature Explainer
**Purpose**: Capability overview with use cases
**Structure**:
- Title: "[Feature Name]: [What it does]"
- What it is (1 paragraph)
- Key benefits (bullet list)
- Use cases (2-3 scenarios)
- How to access/enable
- Related features

### 3. Troubleshooting Guide
**Purpose**: Problem diagnosis and resolution
**Structure**:
- Title: "Fix: [Error/Problem Description]"
- Symptoms (what user sees)
- Possible causes
- Solution steps (most likely first)
- When to contact support
- Prevention tips

### 4. FAQ Article
**Purpose**: Quick answers to common questions
**Structure**:
- Title: "[Topic] FAQ"
- Q&A pairs (most common first)
- Related articles
- Last updated date

## Standard KB Structure

```json
{
  "title": "Clear, searchable title with key terms",
  "summary": "2-3 sentence overview that appears in search results",
  "prerequisites": [
    "List of things user needs before starting",
    "Account type requirements",
    "Required permissions"
  ],
  "steps": [
    "1. Navigate to Settings > [Section]",
    "2. Click [Button Name]",
    "3. Enter [required information]",
    "4. Click Save to confirm"
  ],
  "screenshots": [
    "[Screenshot: Settings menu location]",
    "[Screenshot: Dialog with fields highlighted]",
    "[Screenshot: Success confirmation]"
  ],
  "notes": [
    "Important callouts or warnings",
    "Platform-specific differences"
  ],
  "related_articles": [
    "Link to related how-to",
    "Link to troubleshooting if applicable"
  ],
  "tags": [
    "feature-name",
    "category",
    "common-error-terms"
  ]
}
```

## Writing Guidelines

### Titles
- Start with action verb for how-tos: "Set up", "Configure", "Enable"
- Include key searchable terms
- Keep under 60 characters for SEO
- Avoid jargon in titles

### Steps
- One action per step
- Start each step with a verb
- Include the exact text of buttons/menu items in [brackets] or **bold**
- Number all steps sequentially
- Use sub-steps (a, b, c) for complex single steps

### Screenshots
- Capture only relevant portion of screen
- Use arrows/highlights to draw attention
- Include alt text for accessibility
- Blur any sensitive information
- Update when UI changes

### Notes and Warnings
Use callout boxes for:
- **Note**: Additional helpful information
- **Important**: Key information user shouldn't miss
- **Warning**: Potential data loss or security concerns
- **Tip**: Pro tips or shortcuts

## Image Placeholders

When creating KB articles, include placeholders for images that can be generated:

### For UI Mockups
```
[IMAGE: Screenshot of {specific screen} showing {specific element highlighted}]
Prompt for generation: "Generate a realistic screenshot of [app/UI] showing [feature] with [element] highlighted"
```

### For Workflow Diagrams
```
[DIAGRAM: Flowchart showing {process name}]
Prompt for generation: "Create a clean flowchart diagram showing [process] with steps: [list steps]"
```

### For Before/After Comparisons
```
[IMAGE: Before/After comparison of {feature}]
Prompt for generation: "Create a side-by-side comparison showing [before state] vs [after state]"
```

Use the image-generation skill to generate these images with Nano Banana Pro.

## Output Format

### Draft Mode (Default)
Generate as artifact for review before publishing:

```markdown
::artifact{type="markdown" title="KB Draft: [Article Title]"}

# [Article Title]

## Overview
[Summary paragraph]

## Prerequisites
- [Prerequisite 1]
- [Prerequisite 2]

## Steps
1. [First step]
2. [Second step]
...

## Related Articles
- [Related 1]
- [Related 2]

## Tags
`tag1` `tag2` `tag3`
```

### Review Checklist
Before finalizing any KB article, verify:

- [ ] Title is clear and searchable
- [ ] Summary explains what article covers
- [ ] Prerequisites are complete
- [ ] Steps are in logical order
- [ ] Each step has one action only
- [ ] Screenshots/images are identified
- [ ] Related articles are linked
- [ ] Tags include key search terms
- [ ] No jargon without explanation
- [ ] Tested by following steps yourself

## KB Article Templates

### Quick How-To Template
```markdown
# How to [Action] [Object]

[One sentence explaining what this achieves]

## Steps
1. [Action] [where/what]
2. [Action] [where/what]
3. [Action] to confirm

## Notes
- [Any important callout]

**Related**: [Link to related article]
```

### Troubleshooting Template
```markdown
# Fix: [Error Message or Problem]

## Symptoms
You may see this error when [context]:
- [Symptom 1]
- [Symptom 2]

## Solution
1. [Most likely fix first]
2. [Alternative if step 1 doesn't work]
3. [Last resort option]

## Still Having Issues?
Contact support with:
- Your error message
- Steps you've already tried
- [Any relevant details]
```

## Integration with FeedMe

KB articles created through this skill can be:
1. Saved as drafts in the artifact panel
2. Reviewed and edited by content team
3. Published to mailbird_knowledge via FeedMe ingestion
4. Auto-tagged for searchability
