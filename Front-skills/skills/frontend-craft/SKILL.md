---
name: frontend-craft
description: Design and implement polished web interfaces using the user's Forte visual reference collection. Use for new pages, dashboards, landing pages, UI components, redesigns, or requests to make frontend design clearer and more distinctive. Includes typography, color, layout, responsive behavior and interaction states. Not for backend-only changes or native mobile UI.
metadata:
  source: Forte reference collection and reviewed ECC guidance
---

# Frontend Craft

Produce a working interface with deliberate visual hierarchy, readable content, coherent components and complete interactions. The user's current brief and the existing product design system take priority over the examples in this skill.

## Establish the design problem

Inspect the target route, neighboring screens, components, tokens, dependencies and available assets before editing. For a small change, stay within that component. For a new page or redesign, establish a short design brief: audience and task; primary action; content hierarchy; visual direction; constraints and target viewports. Infer routine choices from the project; ask only when a missing decision materially affects the result. Do not require a separate approval step for ordinary design work.

- **Existing product:** extend its spacing, typography, controls and navigation. Preserve routes, data contracts and working behaviors.
- **New product:** choose a direction suited to its actual job. A dense operations dashboard needs scanning, filters and useful data; a launch page may need expressive typography and a strong hero image.
- **Reference recreation:** open the supplied reference, identify layout, type, color and behavior separately, and reproduce the requested fidelity. Do not substitute your preferred aesthetic.
- **Review only:** inspect and report prioritized, concrete fixes. Do not edit when the user only asked for review.

## Use the visual collection as evidence

Read [visual-principles.md](references/visual-principles.md). For visual design work, select 2–4 relevant IDs from [reference-index.md](references/reference-index.md) and open the actual images with the host's image-reading tool. Every path is relative to this skill directory. If image reading is unavailable, use the documented interpretation and explicitly say the visual comparison was not performed.

The 63 originals are educational design cards, not 63 production interfaces. Their repeated black/lime presentation is the author's framing, not a mandatory palette. Transfer the principle: hierarchy, rhythm, typography, identity or feedback. Do not copy a reference's logo, marketing claims or watermark into the product.

Read only the supporting material needed:

- [typography.md](references/typography.md): font selection, Cyrillic text and readable typesetting.
- [palettes.md](references/palettes.md): 12 observed pairs, measured pair contrast and semantic adaptation.
- [implementation.md](references/implementation.md): responsive structure, states, assets and finishing details.
- [design-brief.md](assets/design-brief.md): optional reusable brief for a substantial page or redesign.

## Implement from the hierarchy

1. Place real content and the primary user flow first. Establish alignment, information density and section rhythm before adding effects.
2. Reuse existing tokens or define a small semantic set for surfaces, text, border, accent, statuses, spacing, type and radius. An accent palette is not a complete UI theme.
3. Choose one recognizable detail that serves the product: a typographic treatment, diagram, data presentation, restrained shape language or photographic composition. It need not be a decorative asset.
4. Build reusable components where repetition exists. Use the project's framework and installed libraries. Do not migrate stacks or introduce a design dependency just to make one screen look polished.
5. Implement applicable loading, empty, error, success, disabled and partial-data states. State changes need understandable feedback and recovery. A static mockup may simulate them locally, but must not pretend to submit to a real backend.
6. Make layout constraints explicit. Handle long names, real numbers, translated labels, narrow screens, image ratios and text enlargement. Primary actions must remain reachable.

Specific visual checks:

- One dominant message per region, with quieter supporting text. Repeated rows may each have a primary action; do not remove useful actions to satisfy a slogan.
- Usually one or two type families. Check actual font files and glyph coverage; never assume a commercial font is installed or licensed.
- Clear shared alignment lines and a small spacing scale. Group spacing should communicate relationships.
- Color supports hierarchy and state. Use semantic status colors when needed; the reference's 60/30/10 rule is a heuristic, not a hard budget.
- Use shadow for elevation, borders for separation, and radius consistently. Avoid repeating identical oversized cards for unrelated content.
- Purposeful motion, usable keyboard focus, and reduced-motion support. A quick CSS transition is often enough.

## Render, inspect, improve

Run the app with the project's actual commands. Inspect the affected screen at a narrow and wide viewport (include an intermediate one for a substantial layout), exercise the main action and relevant error/empty states, and correct the most visible problems. Use the companion `frontend-qa` skill if installed; otherwise follow the same checks above and record the actual evidence.

Do not call a page visually verified because it compiles. If browser access is unavailable, complete the source changes and report which visual and interaction checks remain unverified. Stop when the requested behavior works, relevant checks pass and no known significant visual defect remains; avoid endless arbitrary redesign passes.

For specialized implementation help, use `ecc-library` if available to select a narrow supporting reference. This skill does not depend on ECC hooks, MCP services, external APIs or a specific agent runtime.

Deliver the implemented result, concise rationale, evidence of checks and material remaining limitations. Keep development explanations out of product-facing copy.
