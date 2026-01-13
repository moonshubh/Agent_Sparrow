---
name: pptx
description: Presentation creation, editing, and analysis for PowerPoint files. Use when creating training materials, generating slide decks from KB content, or analyzing customer presentations.
---

# PPTX Processing Skill

## Overview

PowerPoint presentation processing for Agent Sparrow's documentation and training needs.

## When to Use

- Create presentation materials for support training
- Generate slide decks from KB articles
- Analyze customer-submitted presentations
- Extract content from existing presentations

## Reading and Analyzing Content

### Text Extraction
```bash
# Convert presentation to markdown
python -m markitdown presentation.pptx > content.md
```

### Using python-pptx
```python
from pptx import Presentation

prs = Presentation('presentation.pptx')
for slide in prs.slides:
    for shape in slide.shapes:
        if hasattr(shape, "text"):
            print(shape.text)
```

## Creating New Presentations

```python
from pptx import Presentation
from pptx.util import Inches, Pt

# Create presentation
prs = Presentation()

# Add title slide
title_slide_layout = prs.slide_layouts[0]
slide = prs.slides.add_slide(title_slide_layout)
title = slide.shapes.title
subtitle = slide.placeholders[1]

title.text = "Presentation Title"
subtitle.text = "Subtitle text"

# Add content slide
bullet_slide_layout = prs.slide_layouts[1]
slide = prs.slides.add_slide(bullet_slide_layout)
shapes = slide.shapes

title_shape = shapes.title
body_shape = shapes.placeholders[1]

title_shape.text = 'Slide Title'
tf = body_shape.text_frame
tf.text = 'First bullet point'
p = tf.add_paragraph()
p.text = 'Second bullet point'
p.level = 0

# Save
prs.save('output.pptx')
```

## Adding Images

```python
from pptx.util import Inches

# Add image to slide
left = Inches(1)
top = Inches(2)
width = Inches(4)

slide.shapes.add_picture('image.png', left, top, width=width)
```

## Creating Tables

```python
from pptx.util import Inches

rows, cols = 3, 4
left = Inches(1)
top = Inches(2)
width = Inches(8)
height = Inches(2)

table = slide.shapes.add_table(rows, cols, left, top, width, height).table

# Set header row
table.cell(0, 0).text = 'Column 1'
table.cell(0, 1).text = 'Column 2'

# Add data
table.cell(1, 0).text = 'Data 1'
table.cell(1, 1).text = 'Data 2'
```

## KB Article to Presentation

```python
def kb_to_presentation(kb_article):
    """Convert KB article to presentation slides."""
    prs = Presentation()

    # Title slide
    title_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_layout)
    slide.shapes.title.text = kb_article['title']

    # Content slides
    content_layout = prs.slide_layouts[1]
    for section in kb_article['sections']:
        slide = prs.slides.add_slide(content_layout)
        slide.shapes.title.text = section['heading']

        body = slide.shapes.placeholders[1].text_frame
        for i, point in enumerate(section['points']):
            if i == 0:
                body.text = point
            else:
                p = body.add_paragraph()
                p.text = point

    return prs
```

## Quick Reference

| Task | Method |
|------|--------|
| Create presentation | `Presentation()` |
| Add slide | `prs.slides.add_slide(layout)` |
| Add text | `shape.text = "..."` |
| Add image | `slide.shapes.add_picture()` |
| Add table | `slide.shapes.add_table()` |
| Save | `prs.save('file.pptx')` |

## Integration with Agent Sparrow

- **Training Materials**: Generate support training from KB articles
- **Customer Presentations**: Analyze submitted presentations
- **Documentation**: Create visual guides from text content
- **Reporting**: Generate presentation reports from data

## Dependencies

- **python-pptx**: `pip install python-pptx`
- **markitdown**: `pip install markitdown[pptx]`
