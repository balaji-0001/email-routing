# Design

How the product looks and behaves, as built on 2026-10-07. All styles are in `frontend/src/index.css`; shared components are in `frontend/src/components/kit.tsx`.

The whole product uses one **glass** design: translucent, frosted surfaces over a flowing coloured backdrop, with dark navy for text and the main actions. It was built from a reference image the owner supplied for the sign-in screen and then carried across the app.

There are two strengths of it:

- **The app** (everything after sign-in): a pale, soft backdrop in mint, aqua and lavender, with frosted white panels on top. Calm enough to work in all day.
- **The sign-in screens** (sign in, sign up, forgot and reset password, workspace setup): the full-strength backdrop, bright green through teal to deep navy, with one frosted blue card in the middle.

A plain white version of the app was tried on 2026-10-07 and the owner asked for the glass design back the same day. Do not flatten it.

---

## 1. Principles

1. **Glass over colour.** Surfaces are translucent and blur what is behind them; the backdrop supplies the colour. A surface is never an opaque flat fill, except menus, which stay nearly solid so their text is easy to read.
2. **Readable first.** Type is deliberately large for a dense tool, and nothing is below 12px. Text on glass is dark navy, never grey-on-tint.
3. **One dark accent, one flowing accent.** Dark navy marks the primary action. A short green-to-blue gradient marks "where you are" and "on": the active page, the workspace tile, meters, switches.
4. **Honest states.** A screen shows real data, a loading skeleton, an empty state or an error. Never placeholder content.
5. **Motion answers the user.** Short transitions on hover, press, open and close. Nothing moves by itself to decorate.

---

## 2. Colour

Defined as custom properties on `:root`, in the block of `index.css` headed "glass surfaces".

### Text and accents

| Token | Value | Use |
|-------|-------|-----|
| `--ink` | `#080d2e` | Primary buttons (as a gradient from `#19235c`), the logo word, ticked checkboxes |
| `--navy` | `#141d44` | Headings, input text, names |
| `--copy` | `#26324f` | Body text |
| `--copy-2` | `#44526e` | Secondary text, descriptions, hints |
| `--accent-flow` | `linear-gradient(180deg, #2fc58c, #1a78b4)` | Active-page marker in the sidebar, workspace tile, selected-row marker |
| Switch on | `#12a089` | |
| Links | `#14599a`, hover `#0a2c63` | |
| Focus ring | `0 0 0 4px rgba(34,160,170,.2)` (`--focus-ring`) | Inputs and the search bar |

### Glass

| Token | Value | Use |
|-------|-------|-----|
| `--glass` | `rgba(255,255,255,.5)` | Standard translucent fill |
| `--glass-hi` | `rgba(255,255,255,.74)` | Brighter fill: workspace switcher |
| `--glass-lo` | `rgba(255,255,255,.32)` | Quiet fill: table header rows |
| `--rim` | `rgba(255,255,255,.82)` | The light border on every glass surface |
| `--frost` | `blur(26px) saturate(1.7)` | The backdrop filter on panels, sidebar and top bar |
| `--line` | `rgba(24,44,102,.1)` | Dividers inside panels and tables |
| `--line-2` | `rgba(24,44,102,.18)` | Stronger dividers, checkbox border |

Panels and tiles are filled with `linear-gradient(160deg, rgba(255,255,255,.76), rgba(255,255,255,.52))`. Banners that give information (the strip at the top of the overview) use a faint aqua-to-mint tint instead.

### Backdrop

Drawn in code by `frontend/src/components/aurora.tsx` as flowing lines over a gradient. Its colours are the `--au-0` to `--au-5` properties.

| | Colours, left to right |
|---|---|
| In the app (`<Aurora soft />`) | `#bdeecb` · `#b1e8d4` · `#aadfe3` · `#b0cdef` · `#bcc4f1` · `#cbc8f3` |
| Sign-in screens (`<Aurora />`) | `#7be38c` · `#3fc98d` · `#1f9590` · `#195f92` · `#122c6e` · `#060a2a` |

`body` has a fallback colour of `#d6ece9` for the moment before the backdrop draws.

### Errors

Text `#a3271d` or `#8f1d15` on `rgba(255,226,221,.7)` with a soft red border. Red appears nowhere else.

---

## 3. Typography

| | |
|---|---|
| Text | **Manrope** (400, 500, 600, 700, 800), loaded from Google Fonts in `index.css` |
| Small uppercase labels and table headers | **DM Mono** (400, 500), letter-spaced |
| Default weight in the app | 500 |
| Headings inside panels | 700 |

| Role | Size | Notes |
|------|------|-------|
| Page title | 30px, weight 800 | Tight letter-spacing, `#0e1740` |
| Page description | 16px | |
| Panel title | 16px, weight 700 | |
| Big number on a tile | 27px, weight 800 | Tabular figures |
| Navigation item | 15px, weight 600 | |
| Body, buttons, inputs | 14 to 14.5px | |
| Table cells, secondary lines | 13 to 13.5px | |
| Uppercase label above a title or nav group | 12 to 13px DM Mono | The only uppercase text |
| Smallest allowed | 12px | |

Sentence case everywhere else. Line height about 1.45 for interface text and 1.6 to 1.7 for paragraphs.

---

## 4. Shape, depth and spacing

| | |
|---|---|
| Panel radius | 22px (`--r-panel`) |
| Tile radius | 18px (`--r-card`) |
| Input radius | 13px (`--r-ctl`) |
| Buttons, search bar, tags | Fully rounded (pill) |
| Resting depth | `--glass-shadow`: a white highlight along the top edge and a soft, wide navy shadow underneath |
| Small raised things | `--lift-1` |
| Hover on tiles | `--lift-2`, and the border brightens to white |
| Menus, dialogs | `--lift-3` |

The light rim and the top highlight are what make a surface read as glass; keep both when adding a new one. Page padding is about 33px top and 39px at the sides on desktop.

---

## 5. Layout

- **Sidebar:** 292px wide, frosted (`rgba(255,255,255,.46)` with `--frost`), light rim on the right. Logo, workspace switcher, Compose button, navigation groups, and the signed-in person at the bottom.
- **Top bar:** 67px tall, frosted, light rim underneath. Breadcrumb (workspace › page) on the left; search, help, notifications and avatar on the right.
- **Content:** fills the rest, up to 1725px wide, directly on the backdrop.

| Width | Layout |
|-------|--------|
| Above 1260px | Full layout |
| 1260px and below | Narrower sidebar (258px) and tighter padding |
| 940px and below | Sidebar becomes a drawer opened from a menu button (nearly solid, so it reads over the page); side-by-side panels stack |
| 690px and below | Phone layout: two-column tiles, stacked forms, search collapses to an icon |

These `@media` blocks are at the very end of `index.css` and must stay there.

---

## 6. Components

**Buttons** — 42px tall pills, 14.5px text.
- Primary: navy gradient (`#19235c` to `#080d2e`), white text, a deep shadow. One per screen where possible.
- Secondary: translucent white with the light rim; brighter on hover.
- Both press in slightly when clicked. A button that is working shows its progress in the label ("Saving…") and is disabled.

**Fields** — label above (13.5px), 46px input filled `rgba(255,255,255,.6)` with the light rim; on focus it turns nearly solid white with the teal focus ring. A hint or an error sits under the input. Read-only fields are more transparent.

**Panels** — the glass fill, light rim, 22px radius, `--glass-shadow`, `--frost`. A panel header has a 16px bold title and an optional one-line description.

**Tiles** (the numbers on the overview) — the same glass at 18px radius: a small icon square, a label, a big number, one line of context. On hover the rim turns white and the shadow deepens.

**Tables** — DM Mono header row on `--glass-lo`, 64px rows separated by `--line`, row brightens on hover. A person is shown as avatar, bold name, and email underneath.

**Empty state** — centred: icon in a 52px translucent white square, a 17px bold title, one or two sentences. Says what will appear here, and "isn't available yet" when the feature is not built. No action button unless the action works.

**Notices** — a translucent white box with the rim for information; the red error style for failures.

**Tags** — small pills: the role on the team page (translucent white with the rim), "You" (soft green tint, dark green text).

**Avatars** — initials in a circle.

**Switch** — 40×24px; translucent navy when off, green `#12a089` when on; the knob stretches while pressed.

**Menus** (workspace, profile, help) — nearly solid white (`rgba(250,253,254,.98)`), light rim, 18px radius, `--lift-3`; 40px rows. Close on Escape and on a click outside.

**Dialogs** — glass at 28px radius over a dimmed, slightly blurred page.

**Toasts** — bottom right, dark translucent navy with a blur, white text; disappear after 5 seconds (8 for errors).

**Loading** — skeleton rows that shimmer. Use them while a list or form is loading; do not show a spinner over content.

---

## 7. Motion

- Easing: `cubic-bezier(.2,.8,.2,1)` for most things; a slight overshoot (`cubic-bezier(.34,1.45,.64,1)`) for the switch and small icon reactions.
- Hover and focus changes: about 150ms. Menus and toasts: 140 to 200ms. Page change: a 300ms fade and 6px rise.
- Lists and tiles rise in once when a page opens, a few tens of milliseconds apart.
- The backdrop does not animate.
- With "reduce motion" set in the operating system, animations are switched off.

---

## 8. Sign-in screens

The full-strength version of the design.

- **Backdrop:** full-screen flowing lines from bright green on the left through teal and blue to deep navy on the right. Outlined rounded squares sit in the top-right and bottom-left corners on wide screens.
- **Card:** centred, up to 600px wide, 38px radius, translucent light blue with a 38px background blur, a soft inner highlight and a deep shadow.
- **Title:** 44px, weight 800, centred, `#27325f`. One line of supporting text under it at 18px.
- **Fields:** 66px tall translucent blue boxes with the label inside at the top and an icon on the right; the password field's icon shows or hides the password.
- **Row under the fields (sign-in only):** "Forgot password?" on the left, a "Remember me" checkbox on the right.
- **Button:** 66px navy pill, label centred, arrow at the right edge that moves on hover.
- **Under the card:** one white line that switches between sign-in and sign-up.
- **Messages:** errors and notices appear inside the card, above the fields.
- **Short windows:** below 840px and again below 720px of height, the card tightens so the screen fits without scrolling.
- **Phones:** the card fills the width with 28px radius; the corner squares are hidden.

---

## 9. Writing in the interface

- Say what the thing is, in the user's words: "Email accounts", not "Connections".
- Sentence case. No exclamation marks.
- A button names its action; the confirmation repeats the word: "Save changes" then "Workspace saved."
- Errors say what happened and what to do next: "Your current password is incorrect."
- Not built yet: "Inviting teammates isn't available yet." followed by what it will do.
- Empty because there is no data: "No conversations yet", followed by when they will appear.

---

## 10. Accessibility

- Text on glass is dark navy. Calculated against the backdrop's own colours, the secondary text colour (`--copy-2`) comes out at about 4.6:1 at its worst (the lavender end), just above the WCAG AA line of 4.5:1. Do not use anything lighter for text, and check new text colours against both the palest and the most saturated parts of the backdrop.
- With "reduce transparency" set in the operating system, the blur is switched off and surfaces become solid.
- Every control is reachable by keyboard and shows a visible focus outline.
- Icons that are the only content of a button have an `aria-label`.
- Form errors are linked to their field and announced.
- The layout works from 390px wide upward.

---

## 11. Adding to the design

- A new surface gets the glass fill, the `--rim` border, a radius from section 4, `--glass-shadow` and `--frost`. Copy an existing panel rather than inventing a variant.
- Blurring is the expensive part of this design. Put it on containers (a panel, a bar), not on every row or chip inside them.
- Colour comes from the backdrop and the two accents. Do not introduce new hues for decoration.

## 12. Undecided

- The product name and logo. "northstar" with three rising bars is a working mark.
