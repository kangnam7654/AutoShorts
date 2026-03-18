# Character Guide

AutoShorts uses a reference image to maintain consistent character appearance across videos. This guide explains how to set up your own character.

## How It Works

When you pass `--image character.png`, Veo 3.1 uses that image as a visual reference. The generated video character will match the style, clothing, and features of your reference image.

## Creating a Character Image

### Requirements

- **Resolution**: 1024x1024 or higher recommended
- **Format**: PNG (transparent background preferred)
- **Style**: Whatever matches your content — 3D animation, anime, realistic, illustrated
- **Framing**: Full upper body or full body, facing forward

### Recommended Approach

1. **Use an AI image generator** (Midjourney, DALL-E, Stable Diffusion) to create your character
2. **Generate multiple expressions** — at minimum:
   - Neutral/default expression
   - Serious/contemplative expression
   - Smiling/warm expression
3. **Keep the style consistent** across all expression variants
4. **Save to** `contents/character/your_character_name/`

### Example Directory Structure

```
contents/
  character/
    my_character/
      default.png        # Neutral expression
      serious.png        # For dramatic content
      smile.png          # For positive content
```

## Using Your Character

### In CLI

```bash
uv run python Backend/cli.py veo \
  --prompt-file prompts.json \
  --image contents/character/my_character/serious.png \
  -o output/video.mp4
```

### In Prompts

Describe your character in the prompt to help Veo maintain consistency:

```
3D animated character style matching the reference image throughout
— NOT live action, NOT realistic.
[Your character description: clothing, hair, accessories, etc.]
She/He stands alone in the center of a dark mystical space.
```

## Tips for Character Consistency

### What Works

- **Distinctive features**: Unique accessories, hair color, or clothing patterns help Veo recognize and maintain the character
- **Simple clothing**: Solid colors and clear silhouettes work best
- **3D animated style**: More consistent than realistic styles across parts
- **"matching the reference image"**: Always include this phrase in your prompt

### What Doesn't Work

- **Complex patterns**: Detailed textures on clothing tend to change between parts
- **Realistic style**: Veo struggles to maintain exact likeness in realistic mode
- **Multiple characters**: Consistency degrades with more than one character
- **Fast model**: The `veo-3.1-fast-generate-preview` model frequently changes character appearance between Part 1 and Part 2. Use Standard model for production.

### Part 2 Consistency

Always include in your Part 2 prompt:

```
Jeongbin remains standing in the same position,
wearing the EXACT same outfit and colors as Part 1.
```

Replace "Jeongbin" with your character's name.

## Character Description Template

```
[Name] is a [nationality/ethnicity] [gender] [role/occupation]
in [clothing description] with [distinctive feature 1],
[distinctive feature 2], and [distinctive feature 3],
rendered in [art style].
```

Example:
```
Luna is a mystical European fortune teller
in a dark velvet cloak with silver star earrings,
a crescent moon pendant, and long white hair,
rendered in stylized 3D animation.
```
