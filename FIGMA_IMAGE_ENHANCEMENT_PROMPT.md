# Figma Agent Prompts — Image Enhancement

Copy one of the prompts below into the Figma agent (Figma AI / Make / Dev Mode agent).
Attach or paste the image(s) you want enhanced before sending.

---

## 1. Master prompt (works for any image)

```
You are a senior product/UI designer. Enhance the attached image(s) for the
"Datalytics" data-analytics platform and rebuild each one as clean, editable
Figma frames (vector, auto-layout, named layers) — not a flat bitmap.

GOAL
- Keep 100% of the original content: every label, number, arrow and relationship.
- Make it sharper, more modern, more readable, and presentation-ready.

VISUAL STYLE
- Background: #F4F6F5 (light) with a dark variant #101614.
- Ink: #17211F (text), #55635F (secondary text), #8B9995 (captions).
- Accent (teal): #0D6A68, accent-soft fill #D6EBE9.
- Highlight (ochre): #9A6209 on #F5E7CF — use only for warnings/notes.
- Borders: #CCD5D2, 1.5px, radius 10px. Soft shadow: 0 2 8 rgba(0,0,0,0.06).
- Fonts: Archivo (titles, 600–700), Source Serif 4 (body), JetBrains Mono
  (small labels, arrows, code, uppercase eyebrow text with +12% letter spacing).
- 8px spacing grid, generous white space, consistent box sizes, aligned centers.

ENHANCEMENTS TO APPLY
1. Redraw all boxes, arrows and connectors as vectors with even stroke weight
   and consistent arrowheads.
2. Establish clear hierarchy: title > block name > description > captions.
3. Add a simple line icon (24px, 1.5px stroke) to each block that fits its
   meaning (database, plug, gear, server, browser, sparkle for AI, cylinder
   for storage, share arrow).
4. Keep exactly ONE highlighted element (e.g. "AI Layer") in the accent color.
5. Fix contrast to WCAG AA (min 4.5:1 for text).
6. Remove blur, JPEG artifacts and uneven spacing.

DELIVERABLES
- One frame per image at 2x (e.g. 2400px wide), light and dark versions.
- Components for "Block", "Support block", "Arrow + label" so they are reusable.
- Export: PNG @2x and SVG.
- Short list of what you changed.

Do NOT invent new features, change wording, or add fake data.
```

---

## 2. Architecture diagram (`Datalytics-Diagram.png`, `Datalytics-Diagram-Detailed.png`)

```
Rebuild the attached architecture diagram in Figma using the master style.
Structure:
- Row 1 "MAIN FLOW →": Your Data → Connect & Load → Query Engine →
  Backend API → Web App, with arrow labels read / shape / rows / JSON.
- Row 2 "SUPPORT BLOCKS ↕": Datasets & Prep (builds), AI Layer (same rules,
  highlighted teal), Storage (saves), Share & Send (sends), each linked by a
  two-way vertical arrow to the block above it.
Make main-flow boxes white with a subtle shadow, support boxes #E9EDEC,
and the AI Layer box #D6EBE9 with a #0D6A68 border. Add one icon per box.
Deliver 2400×900 light + dark frames, plus a 1080×1350 vertical version for
mobile/social where the flow runs top-to-bottom.
```

---

## 3. Long project map (`Datalytics-Map.png`)

```
The attached image is a long one-page "project map" (diagram, tables, steps,
feature list). Split it into separate, well-designed Figma frames (1440px wide):
1. Cover + "The picture" diagram
2. Block table ("Block / What it does") styled as a clean data table with
   zebra rows and mono column headers
3. "What a user actually does" — 5 numbered steps as a horizontal stepper
   with teal number badges and code-style tags
4. "Full feature list" — 5 cards (Data, Reports & dashboards, AI,
   Sharing & security, Admin & operations) in a 2–3 column grid, each with
   an icon and its eyebrow label
5. Mermaid/diagram-editing section styled as a code card
Keep all text exactly as written. Use the master style tokens.
```

---

## 4. App screenshots (`screenshots/*.png`)

```
Turn the attached app screenshots into polished marketing mockups:
- Upscale and sharpen; place each inside a clean browser frame
  (light chrome, 12px radius, soft shadow) on a #F4F6F5 background.
- Do NOT redesign or alter the UI inside the screenshot.
- Add a short title + one-line caption above each (Archivo + Source Serif 4).
- Optionally add 1–3 callout pins (teal circles with numbers) pointing to key
  features, with matching notes on the side.
- Output 1600×1000 frames, PNG @2x.
```

---

## Tips
- Send one image per request for the best result, then ask: *"Apply the same
  style to the next image."*
- If the result drifts, reply: *"Keep the exact text and layout of the
  original; only improve styling, spacing, icons and sharpness."*
- For Arabic/RTL versions add: *"Also create an RTL frame with the text
  translated to Arabic, using the IBM Plex Sans Arabic font."*
