---
name: image-generation
description: AI image generation using Gemini Nano Banana Pro. Use when user requests images, diagrams, infographics, screenshots, or visual content. Also activates for KB articles needing illustrations.
---

# Image Generation Skill (Nano Banana Pro)

## Available Models

### gemini-2.5-flash-image
- **Speed**: Fast (2-5 seconds)
- **Quality**: Good for simple images
- **Best for**: Quick diagrams, simple illustrations
- **Resolution**: Up to 2K

### gemini-3-pro-image-preview (Recommended)
- **Speed**: Medium (5-15 seconds)
- **Quality**: High-quality with thinking mode
- **Best for**: Complex images, UI mockups, detailed diagrams
- **Resolution**: Up to 4K
- **Features**: Multi-turn editing, character consistency

## Capabilities

### 1. Text-to-Image
Generate images from text descriptions:
- Product illustrations
- Conceptual diagrams
- UI mockups
- Infographics

### 2. Image Editing
Modify existing images with text prompts:
- Add or remove elements
- Change colors or styles
- Add annotations
- Combine images

### 3. Multi-Turn Editing
Iterative refinement via chat:
- "Make the header blue"
- "Add a shadow to the button"
- "Move the icon to the left"

### 4. Text Rendering
Accurate text in images:
- Logos with text
- Annotated screenshots
- Labeled diagrams
- Infographics with data

### 5. Reference Image Consistency
Up to 14 reference images for:
- Character consistency across images
- Brand asset consistency
- Style matching

## Prompt Templates

### Infographic
```
Create a vibrant infographic explaining [topic] with a [style: clean/corporate/playful] design.
Include:
- Clear section headers
- Icon-based bullet points
- [Color scheme: brand colors/blue-green/warm tones]
- Logical flow from top to bottom
```

### Screenshot Mockup
```
Generate a realistic screenshot of [app name/type] showing [specific feature or screen].
Include:
- [Platform: macOS/Windows/web browser]
- [State: default/hover/active/error]
- [Key elements highlighted with: arrows/circles/callouts]
- Clean, professional appearance
```

### Flowchart Diagram
```
Create a [flowchart/sequence/architecture] diagram showing [process name].
Steps:
1. [Step 1]
2. [Step 2]
3. [Step 3]
Style: [clean boxes/rounded modern/technical]
Colors: [monochrome/brand colors/pastel]
```

### Before/After Comparison
```
Create a side-by-side comparison image showing:
LEFT (Before): [description of before state]
RIGHT (After): [description of after state]
Include:
- Clear "Before" and "After" labels
- Consistent framing between both sides
- [Highlight key differences with arrows/circles]
```

### Icon Set
```
Generate a set of [N] icons for [purpose/category].
Style: [outline/filled/duotone]
Size: Consistent [32x32/64x64] feel
Theme: [topic]
Include icons for: [list specific icons needed]
```

## Aspect Ratios

Choose based on use case:

| Ratio | Best For |
|-------|----------|
| 1:1 | Icons, avatars, social media |
| 4:3 | Screenshots, presentations |
| 16:9 | Banners, video thumbnails, headers |
| 2:3 | Mobile screenshots, portrait content |
| 3:2 | Landscape photos, blog images |

## Resolution Options

| Size | Resolution | Use Case |
|------|------------|----------|
| 1K | ~1024px | Quick drafts, thumbnails |
| 2K | ~2048px | Standard web use (recommended) |
| 4K | ~4096px | High-quality prints, hero images |

## Output Integration

### Inline Preview
Rendered directly in chat message (max 400px width):
```markdown
![Generated image](data:image/png;base64,{image_data})
```

### Artifact Panel
Full resolution with options:
- View at full size
- Download as PNG/JPEG
- Copy to clipboard
- Edit with follow-up prompts

### Usage Pattern
```markdown
<!-- In response -->
Here's the diagram you requested:

![Workflow diagram](data:image/png;base64,{thumbnail_base64})

::artifact{type="image" title="Workflow Diagram"}

Click the artifact panel to view full size and download.
```

## Best Practices

### Prompt Writing
1. **Be specific**: Include colors, style, layout
2. **Reference examples**: "In the style of [X]"
3. **Specify text**: Quote exact text to include
4. **Note restrictions**: "No text" if text rendering not needed

### Quality Tips
1. Use 2K resolution for web, 4K for print
2. Choose 16:9 for most UI mockups
3. Request "clean, professional" for business content
4. Include brand colors in hex if available

### Iteration Strategy
1. Start with basic prompt
2. Review and identify issues
3. Use multi-turn editing for refinements
4. Generate variations if needed

## Error Handling

### Common Issues

**"Content filtered"**
- Prompt may contain restricted content
- Rephrase to be more generic
- Avoid brand names or copyrighted characters

**"Generation failed"**
- Retry with simpler prompt
- Reduce resolution
- Check API quota

**"Text not rendering correctly"**
- Use shorter text strings
- Specify font style (sans-serif, bold)
- Place text in clear areas

## Rate Limits

- Gemini 3 Pro Image: Subject to standard Gemini rate limits
- Consider caching generated images for reuse
- Use 2K resolution unless 4K specifically needed
