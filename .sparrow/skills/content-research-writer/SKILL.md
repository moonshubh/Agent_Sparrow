---
name: content-research-writer
description: Assists in writing high-quality content by conducting research, adding citations, improving hooks, and providing section-by-section feedback. Use when writing comprehensive KB articles, blog posts, or documentation that requires research backing.
---

# Content Research Writer Skill

## Overview

Research-backed content writing assistant that helps produce well-sourced, engaging content with proper citations and structured feedback. Designed for creating high-quality KB articles and documentation.

## When to Use

- Write comprehensive KB articles with citations
- Create blog posts and product documentation
- Improve existing content quality
- Research topics thoroughly before writing
- Add credibility through proper sourcing

## Content Creation Workflow

### Phase 1: Research

```markdown
## Research Brief

**Topic**: [Article topic]

**Target Audience**:
- Technical level: [Beginner/Intermediate/Advanced]
- Role: [End user/IT Admin/Developer]
- Primary question they want answered:

**Research Objectives**:
1. Understand current best practices
2. Find authoritative sources
3. Identify common misconceptions
4. Gather supporting data/statistics

**Sources to Check**:
- [ ] Official documentation
- [ ] Industry publications
- [ ] Competitor approaches
- [ ] User forums/communities
- [ ] Academic/technical papers
```

### Phase 2: Outline

```markdown
## Content Outline

**Working Title**: [Title]

**Hook/Opening**:
[One compelling sentence that captures attention]

**Key Takeaways** (reader should learn):
1.
2.
3.

**Structure**:

### Introduction
- Hook
- Problem statement
- Promise (what they'll learn)

### Section 1: [Topic]
- Key point
- Supporting evidence
- Example

### Section 2: [Topic]
- Key point
- Supporting evidence
- Example

### Section 3: [Topic]
- Key point
- Supporting evidence
- Example

### Conclusion
- Summary of key points
- Call to action
- Next steps
```

### Phase 3: Draft with Citations

```markdown
## Draft Template

# [Title]

[Hook sentence that addresses the reader's pain point]

[Problem statement: Why this matters to the reader]

In this article, you'll learn:
- Point 1
- Point 2
- Point 3

## [Section 1 Heading]

[Opening sentence for section]

[Key information with source] [^1]

[Supporting detail or example]

> "Relevant quote if available" - Source

[Transition to next point]

---

## References

[^1]: Author/Organization. "Title." Source, Date. URL
[^2]: ...
```

## Hook Improvement Patterns

Transform weak openings into compelling hooks:

| Weak | Strong |
|------|--------|
| "This article explains..." | "Every day, [user type] waste X hours on [problem]..." |
| "Email is important..." | "The average professional spends 28% of their workday in email..." |
| "Here's how to..." | "What if you could [desirable outcome] in half the time?" |
| "Let me tell you about..." | "[Surprising statistic or fact] And it's costing you [impact]." |

### Hook Templates

```markdown
## Hook Patterns

**Problem-Solution**:
"[Pain point] affects [who]. Here's [solution] that [benefit]."

**Statistic Lead**:
"[Surprising number] - that's [what it means]. Here's why it matters."

**Question Hook**:
"What if [desirable outcome] was possible? [Bridge to solution]"

**Story Hook**:
"When [relatable scenario] happened, [consequence]. Here's what we learned."

**Contrarian Hook**:
"Everyone says [common belief]. But [counterpoint that intrigues]."
```

## Section-by-Section Feedback

For each section, evaluate:

```markdown
## Section Review: [Section Title]

**Clarity** (1-5):
- Is the main point clear?
- Any jargon that needs explanation?

**Evidence** (1-5):
- Are claims supported?
- Sources credible and cited?

**Flow** (1-5):
- Does it follow from previous section?
- Does it lead to next section?

**Engagement** (1-5):
- Examples concrete and relatable?
- Visuals or formatting helpful?

**Actionability** (1-5):
- Can reader apply this?
- Steps clear and complete?

**Suggestions**:
1.
2.
3.
```

## Citation Best Practices

### Citation Format

```markdown
## Citation Styles

**Inline Reference**:
According to [Source Name], "[quote or paraphrase]" [^1].

**Data Citation**:
Research shows that [finding] (Source, Year) [^2].

**Multiple Sources**:
This approach is recommended by multiple experts [^1][^2][^3].

**Self-Citation**:
As we discussed in [Related Article](link), ...

## References Section

[^1]: Last, First. "Article Title." *Publication*, Date. URL (accessed Date).
[^2]: Organization Name. "Document Title." Year. URL.
[^3]: Author. *Book Title*. Publisher, Year.
```

### Source Quality Checklist

```markdown
## Source Evaluation

- [ ] Author has relevant expertise
- [ ] Publication is reputable
- [ ] Date is recent (within 2-3 years for tech)
- [ ] Claims are verifiable
- [ ] No obvious bias or conflicts
- [ ] Consistent with other sources
```

## KB Article Template

```markdown
# [Article Title]

**Last Updated**: [Date]
**Applies To**: [Product versions, platforms]

## Overview

[One paragraph summary: What, Why, Who]

## Prerequisites

- [ ] Requirement 1
- [ ] Requirement 2

## Steps

### Step 1: [Action]

[Explanation of what this step accomplishes]

1. [Sub-step]
2. [Sub-step]

> **Note**: [Important consideration]

### Step 2: [Action]

[Continue pattern...]

## Troubleshooting

### Issue: [Common Problem]

**Symptoms**:
-

**Cause**:

**Solution**:
1.

## Related Articles

- [Related Topic 1](link)
- [Related Topic 2](link)

## References

[^1]: [Citation]
```

## Content Quality Checklist

```markdown
## Final Review Checklist

**Structure**
- [ ] Clear, descriptive title
- [ ] Compelling hook in first paragraph
- [ ] Logical section progression
- [ ] Strong conclusion with CTA

**Accuracy**
- [ ] Technical details verified
- [ ] Steps tested and confirmed
- [ ] Links working
- [ ] Citations accurate

**Readability**
- [ ] Jargon explained or avoided
- [ ] Sentences concise
- [ ] Paragraphs focused
- [ ] Formatting aids scanning

**SEO (if applicable)**
- [ ] Target keyword in title
- [ ] Keyword in first paragraph
- [ ] Headings descriptive
- [ ] Meta description written

**Polish**
- [ ] Grammar/spelling checked
- [ ] Consistent voice/tone
- [ ] Images have alt text
- [ ] Mobile-friendly formatting
```

## Quick Reference

| Phase | Key Output | Tools |
|-------|------------|-------|
| Research | Source list, key findings | Web search, docs |
| Outline | Structure, key points | Templates |
| Draft | Initial content | Writing |
| Review | Section feedback | Checklist |
| Polish | Final article | Grammar check |

## Integration with Agent Sparrow

- **KB Articles**: Research-backed support documentation
- **Product Updates**: Well-sourced release notes
- **How-To Guides**: Step-by-step with proper citations
- **Troubleshooting**: Evidence-based solutions

## Best Practices

1. **Research first** - Never write without sources
2. **One idea per paragraph** - Keep focused
3. **Show, don't tell** - Use examples
4. **Cite everything** - Build trust
5. **Revise ruthlessly** - Cut unnecessary words
