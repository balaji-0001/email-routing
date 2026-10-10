---
name: frontend-builder
description: >
  Build production-grade frontend interfaces — React, Next.js, Vue, HTML/CSS, and web components. Use this skill for: "build a component", "React hook", "Next.js page", "App Router", "server component", "client component", "Tailwind CSS", "CSS layout", "responsive design", "form handling", "state management", "Zustand", "React Query", "data fetching", "infinite scroll", "pagination", "routing", "middleware", "SEO metadata", "web performance", "lazy loading". Also trigger when wiring a frontend to a backend API, handling auth on the client side, or building any interactive web UI.
---

# Frontend Builder

Build production-grade UIs across web, iOS, Android, and cross-platform targets.

---

## Step 1 — Identify the Target Platform

| Platform | Primary Stack |
|----------|--------------|
| Web (App) | React 18+, Next.js 14+ App Router, TypeScript |
| Web (Marketing) | Next.js, Astro, or plain HTML/CSS |
| Cross-platform Mobile | React Native + Expo |
| iOS Native | SwiftUI (Swift 5.9+) |
| Android Native | Jetpack Compose (Kotlin) |
| Desktop | Electron + React, or Tauri |

Ask if unclear. Default to **Next.js 14 App Router + TypeScript + Tailwind** for web.

---

## Step 2 — Understand the Feature

Before writing code, clarify:
1. **What does the user see?** (describe the UI state)
2. **What does the user do?** (interactions, forms, navigation)
3. **Where does data come from?** (API, local state, server component, URL params)
4. **What are the edge cases?** (loading, error, empty state)
5. **Does a design or mockup exist?** (if so, extract tokens: colors, spacing, typography)

---

## Step 3 — Component Architecture

### Component Design Rules
- **Single responsibility** — one concern per component
- **Props down, events up** — parent owns state, child renders + emits
- **Co-locate state** — keep state as close as possible to where it's used
- **Extract early** — if JSX exceeds ~80 lines, extract sub-components

### Folder Structure (Next.js App Router)
```
apps/web/
├── app/
│   ├── (auth)/          # Route group — auth pages
│   ├── (dashboard)/     # Route group — protected pages
│   │   ├── layout.tsx   # Shared shell
│   │   └── page.tsx     # Dashboard home
│   └── api/             # API routes (if not using separate backend)
├── components/
│   ├── ui/              # Primitive, reusable (Button, Input, Modal)
│   ├── features/        # Feature-specific (UserCard, PostEditor)
│   └── layouts/         # Page shells (Sidebar, Topbar)
├── hooks/               # Custom React hooks
├── lib/                 # Utilities, API clients, formatters
└── styles/              # Global CSS, Tailwind config
```

### React Native / Expo
```
apps/mobile/
├── app/                 # Expo Router file-based routing
│   ├── (tabs)/          # Tab navigator
│   └── (stack)/         # Stack screens
├── components/
│   ├── ui/
│   └── features/
├── hooks/
└── constants/           # Theme tokens, sizes
```

---

## Step 4 — Implementation Patterns

### Server vs Client Components (Next.js)
```tsx
// Server Component (default) — runs on server, no interactivity
// ✅ Use for: data fetching, static content, layouts
export default async function ProductPage({ params }) {
  const product = await db.product.findUnique({ where: { id: params.id } });
  return <ProductView product={product} />;
}

// Client Component — runs in browser, interactive
// ✅ Use for: useState, useEffect, event handlers, browser APIs
'use client';
export function AddToCartButton({ productId }) {
  const [loading, setLoading] = useState(false);
  // ...
}
```

### Data Fetching Patterns
```tsx
// 1. Server Component (preferred for initial data)
const data = await fetch('/api/resource', { next: { revalidate: 60 } });

// 2. SWR / React Query (preferred for client-side, frequently updated)
const { data, isLoading, error } = useSWR('/api/resource', fetcher);

// 3. Server Actions (preferred for mutations)
async function updateUser(formData: FormData) {
  'use server';
  await db.user.update({ ... });
  revalidatePath('/profile');
}
```

### Form Handling
```tsx
// React Hook Form + Zod (recommended pattern)
const schema = z.object({
  email: z.string().email(),
  name: z.string().min(2),
});

const form = useForm<z.infer<typeof schema>>({
  resolver: zodResolver(schema),
});
```

### State Management Decision Tree
```
Is state used only in one component?
  → useState / useReducer

Is state shared between siblings or distant components?
  → Lift to parent, or use Context

Is state server data (fetched from API)?
  → SWR / React Query / TanStack Query

Is state global app state (user session, theme, cart)?
  → Zustand (preferred) or Jotai
```

---

## Step 5 — UI Quality Checklist

Before marking a component done:

**Functionality**
- [ ] All user interactions work (click, type, submit, navigate)
- [ ] Loading state shown during async operations
- [ ] Error state shown when something fails
- [ ] Empty state shown when list/data is empty
- [ ] Form validation with clear error messages

**Responsiveness**
- [ ] Mobile-first: works at 320px width
- [ ] Tablet: 768px breakpoint checked
- [ ] Desktop: 1280px+ checked
- [ ] No horizontal scroll on any breakpoint

**Accessibility (a11y)**
- [ ] All interactive elements reachable by keyboard
- [ ] Appropriate ARIA labels on icon-only buttons
- [ ] Color contrast meets WCAG AA (4.5:1 for text)
- [ ] Images have alt text
- [ ] Form inputs have labels (not just placeholders)

**Performance**
- [ ] Images use `next/image` or lazy loading
- [ ] Large lists virtualized (react-window / FlashList on RN)
- [ ] No unnecessary re-renders (check with React DevTools)
- [ ] Code-split heavy components with `dynamic()` / `React.lazy()`

**Polish**
- [ ] Transitions/animations feel smooth (not jarring)
- [ ] Consistent spacing using design tokens
- [ ] Dark mode works (if applicable)
- [ ] Font loading doesn't cause FOUT

---

## Platform-Specific Reference Files

Load the relevant reference when working on platform-specific patterns:
- **React / Next.js deep patterns** → `references/react-nextjs.md`
- **React Native / Expo** → `references/react-native.md`
- **SwiftUI (iOS)** → `references/swiftui.md`
- **Jetpack Compose (Android)** → `references/compose.md`
- **Styling & Design Systems** → `references/styling.md`

---

## Output Standards

1. **Complete, runnable code** — not pseudocode or skeletons unless asked
2. **TypeScript types** — every prop, hook return, and API response typed
3. **Named exports for components** — default export only for page-level files
4. **Separate concerns** — data-fetching logic in hooks, not JSX
5. **File paths included** — always show where each file lives
