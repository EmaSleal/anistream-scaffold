# Anistream — Crunchyroll UI Clone

A Next.js 15 + React 19 scaffold replicating the Crunchyroll UI, built with security best practices.

## Tech Stack

| Tool | Version | Reason |
|------|---------|--------|
| Next.js | 15.x | App Router, SSR, typedRoutes |
| React | 19.x | Concurrent features |
| TypeScript | 5.8 | Strict mode |
| pnpm | 9.x | Secure dependency resolution |
| CSS Modules | built-in | Zero-runtime, scoped styles |

## Prerequisites

- Node.js ≥ 20
- pnpm ≥ 9 (`npm install -g pnpm@9`)

## Setup

```bash
pnpm install
pnpm dev
```

## Security Practices

- **pnpm** over npm: no hoisting = no dependency confusion attacks
- **Security headers** in `next.config.ts`: X-Frame-Options, CSP, XSS protection
- **Strict TypeScript**: `"strict": true`, no `any`
- **no-console** eslint rule: prevents accidental data leaks
- **Lockfile** (`pnpm-lock.yaml`) committed to git
- Run `pnpm audit` regularly; add to CI pipeline

## Project Structure

```
src/
├── app/                  # Next.js App Router pages
│   ├── page.tsx          # Home
│   ├── browse/           # Browse catalogue
│   ├── watch/[id]/       # Video player
│   ├── series/[id]/      # Series detail
│   └── my-lists/         # Watchlist
├── components/
│   ├── ui/               # Primitives: Button, Badge
│   ├── layout/           # Navbar
│   ├── home/             # HeroBanner, AnimeCard, SeriesRow
│   └── player/           # VideoPlayer, PlayerControls, ProgressBar
├── data/                 # Mock data (replace with API calls)
├── hooks/                # usePlayerControls, useWatchlist, useScrollHide
├── lib/                  # utils.ts
├── styles/               # globals.css (design tokens)
└── types/                # index.ts (domain types)
```

## Design Tokens

All tokens live in `src/styles/globals.css` as CSS custom properties:

- `--color-brand`: #F47521 (Crunchyroll orange)
- `--color-bg-primary`: #000000
- `--color-bg-card`: #1E1E1E
- `--nav-height`: 60px

## Next Steps

1. Replace mock data with a real API layer (`src/lib/api.ts`)
2. Add authentication (NextAuth.js or Clerk)
3. Integrate a real video source (HLS.js for adaptive streaming)
4. Add `pnpm audit` to your CI pipeline
5. Implement ISR/SSG for series pages
