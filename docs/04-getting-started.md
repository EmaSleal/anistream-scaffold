# Anistream — Guía de Inicio Rápido

> Todo lo necesario para levantar el proyecto, entender el flujo de trabajo y prepararlo para producción.

---

## Tabla de contenidos

1. [Requisitos del sistema](#1-requisitos-del-sistema)
2. [Instalación](#2-instalación)
3. [Comandos disponibles](#3-comandos-disponibles)
4. [Variables de entorno](#4-variables-de-entorno)
5. [Flujo de desarrollo](#5-flujo-de-desarrollo)
6. [Checklist pre-producción](#6-checklist-pre-producción)
7. [Roadmap de funcionalidades](#7-roadmap-de-funcionalidades)
8. [Decisiones pendientes](#8-decisiones-pendientes)

---

## 1. Requisitos del sistema

| Herramienta | Versión mínima | Verificar con |
|-------------|---------------|---------------|
| Node.js | 20.0.0 | `node --version` |
| pnpm | 9.0.0 | `pnpm --version` |

### Instalar pnpm (si no está instalado)

```bash
# Opción 1: via npm (una sola vez)
npm install -g pnpm@9

# Opción 2: via corepack (recomendado — no requiere npm global)
corepack enable
corepack prepare pnpm@9 --activate
```

> **No usar npm ni yarn** — el proyecto está configurado para pnpm. Usar otro gestor de paquetes puede generar un `node_modules` con hoisting plano, que anula las protecciones de seguridad configuradas en `.npmrc`.

---

## 2. Instalación

```bash
# 1. Clonar / descomprimir el proyecto
cd anistream

# 2. Instalar dependencias (ejecuta auditoría automáticamente)
pnpm install

# 3. Levantar servidor de desarrollo
pnpm dev
```

Abrir [http://localhost:3000](http://localhost:3000) en el navegador.

---

## 3. Comandos disponibles

| Comando | Descripción |
|---------|-------------|
| `pnpm dev` | Servidor de desarrollo con Fast Refresh |
| `pnpm build` | Build de producción optimizado |
| `pnpm start` | Servidor de producción (requiere `pnpm build` previo) |
| `pnpm lint` | Verificar el código con ESLint |
| `pnpm type-check` | Verificar tipos TypeScript sin compilar |
| `pnpm audit` | Auditoría de seguridad de dependencias |

### Flujo recomendado antes de un commit

```bash
pnpm type-check  # 0 errores TypeScript
pnpm lint        # 0 warnings/errors ESLint
pnpm audit       # 0 vulnerabilidades moderate o superior
```

---

## 4. Variables de entorno

Crear un archivo `.env.local` en la raíz del proyecto (nunca commitear este archivo):

```bash
# API
NEXT_PUBLIC_API_URL=http://localhost:4000   # URL de la API durante desarrollo
# NEXT_PUBLIC_API_URL=https://api.anistream.com  # producción

# Autenticación (cuando se integre NextAuth)
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=genera-un-secret-con-openssl-rand-base64-32

# OAuth providers (opcionales)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

> Los valores con prefijo `NEXT_PUBLIC_` se exponen al cliente (navegador). Los demás son exclusivos del servidor.

---

## 5. Flujo de desarrollo

### Estructura de trabajo por feature

```
1. Crear rama:        git checkout -b feature/nombre-feature
2. Desarrollar:       pnpm dev
3. Verificar:         pnpm type-check && pnpm lint
4. Commit:            git commit -m "feat: descripción concisa"
5. Push + PR:         git push origin feature/nombre-feature
```

### Convención de commits (Conventional Commits)

```
feat:     nueva funcionalidad
fix:      corrección de bug
style:    cambios de CSS/estilos sin cambio de lógica
refactor: cambio de código sin feat ni fix
perf:     mejora de performance
docs:     documentación
chore:    build, dependencias, configuración
```

Ejemplos:
```
feat: add episode progress tracking to watchlist
fix: correct progress bar thumb positioning on Firefox
style: update hero banner gradient opacity
perf: debounce mousemove handler in player controls
```

### Agregar una nueva serie (datos mock)

Mientras no existe la API, agregar series al archivo `src/data/mock-series.ts`:

```typescript
{
  id: "chainsaw-man",            // kebab-case, único
  title: "CHAINSAW MAN — THE M...",
  slug: "chainsaw-man",
  description: "...",
  thumbnailUrl: "/images/csm-thumb.jpg",  // imagen en /public/images/
  bannerUrl: "/images/csm-banner.jpg",
  rating: "17+",
  genres: ["Action", "Horror", "Supernatural"],
  audioFormats: ["dub", "sub"],
  seasonCount: 2,
  episodeCount: 24,
  year: 2022,
  isSimulcast: false,
  isFeatured: false,
  score: 8.6,
}
```

### Agregar imágenes

Colocar imágenes en `public/images/`. Next.js sirve todo el contenido de `public/` en la raíz:

```
public/images/one-piece-banner.jpg  →  http://localhost:3000/images/one-piece-banner.jpg
```

Dimensiones recomendadas:
- Banner (hero): `1920×1080px` mínimo, formato WebP
- Thumbnail portrait: `280×400px` mínimo (ratio 2:3), formato WebP
- Thumbnail landscape: `480×270px` mínimo (ratio 16:9), formato WebP

---

## 6. Checklist pre-producción

### Seguridad

- [ ] `pnpm audit` sin vulnerabilidades moderate o superior
- [ ] Variables de entorno de producción configuradas (nunca en el código)
- [ ] `NEXTAUTH_SECRET` generado con `openssl rand -base64 32`
- [ ] Revisar headers en `next.config.ts` y agregar CSP completo
- [ ] `allowJs: false` en `tsconfig.json` (ya configurado)
- [ ] No hay `console.log` en el código (ESLint lo detecta)

### Performance

- [ ] `pnpm build` sin errores ni warnings
- [ ] Verificar que todas las imágenes usan `next/image`
- [ ] Verificar que todos los `aspect-ratio` están definidos en CSS (previene CLS)
- [ ] Web Vitals: LCP < 2.5s, CLS < 0.1 (medir con Lighthouse)
- [ ] Tamaño del bundle analizado con `ANALYZE=true pnpm build`

### Accesibilidad

- [ ] Todos los botones iconográficos tienen `aria-label`
- [ ] Progress bar tiene `role="slider"` con todos los `aria-*`
- [ ] Controles del teclado funcionan en el reproductor
- [ ] Imágenes decorativas tienen `alt=""` o `aria-hidden="true"`
- [ ] Contraste de color verificado (mínimo AA en texto principal)

### SEO

- [ ] Todas las páginas tienen `export const metadata`
- [ ] Páginas de series tienen `openGraph` images
- [ ] `generateMetadata` dinámico en páginas `[id]`

### Funcional

- [ ] El flujo de watch (`/watch/[id]`) funciona end-to-end
- [ ] La watchlist persiste entre sesiones (localStorage o API)
- [ ] El reproductor funciona en Chrome, Firefox, Safari, Edge
- [ ] El reproductor funciona en mobile (iOS Safari, Chrome Android)

---

## 7. Roadmap de funcionalidades

### Fase 1 — MVP funcional (siguiente paso)

| Feature | Prioridad | Complejidad |
|---------|-----------|-------------|
| API layer (`src/lib/api.ts`) | 🔴 Alta | Media |
| Imágenes reales en `/public/images/` | 🔴 Alta | Baja |
| Search funcional | 🔴 Alta | Media |
| Autenticación (NextAuth.js) | 🟡 Media | Alta |
| HLS.js para video real | 🟡 Media | Alta |

### Fase 2 — Experiencia completa

| Feature | Prioridad | Complejidad |
|---------|-----------|-------------|
| Progreso de episodio persistente | 🔴 Alta | Media |
| Selector de audio/subtítulos en player | 🟡 Media | Media |
| Watchlist sincronizada con cuenta | 🟡 Media | Alta |
| Página de serie completa con episodios | 🟡 Media | Media |
| Browse con filtros por género | 🟡 Media | Baja |
| Browse con sort (popularidad, fecha) | 🟢 Baja | Baja |

### Fase 3 — Features avanzados

| Feature | Prioridad | Complejidad |
|---------|-----------|-------------|
| Picture-in-Picture | 🟢 Baja | Baja |
| Calidad de video seleccionable (HLS levels) | 🟡 Media | Media |
| Preview thumbnail en seekbar hover | 🟢 Baja | Alta |
| Continue watching sincronizado | 🟡 Media | Media |
| Simulcasts en tiempo real (low-latency HLS) | 🟢 Baja | Alta |
| Modo oscuro / claro toggle | 🟢 Baja | Baja |
| PWA / offline support | 🟢 Baja | Alta |

---

## 8. Decisiones pendientes

Estas decisiones técnicas deben tomarse antes de escalar el proyecto. Se listan aquí porque impactan la arquitectura y son difíciles de revertir una vez implementadas.

### ¿Base de datos?

Si la watchlist y el progreso de episodios se guardan en el servidor, se necesita una base de datos.

**Opciones evaluadas:**

| Opción | Ventaja | Desventaja |
|--------|---------|------------|
| **PostgreSQL + Prisma** | Tipado completo, migraciones | Requiere servidor propio |
| **PlanetScale (MySQL)** | Serverless, branching | Vendor lock-in |
| **Supabase (PostgreSQL)** | Auth + DB integrado | Vendor lock-in |
| **Turso (SQLite edge)** | Latencia ultra baja | Limitaciones de queries complejas |

**Recomendación:** Supabase para MVP (auth + DB en un solo servicio), migrar a PostgreSQL propio si el proyecto escala.

### ¿Autenticación?

| Opción | Ventaja | Desventaja |
|--------|---------|------------|
| **NextAuth.js v5** | Open source, flexible | Config manual de providers |
| **Clerk** | UI pre-construida, social login fácil | Costo en escala, vendor lock-in |
| **Auth.js** | Sucesor de NextAuth, App Router nativo | Aún en beta |

**Recomendación:** Auth.js (NextAuth v5) para control total. Clerk si se quiere velocidad de implementación.

### ¿CDN para video?

| Opción | Ventaja |
|--------|---------|
| **Cloudflare Stream** | HLS automático, barato por minuto |
| **Mux** | Analytics integrado, thumbnail API |
| **AWS MediaConvert + S3 + CloudFront** | Control total, costo optimizable |
| **Bunny.net** | El más barato, buena CDN global |

**Recomendación:** Cloudflare Stream para inicio (el plan gratuito incluye 1000 minutos de video). Mux si se necesitan analytics de retención.

### ¿Estado global?

El proyecto actualmente no tiene estado global — cada componente usa sus propios hooks. Si la complejidad crece (notificaciones, estado de usuario compartido entre rutas), evaluar:

| Opción | Cuándo usar |
|--------|-------------|
| **React Context** | Estado simple compartido (tema, usuario) |
| **Zustand** | Estado complejo sin boilerplate excesivo |
| **Jotai** | Estado atómico, excelente con Next.js |
| **Redux Toolkit** | Solo si el equipo ya lo conoce bien |

**Recomendación:** empezar con React Context para el usuario autenticado. Zustand si el estado crece más allá de 3–4 slices.
