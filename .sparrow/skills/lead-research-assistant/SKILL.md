---
name: lead-research-assistant
description: Identifies and qualifies high-quality leads by analyzing products, searching for target companies, and providing actionable outreach strategies. Use for enterprise customer research, competitive analysis, and market positioning.
---

# Lead Research Assistant Skill

## Overview

Research and qualification framework for identifying potential enterprise customers, analyzing competitors, and developing outreach strategies. Adapted for Agent Sparrow's business development support.

## When to Use

- Research potential enterprise customers for Mailbird
- Competitive analysis of email client market
- Market research for product positioning
- Generate outreach strategies for sales team

## Research Workflow

### 1. Company Discovery

```markdown
## Company Research Template

### Target Company: [Name]

**Basic Info**
- Industry:
- Size: (employees, revenue if public)
- Location: HQ and key offices
- Website:

**Technology Stack**
- Current email solution:
- Related tools: (CRM, productivity)
- Integration needs:

**Pain Points** (hypothesized)
- [ ] Email management at scale
- [ ] Multi-account handling
- [ ] Team collaboration
- [ ] Migration complexity

**Decision Makers**
- IT Director/CTO:
- Operations Lead:
- Procurement:
```

### 2. Qualification Framework

```markdown
## Lead Qualification Criteria

### BANT Assessment

**Budget**
- Company size indicates budget capacity: [Yes/No/Unknown]
- Industry typically invests in productivity tools: [Yes/No]
- Recent funding or growth signals:

**Authority**
- Identified decision makers: [Names/Titles]
- IT autonomy level: [Centralized/Distributed]

**Need**
- Current pain indicators:
- Public complaints about current solution:
- Growth trajectory requiring scalable solution:

**Timeline**
- Contract renewal timing (if known):
- Expansion plans:
- Urgency indicators:

### Score: [1-10]
```

### 3. Competitive Analysis

```markdown
## Competitive Intelligence Template

### Competitor: [Name]

**Product Overview**
- Core features:
- Pricing model:
- Target market:

**Strengths**
-
-

**Weaknesses**
-
-

**Market Position**
- Market share (if known):
- Customer sentiment:
- Recent changes:

**Differentiation Opportunities**
- Where Mailbird wins:
- Feature gaps to exploit:
```

## Research Tools Integration

### Web Research Pattern

```python
# Use with Agent Sparrow's research tools
research_queries = [
    f"{company_name} email solution",
    f"{company_name} IT infrastructure",
    f"{company_name} technology stack",
    f"{company_name} + 'looking for' OR 'switched to'",
    f"site:linkedin.com {company_name} IT director",
]
```

### Data Sources

1. **Company websites** - About, careers, tech blog
2. **LinkedIn** - Company page, employee profiles
3. **Crunchbase/PitchBook** - Funding, growth data
4. **G2/Capterra** - Current tool reviews
5. **Job postings** - Technology requirements
6. **Press releases** - Partnerships, expansions

## Outreach Strategy Templates

### Cold Email Framework

```markdown
## Outreach Template

**Subject Lines** (test variations)
- "Quick question about [Company]'s email workflow"
- "[Mutual connection] suggested I reach out"
- "Saw your team is growing - quick thought"

**Opening** (personalized)
- Reference recent company news
- Mention specific pain point
- Connect to their industry

**Value Proposition**
- One clear benefit relevant to their situation
- Brief proof point (case study, metric)

**Call to Action**
- Low commitment ask (15-min call, demo)
- Specific time suggestion
- Easy reply option

**Follow-up Cadence**
- Day 3: Add new value/insight
- Day 7: Different angle or case study
- Day 14: Break-up email with resource
```

### Enterprise Pitch Points

```markdown
## Mailbird Enterprise Value Props

**For IT Teams**
- Unified inbox management at scale
- Easy deployment and configuration
- Integration with existing infrastructure
- Security and compliance features

**For End Users**
- Intuitive interface, minimal training
- Multi-account support
- Speed and reliability
- Customization options

**For Decision Makers**
- Cost savings vs current solution
- Productivity gains (quantified)
- Support and SLA guarantees
- Migration assistance included
```

## Market Segment Analysis

```markdown
## Target Segment: [Segment Name]

**Profile**
- Company size range:
- Industries:
- Geographic focus:

**Common Characteristics**
- Technical sophistication:
- Decision process:
- Budget cycle:

**Key Pain Points**
1.
2.
3.

**Buying Triggers**
- Growth events:
- Technology refresh cycles:
- Competitive pressure:

**Channels**
- Where they research:
- Conferences/events:
- Publications:
```

## Quick Reference

| Research Type | Template | Use Case |
|--------------|----------|----------|
| Company profile | Company Research | Initial discovery |
| Qualification | BANT Assessment | Lead scoring |
| Competition | Competitive Intel | Positioning |
| Outreach | Email Framework | Sales support |
| Segmentation | Market Segment | Strategy |

## Integration with Agent Sparrow

- **Customer Research**: Deep-dive on enterprise prospects
- **Competitive Intel**: Monitor email client market
- **Sales Support**: Generate outreach templates
- **Market Analysis**: Identify new segment opportunities

## Best Practices

1. **Always verify** - Cross-reference multiple sources
2. **Date your research** - Markets change quickly
3. **Focus on signals** - Job postings, reviews, news indicate timing
4. **Personalize deeply** - Generic outreach fails
5. **Track outcomes** - Improve templates based on results
