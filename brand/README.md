# Meforash logo assets

`mark-primary.svg` is the authoritative reusable logo asset. The mark uses original vector paths for a Hebrew mem paired with a lowercase Latin m; it contains no text glyphs or font dependency.

- `mark-black.svg` is the one-color version for light backgrounds.
- `mark-reverse.svg` is the one-color version for dark backgrounds.
- `mark-dark.svg` and `mark-dark-512.png` retain the two-letter detail with a lighter sage mem and white lowercase m for dark backgrounds.
- `mark-primary-{256,512,1024}.png` are transparent exports rendered from `mark-primary.svg` at their named pixel sizes.

Keep the mark's proportions, colors, and clear space intact. See the [brand policy](../docs/BRAND-POLICY.md) for use requirements.

Use SVG for editing, print, or any size that must stay sharp. Use PNG where a service expects an uploaded image; these copies have transparent backgrounds. The site favicon intentionally uses a simpler mem-only variant for readability at tiny sizes.

Colors: sage `#41624c`; the inner lowercase m uses the black value specified in the primary SVG. The SVG paths are original artwork, so no font installation is required. The site's separate text wordmark is styled in the web interface; this folder contains the standalone emblem.

The original artwork's copyright license follows the repository's [Apache License 2.0](../LICENSE); the separate brand policy governs source-identifying uses and endorsement.
