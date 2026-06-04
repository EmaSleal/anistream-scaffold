# Anistream — Design System

> Especificaciones visuales completas del clon de Crunchyroll. Fuente de verdad para todos los tokens de diseño, componentes y patrones de UI.

---

## Tabla de contenidos

1. [Paleta de colores](#1-paleta-de-colores)
2. [Tipografía](#2-tipografía)
3. [Espaciado y layout](#3-espaciado-y-layout)
4. [Bordes y radios](#4-bordes-y-radios)
5. [Elevación y sombras](#5-elevación-y-sombras)
6. [Movimiento y transiciones](#6-movimiento-y-transiciones)
7. [Z-index layers](#7-z-index-layers)
8. [Componentes — Home](#8-componentes--home)
9. [Componentes — Player](#9-componentes--player)
10. [Accesibilidad](#10-accesibilidad)
11. [Responsive breakpoints](#11-responsive-breakpoints)

---

## 1. Paleta de colores

Todos los tokens están declarados como CSS custom properties en `src/styles/globals.css`.

### Brand

| Token | Valor | Uso |
|-------|-------|-----|
| `--color-brand` | `#F47521` | CTAs, progress bar, links activos, dots activos |
| `--color-brand-hover` | `#E06318` | Hover de botones primarios |
| `--color-brand-dim` | `rgba(244,117,33,0.15)` | Fondos de tags de género |

### Fondos

| Token | Valor | Uso |
|-------|-------|-----|
| `--color-bg-primary` | `#000000` | Fondo de página, zona de video |
| `--color-bg-surface` | `#141414` | Superficies secundarias |
| `--color-bg-card` | `#1E1E1E` | Cards de anime (portrait y landscape) |
| `--color-bg-card-hover` | `#282828` | Estado hover de cards |
| `--color-bg-overlay` | `rgba(0,0,0,0.75)` | Overlays y badges tipo "Visto" |

### Texto

| Token | Valor | Uso |
|-------|-------|-----|
| `--color-text-primary` | `#FFFFFF` | Títulos, nombres de series, texto principal |
| `--color-text-secondary` | `rgba(255,255,255,0.60)` | Metadatos, formatos (Dub \| Sub), descripciones |
| `--color-text-muted` | `rgba(255,255,255,0.35)` | Fechas, labels de audio, separadores |
| `--color-text-brand` | `#F47521` | Links de serie en el player, "VER MÁS" |

### Bordes

| Token | Valor | Uso |
|-------|-------|-----|
| `--color-border` | `rgba(255,255,255,0.08)` | Divisores sutiles entre paneles |
| `--color-border-hover` | `rgba(255,255,255,0.20)` | Bordes en hover |
| `--color-border-strong` | `rgba(255,255,255,0.30)` | Botón de bookmark, controles del player |

### Player específico

| Token | Valor | Uso |
|-------|-------|-----|
| `--color-progress-track` | `rgba(255,255,255,0.20)` | Track de la barra de progreso |
| `--color-progress-fill` | `#F47521` | Fill de la barra de progreso |
| `--color-ctrl-icon` | `rgba(255,255,255,0.85)` | Iconos de controles del player |

---

## 2. Tipografía

**Font family principal:** `Nunito` (Google Fonts) — `system-ui, -apple-system, sans-serif` como fallback.

```css
--font-sans:  'Nunito', system-ui, -apple-system, sans-serif;
--font-mono:  'SFMono-Regular', 'Consolas', 'Liberation Mono', monospace;
```

> `--font-mono` se usa exclusivamente en el display de tiempo del player (`15:57 / 24:15`).

### Escala tipográfica

| Elemento | Font-size | Font-weight | Color | Notas |
|----------|-----------|-------------|-------|-------|
| Hero title | `36px` | `800` | `#fff` | `letter-spacing: -0.01em` |
| Ep title (player) | `22px` | `700` | `#fff` | `line-height: 1.25` |
| Section row label | `17px` | `700` | `#fff` | Margen-bottom `14px` |
| Nav tab | `14px` | `500–600` | `rgba(255,255,255,0.65)` | Activo: `#fff` + bg |
| CTA button | `14–16px` | `600` | `#fff` | — |
| Card title | `12px` | `500` | `#fff` | Truncado 1 línea |
| Series link (player) | `13px` | `600` | `#F47521` | — |
| Metadata secundario | `12–13px` | `400` | `rgba(255,255,255,0.55–0.65)` | — |
| Badge de rating | `10px` | `600` | `rgba(255,255,255,0.75)` | — |
| Card sub (Dub\|Sub) | `10px` | `400` | `rgba(255,255,255,0.50)` | — |
| Sidebar heading | `11px` | `600` | `rgba(255,255,255,0.50)` | `uppercase`, `letter-spacing: 0.08em` |
| Time display | `12px` | `400` | `rgba(255,255,255,0.75)` | `font-family: mono` |
| Badge "Visto" | `9px` | `600` | `rgba(255,255,255,0.75)` | — |
| Footer legal | `10px` | `400` | `rgba(255,255,255,0.25)` | — |

---

## 3. Espaciado y layout

### Contenedor

```css
max-width: 1440px;
margin: 0 auto;
padding: 0 24px;   /* desktop */
padding: 0 16px;   /* mobile  */
```

### Navbar

```
height: 60px (--nav-height)
padding: 0 24px
```

### Escala de espaciado

| Token | Valor | Uso frecuente |
|-------|-------|---------------|
| `--space-1` | `4px` | Gaps mínimos internos |
| `--space-2` | `8px` | Gap entre cards en row |
| `--space-3` | `12px` | Gap en browse grid |
| `--space-4` | `16px` | Padding interno de cards |
| `--space-5` | `20px` | Padding del sidebar del player |
| `--space-6` | `24px` | Padding estándar de contenedor |
| `--space-8` | `32px` | Gap entre secciones de la home |
| `--space-10` | `40px` | Padding top de páginas internas |

### Cards

| Tipo | Dimensiones | Aspect ratio |
|------|-------------|--------------|
| Portrait (catálogo) | `140px ancho` | `2:3` |
| Landscape (continue watching) | `~280px ancho` | `16:9` aprox. |
| Episode card (sidebar) | `88×54px thumbnail` | `16:9` |

### Browse grid

```css
grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
gap: 12px;
```

---

## 4. Bordes y radios

| Token | Valor | Uso |
|-------|-------|-----|
| `--radius-sm` | `3px` | Badges de rating, badges "Visto" |
| `--radius-md` | `6px` | Cards de anime, botones |
| `--radius-lg` | `8px` | Episode cards en sidebar, contenedores |
| `--radius-pill` | `20px` | Nav tabs (efecto pill) |

**Regla importante:** Los nav tabs usan `border-radius: 20px` para el estado activo. Los botones de acción usan `4–6px`. Nunca aplicar `border-radius` grande a elementos con `border-left` o `border-top` únicamente.

---

## 5. Elevación y sombras

El sistema de diseño es **flat** — sin `box-shadow` decorativo. Las únicas excepciones son:

- **Progress thumb:** `box-shadow: 0 0 0 4px rgba(244,117,33,0.30)` — comunica el estado interactivo del scrubber.
- **Focus rings (accesibilidad):** `box-shadow: 0 0 0 2px #F47521` o `outline: 2px solid var(--color-brand)`.

La profundidad se comunica mediante **opacidad de color** y **gradientes de overlay**, no sombras.

---

## 6. Movimiento y transiciones

| Token | Valor | Uso |
|-------|-------|-----|
| `--transition-fast` | `0.12s ease` | Hover de iconos, cambios de color |
| `--transition-base` | `0.20s ease` | Cards hover scale, nav bg |
| `--transition-slow` | `0.35s ease` | Navbar scroll-hide, overlay hero |

### Comportamientos específicos

**Cards de anime (hover):**
```css
transform: scale(1.04);
transition: transform 0.20s ease;
```

**Barra de progreso (hover):**
```css
/* Track */
height: 4px → 6px;
transition: height 0.12s ease;

/* Thumb */
opacity: 0 → 1;
transition: opacity 0.12s ease;
```

**Controles del player (auto-hide):**
```css
opacity: 1 → 0;
transition: opacity 0.20s ease;
/* Delay: 3000ms sin mousemove */
```

**Dot indicator activo:**
```css
width: 8px → 24px;
transition: width 0.20s ease;
```

**Botones (active state):**
```css
transform: scale(0.97);
transition: transform 0.12s ease;
```

---

## 7. Z-index layers

| Token | Valor | Elemento |
|-------|-------|---------|
| `--z-base` | `0` | Contenido estándar |
| `--z-card` | `10` | Cards en hover |
| `--z-overlay` | `50` | Controles del player, overlays de gradiente |
| `--z-nav` | `100` | Navbar (position: fixed) |
| `--z-modal` | `200` | Modales y drawers futuros |
| `--z-player` | `300` | Player en fullscreen |

---

## 8. Componentes — Home

### Navbar

```
Altura:         60px (fija, position: fixed)
BG default:     linear-gradient(to bottom, rgba(0,0,0,0.95), transparent)
BG scrolled:    rgba(0,0,0,0.97) + backdrop-filter: blur(8px)
Logo:           28×28px SVG circular naranja + texto "anistream" 16px/800
Tabs:           14px/500, padding 6px 14px, border-radius 20px
Tab activo:     bg rgba(255,255,255,0.15), color #fff, font-weight 600
Iconos:         36×36px hit area, color rgba(255,255,255,0.75)
Avatar:         32×32px, border-radius 50%, bg #F47521
```

### Hero Banner

```
Min-height:     520px
BG:             Imagen full-bleed + overlay izquierda:
                linear-gradient(to right, #000 0%, rgba(0,0,0,0.7) 40%, transparent 70%)
                + overlay inferior:
                linear-gradient(to top, #000 0%, transparent 40%)

Rating badge:   10px/600, bg rgba(255,255,255,0.12), padding 3px 7px, radius 3px
Géneros:        12px, color rgba(255,255,255,0.60), separador "·"
Descripción:    -webkit-line-clamp: 3 (truncado con fade)

CTA primario:   bg #F47521, color #fff, radius 6px, padding 13px 28px, 16px/600
                Ícono play SVG a la izquierda
Bookmark btn:   44×44px, bg rgba(255,255,255,0.10), border 1.5px rgba(255,255,255,0.30)
                Estado activo: color #F47521, border-color #F47521

Dots:           8×8px inactivo (rgba(255,255,255,0.30))
                24×8px activo (#F47521), border-radius 4px
                Posición: absolute, bottom 28px, left 32px
```

### Anime Card (portrait)

```
Ancho:          140px (flex-shrink: 0 en row)
Aspect ratio:   2:3 (thumbnail)
BG:             #1E1E1E
Border-radius:  6px
Hover:          scale(1.04)

Thumbnail:      Next/Image fill, object-fit: cover
Overlay hover:  linear-gradient(to top, rgba(0,0,0,0.6) 0%, transparent 50%), opacity 0→1

Título:         12px/500, #fff, truncado 1 línea
Sub (Dub|Sub):  10px, rgba(255,255,255,0.50)
Menú "···":     14px, rgba(255,255,255,0.35), hover #fff
```

### Series Row

```
Section label:  17px/700, #fff, padding 0 24px, margin-bottom 14px
Row:            display flex, gap 8px, overflow-x auto
                scroll-snap-type: x mandatory
                scrollbar-width: none (oculto)
Padding:        0 24px 8px (para que no se corte la sombra de hover)
```

### Continue Watching Card

```
Ancho:          ~280px (landscape)
Aspect ratio:   approx 16:9
Overlay play:   32×32px, bg rgba(255,255,255,0.85), border-radius 50%
Time left:      posición absolute bottom-right, bg rgba(0,0,0,0.70), 9px/600
Progress bar:   2px height, bg #F47521, base del thumbnail
Título:         12px/500, #fff
Episodio:       10px, rgba(255,255,255,0.50)
```

---

## 9. Componentes — Player

### Layout general del player

```
Video zone:     100vw × aspect-ratio 16/9, bg #000
                position: relative (controles en absolute)

Meta panel:     grid-template-columns: 1fr 300px
                border-top: 0.5px solid rgba(255,255,255,0.08)

Meta left:      padding 24px 28px
                border-right: 0.5px solid rgba(255,255,255,0.08)

Sidebar:        width 300px fijo, padding 20px 18px

Footer:         padding 20px 28px
                border-top: 0.5px solid rgba(255,255,255,0.06)
                layout: flex, space-between
```

### Barra de progreso

```
Track:          height 4px, bg rgba(255,255,255,0.20), border-radius 2px
                hover → height 6px, transition 0.12s ease
                cursor: pointer
                role="slider" (accesible via teclado: ← → arrow keys)

Fill:           bg #F47521, height 100% del track
                pointer-events: none (clics van al track)

Thumb:          14×14px, border-radius 50%, bg #F47521
                box-shadow: 0 0 0 4px rgba(244,117,33,0.30)
                opacity: 0 en reposo → 1 en hover, transition 0.12s
                position: absolute, right -7px, top 50%, translateY(-50%)
```

### Barra de controles

```
Layout:         flex, space-between, padding 6px 14px 12px
BG:             linear-gradient(to top, rgba(0,0,0,0.85), transparent)
Altura total:   ~44px

Iconos:         20px, color rgba(255,255,255,0.85)
                hover: color #fff + scale(1.1), transition 0.12s

Lado izquierdo (orden):
  ⟳  Rewind 10s
  ▶  Play / Pause  (color #fff, ligeramente mayor)
  ↺  Forward 10s
  🔊 Mute toggle
  MM:SS / MM:SS  (12px mono, rgba(255,255,255,0.75))

Lado derecho (orden):
  CC  Subtítulos
  1x  Velocidad (badge: border 0.5px rgba(255,255,255,0.30), radius 3px, padding 2px 6px, 11px/600)
  ⛶  Fullscreen
```

### Controles superiores del video

```
Posición:       absolute, top 12px, right 14px
Íconos:         ⚙ Settings + ⛶ Fullscreen
Color:          rgba(255,255,255,0.70), hover #fff
Gap:            10px
```

### Panel de metadatos — izquierda

```
Series link:    13px/600, #F47521, hover opacity 0.80, margin-bottom 8px
Ep title:       22px/700, #fff, line-height 1.25, margin-bottom 10px
Rating badge:   10px/600, bg rgba(255,255,255,0.12), padding 3px 7px, radius 3px
Format text:    11px, rgba(255,255,255,0.50), separador "·"
Fecha:          12px, rgba(255,255,255,0.40), margin-bottom 16px

Reacciones:     flex, gap 16px
  Like/Dislike: 13px, rgba(255,255,255,0.65), hover #fff
  Share:        margin-left auto, rgba(255,255,255,0.50)

Descripción:    13px, rgba(255,255,255,0.55), line-height 1.65
Audio row:      flex space-between, 12px
  Label:        rgba(255,255,255,0.35)
  Valor:        rgba(255,255,255,0.50)

"VER MÁS":     12px/600, #F47521, hover opacity 0.75
```

### Sidebar — episodios

```
Heading:        11px/600, uppercase, letter-spacing 0.08em, rgba(255,255,255,0.50)

Episode card:
  Layout:       flex, gap 10px
  Thumbnail:    90×56px, radius 4px, bg #1A1A1A
  "Visto" badge: absolute bottom-right, bg rgba(0,0,0,0.75), 9px, radius 3px
  Título:       12px/500, #fff, -webkit-line-clamp: 2
  Formato:      10px, rgba(255,255,255,0.40)
  Hover card:   bg rgba(255,255,255,0.06), radius 6px

"Ver más" btn:
  width 100%, bg transparent
  border: 0.5px solid rgba(255,255,255,0.20)
  radius 6px, padding 9px, 12px/600
  color rgba(255,255,255,0.70)
  hover: border-color rgba(255,255,255,0.40), color #fff
```

### Auto-hide de controles

```
Trigger:        mousemove sobre el video
Delay:          3000ms de inactividad
Transición:     opacity 0.20s ease
Excepción:      NO se ocultan si el video está pausado
Implementación: debounce(50ms) en mousemove para evitar thrashing
```

---

## 10. Accesibilidad

### Principios aplicados

- Todos los botones iconográficos tienen `aria-label` descriptivo
- La barra de progreso usa `role="slider"` con `aria-valuemin`, `aria-valuemax`, `aria-valuenow`, `aria-valuetext`
- Navegación con teclado en el progress bar: `←` -5s, `→` +5s
- El carousel de slides usa `role="tablist"` + `role="tab"` + `aria-selected`
- Imágenes decorativas tienen `aria-hidden="true"` o `alt=""`
- El video tiene `<track kind="captions">` para subtítulos
- Clase `.sr-only` disponible para contenido solo para lectores de pantalla
- Focus visible con outline naranja: `outline: 2px solid #F47521`
- Botón bookmark usa `aria-pressed` para estado

### Color contrast

| Combinación | Ratio estimado | Estado |
|-------------|---------------|--------|
| `#fff` sobre `#000` | 21:1 | ✅ AAA |
| `#F47521` sobre `#000` | 4.6:1 | ✅ AA |
| `rgba(255,255,255,0.60)` sobre `#000` | ~7:1 | ✅ AA |
| `rgba(255,255,255,0.35)` sobre `#000` | ~4:1 | ⚠️ Límite AA (solo para texto no crítico) |

---

## 11. Responsive breakpoints

```css
/* Tablet */
@media (max-width: 1024px) {
  /* Browse grid: auto-fill minmax(140px, 1fr) se adapta automáticamente */
}

/* Mobile */
@media (max-width: 768px) {
  /* Player meta panel: 1fr (single column) */
  /* Hero: min-height 320px */
  /* Container padding: 0 16px */
  /* Card width: minmax(120px, 1fr) */
}
```

### Comportamiento de componentes

| Componente | Desktop | Tablet | Mobile |
|------------|---------|--------|--------|
| Navbar tabs | Todos visibles | Todos visibles | Ocultos (hamburger pendiente) |
| Hero | 520px min-height | 400px | 320px |
| Cards row | scroll horizontal | scroll horizontal | scroll horizontal |
| Browse grid | 7+ cols | 4–5 cols | 2–3 cols |
| Player meta | `1fr / 300px` | `1fr / 240px` | stack vertical |
| Player sidebar | 300px fijo | 240px | debajo del meta izquierdo |
