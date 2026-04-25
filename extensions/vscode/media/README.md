# Marketplace assets

VS Code's gallery requires PNG icons (SVG isn't accepted as the
`icon` field). The repo ships SVG sources here so the PNGs can be
regenerated at any size without re-doing the design.

## Regenerate `icon.png` (128 × 128) and `banner.png` (1280 × 640)

```bash
# Requires `rsvg-convert` (librsvg) or `inkscape`.
rsvg-convert -w 128 -h 128 media/icon.svg -o media/icon.png

# Banner is built from the same gradient as `icon.svg` extruded to
# 1280×640 in `media/banner.svg`. Re-export the same way:
rsvg-convert -w 1280 -h 640 media/banner.svg -o media/banner.png
```

Both PNGs are gitignored — keep the SVGs canonical, regenerate on
release.

## Icon design

- 22 px corner radius (matches VS Code marketplace tile rounding).
- Deep-orange Grok primary (`#ff6b35`) at the centre = Grok.
- Three smaller satellite dots = Harper (cyan), Benjamin (amber),
  Lucas (judge red).
- Radial glow under the dots so the icon reads at 16 px in the
  marketplace search results.

## Activity-bar icon

`media/activity-bar.svg` is the monochrome glyph for the activity-
bar entry. VS Code re-tints `currentColor` to match the active
theme, so do NOT bake colours into this file.
