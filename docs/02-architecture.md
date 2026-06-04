# Anistream — Arquitectura del Proyecto

> Decisiones técnicas, estructura de carpetas, convenciones de código y guía de extensión del proyecto.

---

## Tabla de contenidos

1. [Stack tecnológico](#1-stack-tecnológico)
2. [Estructura de carpetas](#2-estructura-de-carpetas)
3. [App Router — rutas y páginas](#3-app-router--rutas-y-páginas)
4. [Convenciones de código](#4-convenciones-de-código)
5. [Sistema de estilos (CSS Modules)](#5-sistema-de-estilos-css-modules)
6. [Custom Hooks](#6-custom-hooks)
7. [Tipos TypeScript](#7-tipos-typescript)
8. [Datos y capa de API](#8-datos-y-capa-de-api)
9. [Seguridad](#9-seguridad)
10. [Performance](#10-performance)
11. [Cómo extender el proyecto](#11-cómo-extender-el-proyecto)

---

## 1. Stack tecnológico

| Herramienta | Versión | Justificación |
|-------------|---------|---------------|
| **Next.js** | 15.x | App Router, SSR/SSG/ISR, `typedRoutes`, image optimization |
| **React** | 19.x | Concurrent features, `use()` hook para data fetching futuro |
| **TypeScript** | 5.8 | Strict mode — cero `any` en el codebase |
| **CSS Modules** | built-in | Zero-runtime, scoped automático, sin dependencias |
| **pnpm** | 9.x | Resolución estricta, sin hoisting plano, auditoría integrada |

### Por qué Next.js sobre React puro

Crunchyroll tiene múltiples rutas con necesidades distintas de rendering:

| Ruta | Estrategia ideal | Razón |
|------|-----------------|-------|
| `/` | SSG + ISR | Contenido featured cambia diariamente |
| `/browse` | SSG + ISR | Catálogo estable, actualización esporádica |
| `/series/[id]` | SSG + ISR | SEO crítico para descubrimiento orgánico |
| `/watch/[id]` | SSR o Client | Requiere auth, progreso personalizado |
| `/my-lists` | Client-only | Datos 100% del usuario |

Next.js permite esta granularidad sin configuración adicional. React puro (Vite/CRA) no.

### Por qué CSS Modules sobre Tailwind

- **Zero-runtime:** no se envía CSS innecesario al cliente
- **Colocación:** cada componente tiene su `.module.css` junto al `.tsx`
- **Tipado:** los class names son strings locales, sin riesgo de colisiones
- **Sin dependencias:** Tailwind requiere compilación, PostCSS, configuración de purge

---

## 2. Estructura de carpetas

```
anistream/
├── public/
│   └── fonts/                    # Fuentes locales (si se migra de Google Fonts)
│
├── src/
│   ├── app/                      # Next.js App Router
│   │   ├── layout.tsx            # Root layout: <html>, <body>, Navbar
│   │   ├── page.tsx              # Home "/"
│   │   ├── browse/
│   │   │   └── page.tsx          # "/browse"
│   │   ├── watch/
│   │   │   └── [id]/
│   │   │       └── page.tsx      # "/watch/:episodeId"
│   │   ├── series/
│   │   │   └── [id]/
│   │   │       └── page.tsx      # "/series/:seriesId"
│   │   └── my-lists/
│   │       └── page.tsx          # "/my-lists"
│   │
│   ├── components/
│   │   ├── ui/                   # Primitivos reutilizables (Button, Badge)
│   │   ├── layout/               # Navbar, Footer (futuros)
│   │   ├── home/                 # HeroBanner, AnimeCard, SeriesRow
│   │   ├── player/               # VideoPlayer, PlayerControls, ProgressBar
│   │   ├── series/               # (reservado: EpisodeList, SeriesHeader)
│   │   └── browse/               # (reservado: FilterBar, BrowseGrid)
│   │
│   ├── data/
│   │   ├── mock-series.ts        # Datos de prueba — reemplazar con API
│   │   └── mock-episodes.ts      # Datos de prueba — reemplazar con API
│   │
│   ├── hooks/
│   │   ├── usePlayerControls.ts  # Estado completo del reproductor
│   │   ├── useWatchlist.ts       # CRUD de watchlist en localStorage
│   │   └── useScrollHide.ts      # Detección de scroll para navbar
│   │
│   ├── lib/
│   │   └── utils.ts              # Funciones puras: formatDuration, clamp, cn...
│   │
│   ├── styles/
│   │   └── globals.css           # Design tokens (CSS variables) + reset
│   │
│   └── types/
│       └── index.ts              # Tipos de dominio: Series, Episode, User...
│
├── .gitignore
├── .npmrc                        # Configuración de pnpm
├── eslint.config.mjs             # ESLint flat config
├── next.config.ts                # Next.js + security headers
├── package.json
├── README.md
└── tsconfig.json                 # TypeScript strict mode
```

### Convención de nomenclatura de archivos

| Tipo | Convención | Ejemplo |
|------|-----------|---------|
| Componentes React | PascalCase | `AnimeCard.tsx` |
| CSS Modules | PascalCase + `.module.css` | `AnimeCard.module.css` |
| Hooks | camelCase + `use` prefix | `usePlayerControls.ts` |
| Utilidades | camelCase | `utils.ts` |
| Tipos | camelCase | `index.ts` |
| Páginas (App Router) | siempre `page.tsx` | `page.tsx` |
| Layouts | siempre `layout.tsx` | `layout.tsx` |

---

## 3. App Router — rutas y páginas

### Jerarquía de layouts

```
src/app/layout.tsx          ← Root: aplica a TODAS las rutas
├── page.tsx                ← "/"
├── browse/page.tsx         ← "/browse"
├── my-lists/page.tsx       ← "/my-lists"
├── series/[id]/page.tsx    ← "/series/one-piece"
└── watch/[id]/page.tsx     ← "/watch/ptmm-e5"
```

> **Nota:** La página `/watch/[id]` podría necesitar su propio `layout.tsx` en el futuro para ocultar la Navbar durante la reproducción en fullscreen.

### Params en App Router (Next.js 15)

En Next.js 15, `params` es una `Promise`. Siempre usar `await`:

```typescript
// ✅ Correcto
export default async function WatchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
}

// ❌ Incorrecto (Next.js 14 y anterior)
export default function WatchPage({ params }: { params: { id: string } }) {
  const { id } = params; // Error en Next.js 15
}
```

### Metadata dinámica

```typescript
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const series = await fetchSeries(id); // cuando exista la API
  return {
    title: series.title,
    description: series.description,
    openGraph: {
      images: [series.bannerUrl],
    },
  };
}
```

---

## 4. Convenciones de código

### Componentes

```typescript
// 1. Imports primero (externos → internos → tipos)
import { useState } from "react";
import Link from "next/link";
import type { Series } from "@/types";
import { Button } from "@/components/ui/Button";
import styles from "./MyComponent.module.css";

// 2. Interface de props con nombre explícito
interface MyComponentProps {
  series: Series;
  onSelect?: (id: string) => void; // callbacks opcionales con ?
}

// 3. Named export (no default)
export function MyComponent({ series, onSelect }: MyComponentProps) {
  // ...
}
```

**Por qué named exports:** facilitan el tree-shaking y hacen los imports más explícitos. `export default` puede llevar a imports ambiguos como `import Foo from "./MyComponent"`.

### Handlers de eventos

```typescript
// ✅ Nombrar con "handle" prefix
const handleCardClick = () => { ... };
const handleVolumeChange = (value: number) => { ... };

// ❌ Evitar lambdas inline en JSX para lógica no-trivial
<button onClick={() => { doComplexThing(); updateState(); }}>
```

### Void en promesas

```typescript
// ✅ Cuando la promesa no necesita await
void video.play();
void el.requestFullscreen();

// Las promesas ignoradas sin void generan warning de TypeScript strict
```

### Alias de paths

Usar siempre `@/` en lugar de rutas relativas largas:

```typescript
// ✅
import { cn } from "@/lib/utils";
import type { Series } from "@/types";

// ❌
import { cn } from "../../../lib/utils";
```

---

## 5. Sistema de estilos (CSS Modules)

### Estructura de un módulo

```css
/* ComponentName.module.css */

/* 1. Clase raíz del componente */
.wrapper { ... }

/* 2. Elementos internos */
.header { ... }
.body { ... }

/* 3. Variantes (si aplica) */
.wrapper.large { ... }
.wrapper.active { ... }

/* 4. Estados interactivos */
.item:hover { ... }
.item:focus-visible { ... }

/* 5. Media queries al final */
@media (max-width: 768px) { ... }
```

### Combinar clases condicionalmente

Usar la función `cn()` de `src/lib/utils.ts` (sin dependencia externa):

```typescript
import { cn } from "@/lib/utils";

// En JSX
<div className={cn(
  styles.card,
  isActive && styles.active,
  size === "large" && styles.large,
  className  // permitir override desde el padre
)}>
```

### Tokens en CSS Modules

Los CSS Modules tienen acceso completo a los custom properties de `globals.css`:

```css
.button {
  background: var(--color-brand);        /* ✅ usa token */
  color: #fff;
  transition: background var(--transition-fast); /* ✅ usa token */
}

/* ❌ Evitar hardcodear valores que existen como tokens */
.button {
  background: #F47521;
  transition: background 0.12s ease;
}
```

---

## 6. Custom Hooks

### `usePlayerControls`

Encapsula **todo** el estado y la lógica del reproductor de video.

```typescript
const {
  playerState,      // { isPlaying, currentTime, duration, volume, isMuted, ... }
  videoRef,         // ref para el elemento <video>
  togglePlay,       // () => void
  seek,             // (seconds: number) => void
  skipSeconds,      // (delta: number) => void — skip +/- N segundos
  setVolume,        // (volume: number) => void — 0 a 1
  toggleMute,       // () => void
  setPlaybackRate,  // (rate: number) => void — 0.5, 0.75, 1, 1.25, 1.5, 2
  toggleFullscreen, // (containerRef) => void
  handleMouseMove,  // () => void — debounced, para auto-hide
} = usePlayerControls(initialDuration);
```

**Decisión de diseño:** el hook sincroniza los eventos nativos del `<video>` (play, pause, timeupdate, etc.) hacia el estado de React. Esto evita polling con `setInterval` y mantiene el estado siempre en sincronía con el elemento nativo.

### `useWatchlist`

Persiste en `localStorage`. Cuando se integre autenticación, este hook debe migrar a llamadas de API.

```typescript
const {
  watchlist,          // WatchlistItem[]
  isInWatchlist,      // (seriesId: string) => boolean
  toggleWatchlist,    // (seriesId: string) => void
} = useWatchlist();
```

### `useScrollHide`

```typescript
const isScrolled = useScrollHide(threshold = 60); // true si scroll > threshold px
```

Usado en Navbar para cambiar el fondo de transparente a sólido al hacer scroll.

---

## 7. Tipos TypeScript

Todos los tipos de dominio están en `src/types/index.ts`. No dispersar tipos entre archivos de componentes.

### Tipos principales

```typescript
Series       // Una serie de anime completa
Episode      // Un episodio específico con progreso
WatchlistItem // Referencia a serie en watchlist del usuario
User         // Datos del usuario autenticado
PlayerState  // Estado completo del reproductor en un momento dado
SortOption   // Union type para opciones de ordenamiento
Genre        // Union type de géneros disponibles
AudioFormat  // "sub" | "dub" | "dub-sub"
ContentRating // "G" | "PG" | "PG-13" | "14+" | "17+" | "R"
```

### Principio: tipos de dominio vs tipos de UI

```typescript
// Tipo de DOMINIO — va en src/types/index.ts
interface Series {
  id: string;
  title: string;
  // ...
}

// Tipo de UI/componente — va en el archivo del componente
interface AnimeCardProps {
  series: Series;
  onSelect?: (id: string) => void;
}
```

---

## 8. Datos y capa de API

### Estado actual (mock)

```
src/data/mock-series.ts     → Array<Series> estático
src/data/mock-episodes.ts   → Array<Episode> estático
```

### Migración a API real

Crear `src/lib/api.ts` con todas las funciones de fetch:

```typescript
// src/lib/api.ts

const API_BASE = process.env.NEXT_PUBLIC_API_URL;

export async function fetchFeaturedSeries(): Promise<Series[]> {
  const res = await fetch(`${API_BASE}/series/featured`, {
    next: { revalidate: 3600 }, // ISR: revalidar cada hora
  });
  if (!res.ok) throw new Error("Failed to fetch featured series");
  return res.json() as Promise<Series[]>;
}

export async function fetchEpisode(id: string): Promise<Episode> {
  const res = await fetch(`${API_BASE}/episodes/${id}`, {
    cache: "no-store", // SSR: siempre fresco (incluye progreso del usuario)
  });
  if (!res.ok) throw new Error(`Episode ${id} not found`);
  return res.json() as Promise<Episode>;
}
```

### Variables de entorno

```bash
# .env.local (nunca commitear)
NEXT_PUBLIC_API_URL=https://api.anistream.com
DATABASE_URL=postgresql://...
NEXTAUTH_SECRET=...
NEXTAUTH_URL=http://localhost:3000
```

> Prefijo `NEXT_PUBLIC_` = expuesto al cliente. Sin prefijo = solo servidor.

---

## 9. Seguridad

### pnpm + .npmrc

```ini
# .npmrc
public-hoist-pattern[]=*
strict-peer-dependencies=false
auto-install-peers=true
audit=true
```

- **Sin hoisting plano:** cada paquete accede solo a sus propias dependencias declaradas. Elimina ataques de dependency confusion.
- **audit=true:** `pnpm install` ejecuta auditoría automáticamente.

### Security headers (next.config.ts)

```typescript
headers: async () => [{
  source: "/(.*)",
  headers: [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options",        value: "DENY" },
    { key: "X-XSS-Protection",       value: "1; mode=block" },
    { key: "Referrer-Policy",        value: "strict-origin-when-cross-origin" },
    { key: "Permissions-Policy",     value: "camera=(), microphone=(), geolocation=()" },
  ],
}]
```

| Header | Protege contra |
|--------|---------------|
| `X-Content-Type-Options: nosniff` | MIME type sniffing attacks |
| `X-Frame-Options: DENY` | Clickjacking via iframes |
| `X-XSS-Protection` | XSS en navegadores legacy |
| `Referrer-Policy` | Filtración de URLs en referer headers |
| `Permissions-Policy` | Acceso no autorizado a hardware del dispositivo |

### Content Security Policy (pendiente)

Agregar como siguiente paso:

```typescript
{
  key: "Content-Security-Policy",
  value: [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",  // ajustar según necesidad
    "style-src 'self' 'unsafe-inline' fonts.googleapis.com",
    "font-src 'self' fonts.gstatic.com",
    "img-src 'self' data: blob:",
    "media-src 'self' blob:",
  ].join("; ")
}
```

### TypeScript strict mode

```json
// tsconfig.json
{
  "compilerOptions": {
    "strict": true,           // habilita todas las verificaciones estrictas
    "noEmit": true,           // solo type-check, Next.js compila
    "allowJs": false          // solo TypeScript, sin escape hatch a JS
  }
}
```

### ESLint

```javascript
// eslint.config.mjs
rules: {
  "@typescript-eslint/no-unused-vars": "error",   // elimina dead code
  "@typescript-eslint/no-explicit-any": "error",   // sin escape a any
  "no-console": ["warn", { allow: ["error"] }],    // previene logs accidentales
}
```

---

## 10. Performance

### Next/Image

Todos los thumbnails y banners usan `next/image`:

```tsx
<Image
  src={series.thumbnailUrl}
  alt={series.title}
  fill                                         // relative parent
  sizes="(max-width: 768px) 140px, 160px"     // responsive srcset
  placeholder="blur"
  blurDataURL="data:image/png;base64,..."      // placeholder de baja resolución
/>
```

Beneficios automáticos: formato WebP/AVIF, lazy loading, prevención de CLS.

### Scroll horizontal sin JS

Las filas de cards usan CSS puro:

```css
.row {
  overflow-x: auto;
  scroll-snap-type: x mandatory;   /* snap por card */
  scrollbar-width: none;           /* oculta scrollbar en Firefox */
}
.row::-webkit-scrollbar { display: none; } /* Chrome/Safari */
.card { scroll-snap-align: start; }
```

### Debounce en eventos frecuentes

```typescript
// usePlayerControls.ts
const handleMouseMove = useCallback(
  debounce(() => {
    setPlayerState((prev) => ({ ...prev, showControls: true }));
    scheduleHideControls();
  }, 50), // máximo 20 llamadas por segundo
  [scheduleHideControls]
);
```

### Web Vitals a monitorear

| Métrica | Target | Componente crítico |
|---------|--------|-------------------|
| LCP | < 2.5s | Hero banner image |
| CLS | < 0.1 | Cards con aspect-ratio definido |
| FID/INP | < 200ms | Player controls |
| TTFB | < 800ms | SSR/ISR pages |

---

## 11. Cómo extender el proyecto

### Agregar una nueva página

1. Crear `src/app/nueva-ruta/page.tsx`
2. Exportar `metadata` para SEO
3. Si tiene rutas dinámicas: `src/app/cosa/[id]/page.tsx`

```typescript
// src/app/nueva-ruta/page.tsx
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Nueva Ruta" };

export default function NuevaRutaPage() {
  return <div>contenido</div>;
}
```

### Agregar un nuevo componente

1. Crear `src/components/[categoria]/NombreComponente.tsx`
2. Crear `src/components/[categoria]/NombreComponente.module.css`
3. Exportar como named export
4. Agregar tipos de props en el mismo archivo (si son simples) o en `src/types/index.ts` (si son de dominio)

### Agregar un nuevo hook

1. Crear `src/hooks/useNombreHook.ts`
2. Incluir `"use client"` al inicio (los hooks son siempre client-side)
3. Retornar un objeto tipado con todas las primitivas

### Integrar HLS.js para video real

```bash
pnpm add hls.js
pnpm add -D @types/hls.js
```

```typescript
// En usePlayerControls.ts o un nuevo useHlsPlayer.ts
import Hls from "hls.js";

useEffect(() => {
  const video = videoRef.current;
  if (!video || !src) return;

  if (Hls.isSupported()) {
    const hls = new Hls({ enableWorker: true });
    hls.loadSource(src);
    hls.attachMedia(video);
    return () => hls.destroy();
  } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
    // Safari: HLS nativo
    video.src = src;
  }
}, [src]);
```

### Integrar autenticación

Opción recomendada: **NextAuth.js v5 (Auth.js)**

```bash
pnpm add next-auth@beta
```

```typescript
// src/lib/auth.ts
import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [Google],
});
```

Rutas protegidas via middleware:

```typescript
// middleware.ts (raíz del proyecto)
export { auth as middleware } from "@/lib/auth";

export const config = {
  matcher: ["/my-lists", "/watch/:path*"],
};
```
