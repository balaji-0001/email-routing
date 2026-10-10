---
name: ui-ux-designer
description: >
  Design and implement stunning, production-grade UI/UX for web apps, mobile apps, SaaS dashboards, landing pages, and component libraries. Use this skill whenever the user wants anything to look beautiful, polished, or professional — including: "make this look good", "design a dashboard", "create a landing page", "design onboarding screens", "build a component library", "make this more modern", "glassmorphism", "dark mode", "animations", "micro-interactions", "design system", "color palette", "typography", "UI kit", "hero section", "pricing page", "modal", "sidebar navigation", "onboarding flow", "empty states", "loading states", "Framer Motion". Always use this skill when the primary goal is visual quality, design consistency, or user experience.
---

# UI/UX Designer

A skill for designing and implementing world-class user interfaces — from single components to
full design systems — across web, mobile, and desktop platforms.

---

## Design Philosophy

Great UI is not decoration. It is the product. Every pixel communicates trust, quality, and
care. The standard to aim for: could this ship in a Stripe, Linear, Vercel, or Arc product?

**Core Principles**
- **Hierarchy first** — guide the eye; every screen has one primary action
- **Space is not empty** — whitespace is a design element, not a mistake
- **Consistency over creativity** — establish a system, then work within it
- **Motion has meaning** — animate to orient, not to impress
- **Accessibility is non-negotiable** — contrast ratios, focus states, keyboard nav

---

## Phase 1 — Design Brief

Before designing, establish:

1. **Platform** — Web (desktop/responsive), iOS, Android, cross-platform (RN/Flutter)?
2. **Context** — SaaS, consumer app, marketing site, admin tool, e-commerce?
3. **Vibe** — collect 3 adjectives (e.g. "clean, powerful, minimal" or "warm, playful, bold")
4. **Existing brand?** — colors, fonts, logos already defined?
5. **Key screens** — what needs to be designed (list them)?
6. **Tech stack** — React+Tailwind? SwiftUI? Flutter? Affects implementation approach.

---

## Phase 2 — Design System Foundation

Always establish the system before designing individual screens.

### 2a. Color System

```
PRIMARY PALETTE
├── Brand Primary:    #[hex]  — CTAs, active states, links
├── Brand Secondary:  #[hex]  — supporting accents
├── Brand Tertiary:   #[hex]  — subtle highlights
│
NEUTRAL PALETTE (9-step scale)
├── 50:   #F9FAFB  — page backgrounds
├── 100:  #F3F4F6  — card backgrounds
├── 200:  #E5E7EB  — borders, dividers
├── 300:  #D1D5DB  — disabled states
├── 400:  #9CA3AF  — placeholder text
├── 500:  #6B7280  — secondary text
├── 600:  #4B5563  — body text
├── 700:  #374151  — strong text
├── 800:  #1F2937  — headings
├── 900:  #111827  — high-contrast
│
SEMANTIC COLORS
├── Success:  #10B981  (green-500)
├── Warning:  #F59E0B  (amber-500)
├── Error:    #EF4444  (red-500)
└── Info:     #3B82F6  (blue-500)
```

**Dark Mode** — always design both. Dark backgrounds:
- `#0A0A0B` — deepest (page bg)
- `#111113` — card bg
- `#1C1C1F` — elevated surface
- `#2C2C30` — borders

### 2b. Typography Scale

```
Font Family: Inter (sans), JetBrains Mono (code), optional serif accent

SCALE (rem-based, 4px grid)
display-2xl: 4.5rem / 5rem    — Hero headlines
display-xl:  3.75rem / 4.5rem — Section heroes  
display-lg:  3rem / 3.75rem   — Large headings
display-md:  2.25rem / 2.75rem
display-sm:  1.875rem / 2.375rem
display-xs:  1.5rem / 2rem
text-xl:     1.25rem / 1.875rem
text-lg:     1.125rem / 1.75rem
text-md:     1rem / 1.5rem     — Body default
text-sm:     0.875rem / 1.25rem — Secondary body
text-xs:     0.75rem / 1.125rem — Captions, labels
```

**Weight usage:**
- 400 Regular — body copy
- 500 Medium — UI labels, nav items
- 600 Semibold — card titles, subheadings  
- 700 Bold — page headings
- 800 Extrabold — hero display text

### 2c. Spacing System

Base unit: 4px. All spacing is multiples of 4.

```
4px   (1)  — tight inline gaps
8px   (2)  — icon-to-label, badge padding
12px  (3)  — input padding vertical
16px  (4)  — standard padding, gap between items
20px  (5)  — card padding (compact)
24px  (6)  — card padding (standard)
32px  (8)  — section inner padding
40px  (10) — between major sections (mobile)
48px  (12) — between major sections (desktop)
64px  (16) — hero vertical padding
80px  (20) — large section gaps
96px  (24) — page-level vertical rhythm
```

### 2d. Border Radius

```
none:  0     — tables, dividers
xs:    2px   — badges, tags
sm:    4px   — buttons (compact), inputs
md:    8px   — buttons (standard), cards (compact)
lg:    12px  — cards, dropdowns
xl:    16px  — modals, panels
2xl:   24px  — large cards, feature sections
3xl:   32px  — hero cards, app frames
full:  9999px — pills, avatars, toggles
```

### 2e. Shadow System

```css
/* Elevation scale */
--shadow-xs:  0 1px 2px rgba(0,0,0,0.05);
--shadow-sm:  0 1px 3px rgba(0,0,0,0.10), 0 1px 2px rgba(0,0,0,0.06);
--shadow-md:  0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.06);
--shadow-lg:  0 10px 15px rgba(0,0,0,0.10), 0 4px 6px rgba(0,0,0,0.05);
--shadow-xl:  0 20px 25px rgba(0,0,0,0.10), 0 10px 10px rgba(0,0,0,0.04);
--shadow-2xl: 0 25px 50px rgba(0,0,0,0.25);

/* Colored glow (for brand accents) */
--shadow-brand: 0 0 0 3px rgba(var(--brand-rgb), 0.15),
                0 4px 16px rgba(var(--brand-rgb), 0.20);
```

---

## Phase 3 — Component Library

### Buttons

```
HIERARCHY
├── Primary    — filled brand bg, white text (main CTA)
├── Secondary  — white bg, border, brand text (supporting action)
├── Ghost      — transparent, no border, muted text (tertiary)
├── Destructive — filled red, white text (delete/danger)
└── Link       — no bg/border, brand color, underline on hover

SIZES
├── xs: h-7  px-3  text-xs  — compact lists
├── sm: h-8  px-4  text-sm  — secondary actions
├── md: h-9  px-5  text-sm  — default
├── lg: h-11 px-6  text-base — hero CTAs
└── xl: h-13 px-8  text-lg  — landing page hero

STATES: default → hover (lighten 10%) → active (darken 5%) → focus (ring) → disabled (50% opacity)
```

### Form Elements

```
INPUT ANATOMY
├── Label: text-sm font-medium text-gray-700, mb-1.5
├── Input: h-9 px-3 border border-gray-300 rounded-md text-sm
│         focus:ring-2 focus:ring-brand-500 focus:border-brand-500
├── Helper: text-xs text-gray-500 mt-1
└── Error: text-xs text-red-600 mt-1, border turns red-500

INPUT TYPES: text, password (toggle reveal), search (icon prefix),
  select (custom chevron), textarea (auto-resize), toggle, checkbox, radio
```

### Cards

```
VARIANTS
├── Default:  white bg, border, shadow-sm, p-6, rounded-xl
├── Elevated: white bg, shadow-lg (no border), p-6, rounded-xl
├── Ghost:    bg-gray-50, no border, no shadow, p-6
├── Feature:  gradient bg, white text, p-8, rounded-2xl
└── Stat:     compact, icon+label+value, p-4, rounded-lg
```

---

## Phase 4 — Screen Patterns

### Navigation Patterns

**Sidebar (SaaS/Admin)**
```
Width: 240px collapsed → 64px icon-only
├── Logo area: h-16, px-4
├── Nav items: h-9, px-3, icon+label, active=brand bg
├── Section headers: text-xs uppercase tracking-wider text-gray-400
├── User profile: bottom-pinned, avatar+name+role
└── Collapse toggle: bottom right
```

**Top Nav (Marketing/App)**
```
Height: 64px, sticky, backdrop-blur-md bg-white/80
├── Logo: left
├── Nav links: center (hidden mobile → hamburger)
├── CTAs: right (Login + Get Started)
└── Mobile: slide-in drawer
```

### Page Templates

**Dashboard**
- Stat cards row (4 across) → Charts row → Table
- Left sidebar + right content area
- Quick-action buttons in header

**Settings**
- Left nav (categorized) + right content pane
- Each section: heading + description + form fields + save button
- Danger zone section at bottom (red bg)

**Landing Page**
- Hero (headline + subheading + CTAs + hero image/animation)
- Social proof (logos row)
- Features (alternating image+text or 3-column cards)
- How it works (numbered steps)
- Pricing (3-column table)
- Testimonials (carousel or masonry)
- Final CTA section
- Footer

**Onboarding Flow**
- Progress bar top
- One question/step per screen
- Large, friendly typography
- Big input targets (mobile-friendly)
- Skip option where appropriate
- Celebratory completion screen

---

## Phase 5 — Motion & Animation

### Principles
- **Duration**: 150ms for micro (hover), 200-300ms for transitions, 400-500ms for entrances
- **Easing**: `ease-out` for entrances, `ease-in` for exits, `ease-in-out` for transitions
- **Never animate**: color alone (pair with another property), layout shifts

### Framer Motion Patterns (React)

```tsx
// Page entrance
const pageVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
  exit:    { opacity: 0, y: -8, transition: { duration: 0.2 } }
};

// Stagger children
const containerVariants = {
  animate: { transition: { staggerChildren: 0.06 } }
};

// Card hover
const cardHover = {
  whileHover: { y: -2, boxShadow: 'var(--shadow-lg)', transition: { duration: 0.15 } }
};

// Modal
const modalVariants = {
  initial: { opacity: 0, scale: 0.96 },
  animate: { opacity: 1, scale: 1, transition: { duration: 0.2 } },
  exit:    { opacity: 0, scale: 0.96 }
};
```

### CSS Micro-interactions
```css
/* Button press */
button:active { transform: scale(0.97); }

/* Smooth color transitions */
* { transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s; }

/* Skeleton loading */
@keyframes shimmer {
  from { background-position: -200% 0; }
  to   { background-position:  200% 0; }
}
.skeleton {
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
```

---

## Phase 6 — Special Design Treatments

### Glassmorphism
```css
.glass {
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(16px) saturate(180%);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
}
/* Dark glass */
.glass-dark {
  background: rgba(0, 0, 0, 0.25);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
```

### Gradient Patterns
```css
/* Mesh gradient background */
.mesh-bg {
  background: radial-gradient(at 40% 20%, hsla(228,100%,74%,1) 0px, transparent 50%),
              radial-gradient(at 80% 0%,  hsla(189,100%,56%,1) 0px, transparent 50%),
              radial-gradient(at 0%  50%, hsla(355,100%,93%,1) 0px, transparent 50%);
}
/* Aurora */
.aurora {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
  background-size: 400% 400%;
  animation: aurora 8s ease infinite;
}
@keyframes aurora {
  0%, 100% { background-position: 0% 50%; }
  50%       { background-position: 100% 50%; }
}
/* Brand glow */
.glow {
  box-shadow: 0 0 40px rgba(var(--brand-rgb), 0.3),
              0 0 80px rgba(var(--brand-rgb), 0.15);
}
```

### Noise Texture (adds depth)
```css
.noise::after {
  content: '';
  position: absolute; inset: 0;
  background-image: url("data:image/svg+xml,...");  /* SVG noise filter */
  opacity: 0.04;
  mix-blend-mode: overlay;
  pointer-events: none;
}
```

---

## Phase 7 — Platform-Specific Guidelines

### Web (React / Next.js)
- Tailwind CSS utility classes — stick to the design token scale
- shadcn/ui for accessible base components
- Framer Motion for animations
- Responsive breakpoints: `sm:640 md:768 lg:1024 xl:1280 2xl:1536`

### iOS (SwiftUI)
- Follow Apple HIG — use system fonts (SF Pro), system colors
- Minimum tap target: 44×44pt
- Safe area insets — always respect notch/home indicator
- Native components preferred (NavigationStack, TabView, Sheet)
- Custom: gradient cards, custom icons, haptic feedback

### Android (Jetpack Compose)
- Material You design language — dynamic color theming
- `MaterialTheme.colorScheme` for all colors
- Minimum touch target: 48×48dp
- Bottom navigation, FAB, SnackBar patterns
- Motion: Material shared element transitions

### React Native (Cross-platform)
- `StyleSheet.create` for performance
- Platform-specific: `Platform.OS === 'ios' ? ... : ...`
- Custom fonts via expo-font
- React Navigation for routing
- Reanimated 2 for smooth animations (runs on UI thread)

---

## Deliverable Formats

| Request Type | Output |
|---|---|
| "Design a component" | Production-ready code (React/SwiftUI/Compose) |
| "Design system" | Token definitions + component specs |
| "Landing page" | Full responsive HTML/JSX with animations |
| "App screens" | Screen-by-screen code with navigation |
| "Audit my design" | Annotated feedback with specific fixes |
| "Color palette" | Hex values + usage rules + CSS variables |

---

## Quality Bar

Before delivering any design, check:
- [ ] Does it pass WCAG AA contrast (4.5:1 for text)?
- [ ] Do all interactive elements have visible focus states?
- [ ] Does it work at 320px width (smallest mobile)?
- [ ] Are all spacing values on the 4px grid?
- [ ] Is there a loading state, empty state, and error state?
- [ ] Would a non-technical user understand what to do on this screen?
