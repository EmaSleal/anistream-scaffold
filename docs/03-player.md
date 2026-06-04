# Anistream — Reproductor de Video

> Documentación técnica completa del componente de reproductor: arquitectura, comportamiento, especificaciones de UI y hoja de ruta de extensión.

---

## Tabla de contenidos

1. [Arquitectura del reproductor](#1-arquitectura-del-reproductor)
2. [Componentes involucrados](#2-componentes-involucrados)
3. [Hook: usePlayerControls](#3-hook-useplayercontrols)
4. [Especificaciones visuales detalladas](#4-especificaciones-visuales-detalladas)
5. [Flujo de estados](#5-flujo-de-estados)
6. [Accesibilidad del reproductor](#6-accesibilidad-del-reproductor)
7. [Compatibilidad cross-browser](#7-compatibilidad-cross-browser)
8. [Hoja de ruta: video real con HLS](#8-hoja-de-ruta-video-real-con-hls)
9. [Problemas conocidos y decisiones de diseño](#9-problemas-conocidos-y-decisiones-de-diseño)

---

## 1. Arquitectura del reproductor

El reproductor se compone de tres capas:

```
┌─────────────────────────────────────────────────────────┐
│  VideoPlayer.tsx          ← Orquestador principal        │
│                                                          │
│  ┌──────────────────┐   ┌─────────────────────────────┐ │
│  │  <video> nativo   │   │  usePlayerControls (hook)   │ │
│  │  ref={videoRef}   │◄──│  - Sincroniza eventos       │ │
│  │                  │   │  - Expone primitivas         │ │
│  └──────────────────┘   └─────────────────────────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  PlayerControls.tsx   ← UI de controles          │   │
│  │  ┌────────────────┐                              │   │
│  │  │ ProgressBar.tsx │ ← Barra de progreso         │   │
│  │  └────────────────┘                              │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Panel de metadatos + Sidebar de episodios       │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Principio clave:** el elemento `<video>` es la fuente de verdad. El estado de React (`playerState`) es un reflejo de los eventos del DOM — no al revés. Los comandos (play, pause, seek) modifican el elemento de video directamente; los event listeners propagan los cambios al estado.

---

## 2. Componentes involucrados

### `VideoPlayer.tsx`

Componente orquestador. Responsabilidades:

- Renderiza el elemento `<video>` y lo conecta al hook
- Renderiza los controles y el panel de metadatos
- Gestiona el layout general (video + meta + sidebar + footer)
- Delega toda la lógica de estado al hook

**Props:**

```typescript
interface VideoPlayerProps {
  episode: Episode;             // Episodio actual
  previousEpisode?: Episode;    // Para el sidebar (opcional)
  nextEpisode?: Episode;        // Para el sidebar (opcional)
}
```

### `PlayerControls.tsx`

Barra de controles inferior. Renderiza:

- `ProgressBar` (componente hijo)
- Controles izquierdos: rewind, play/pause, forward, mute, tiempo
- Controles derechos: CC, velocidad, fullscreen

**Props:**

```typescript
interface PlayerControlsProps {
  state: PlayerState;
  onTogglePlay: () => void;
  onSeek: (s: number) => void;
  onSkip: (delta: number) => void;
  onToggleMute: () => void;
  onSetPlaybackRate: (rate: number) => void;
  onToggleFullscreen: () => void;
  show: boolean;               // controla visibility (auto-hide)
}
```

### `ProgressBar.tsx`

Scrubber de progreso. Características:

- `role="slider"` accesible (teclado: ← -5s, → +5s)
- Track height: 4px en reposo, 6px en hover
- Thumb visible solo en hover/focus
- Click en cualquier punto del track hace seek proporcional

**Props:**

```typescript
interface ProgressBarProps {
  currentTime: number;   // segundos actuales
  duration: number;      // duración total en segundos
  onSeek: (seconds: number) => void;
}
```

---

## 3. Hook: usePlayerControls

### Tipo de retorno completo

```typescript
interface UsePlayerControlsReturn {
  playerState: PlayerState;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  togglePlay: () => void;
  seek: (seconds: number) => void;
  skipSeconds: (delta: number) => void;
  setVolume: (volume: number) => void;
  toggleMute: () => void;
  setPlaybackRate: (rate: number) => void;
  toggleFullscreen: (containerRef: React.RefObject<HTMLDivElement | null>) => void;
  handleMouseMove: () => void;
}
```

### `PlayerState`

```typescript
interface PlayerState {
  isPlaying: boolean;
  currentTime: number;      // segundos (float)
  duration: number;         // segundos (float)
  volume: number;           // 0.0 a 1.0
  isMuted: boolean;
  playbackRate: number;     // 0.5 | 0.75 | 1 | 1.25 | 1.5 | 2
  isFullscreen: boolean;
  showControls: boolean;    // false cuando auto-hide activo
}
```

### Sincronización de eventos

El hook registra estos event listeners sobre el elemento `<video>`:

| Evento | Actualización de estado |
|--------|------------------------|
| `play` | `isPlaying: true` |
| `pause` | `isPlaying: false`, `showControls: true` |
| `timeupdate` | `currentTime: video.currentTime` |
| `durationchange` | `duration: video.duration` |
| `volumechange` | `volume`, `isMuted` |
| `fullscreenchange` (document) | `isFullscreen: !!document.fullscreenElement` |

Todos los listeners se registran en un solo `useEffect` y se limpian en el cleanup. Esto evita memory leaks.

### Auto-hide de controles

```
mousemove → debounce(50ms) → showControls = true → scheduleHide(3000ms)
                                                          ↓
                                              isPlaying? → showControls = false
                                              !isPlaying → no cambio
```

El debounce de 50ms en `handleMouseMove` limita a ~20 actualizaciones/segundo máximo, evitando re-renders excesivos durante movimiento continuo del mouse.

### Ciclo de velocidades de reproducción

```
PLAYBACK_RATES = [0.5, 0.75, 1, 1.25, 1.5, 2]

Click en badge de velocidad → nextRate = RATES[(currentIndex + 1) % RATES.length]
```

---

## 4. Especificaciones visuales detalladas

### Layout del reproductor (desktop)

```
┌────────────────────────────────────────────────────────────────┐
│  VIDEO AREA  (100vw × aspect-ratio 16/9)                       │
│  bg: #000                                                      │
│                                               [⚙] [⛶]         │
│                                                                │
│                                                                │
│  ══════════════════════════════════════●═══════════════════   │
│  [⟳][▶][↺][🔊]  15:57 / 24:15          [CC][1x][⛶]           │
└────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────┬─────────────────────────┐
│  META LEFT                           │  SIDEBAR    (300px)     │
│  padding: 24px 28px                  │  padding: 20px 18px     │
│                                      │                         │
│  Serie link (#F47521)                │  SIGUIENTE EPISODIO     │
│  E5 – Título (22px/700)              │  [thumb] Título ep      │
│  [14+] · Sub | Dob                   │         Dob | Sub       │
│  Lanzado el 20 nov 2025              │                         │
│  [👍 951] [👎 2]           [⇪]       │  EPISODIO ANTERIOR      │
│  Descripción del episodio...         │  [thumb] Título ep      │
│  Audio  Japanese, Español, English   │         Dob | Sub       │
│  VER MÁS                             │                         │
│                                      │  [📋 VER MÁS EPISODIOS] │
├──────────────────────────────────────┴─────────────────────────┤
│  FOOTER: Anistream logo + legal                     [🌐 ES ▾]  │
└────────────────────────────────────────────────────────────────┘
```

### Barra de progreso — estados

```
REPOSO:
═══════════════════════════════════════════════════════
height: 4px | track: rgba(255,255,255,0.20) | sin thumb

HOVER / FOCUS:
═══════════════════════════════════════●═══════════════
height: 6px | thumb: 14px Ø, #F47521, glow 4px @ 0.3α

FILL:
████████████████████████████████░░░░░░░░░░░░░░░░░░░░░░
         65% #F47521                35% rgba track
```

### Velocidades de reproducción — badge

```
Tamaño:        11px / 600
Padding:       2px 6px
Border:        0.5px solid rgba(255,255,255,0.30)
Border-radius: 3px
Hover:         border-color: rgba(255,255,255,0.60), color: #fff

Ciclo:  0.5x → 0.75x → 1x → 1.25x → 1.5x → 2x → 0.5x...
```

### Episode card del sidebar

```
┌────────────────────────────────────────────┐
│ ┌──────────┐  E6 – ¡En plena temporada!    │
│ │          │  Magípez rebozado              │
│ │  thumb   │  Dob | Sub                    │
│ │  90×56   │                               │
│ │   [Visto]│                               │
│ └──────────┘                               │
└────────────────────────────────────────────┘

thumb:      90×56px, radius 4px, bg #1A1A1A
"Visto":    absolute bottom-right, bg rgba(0,0,0,0.75)
            9px/600, padding 2px 5px, radius 3px
título:     12px/500, #fff, max 2 líneas (-webkit-line-clamp: 2)
formato:    10px, rgba(255,255,255,0.40)
hover card: bg rgba(255,255,255,0.06), padding 4px, radius 6px
```

---

## 5. Flujo de estados

### Estado: reproduciendo con controles visibles (inicial)

```
isPlaying: true
showControls: true
→ Timer activo (3000ms)
→ En 3s sin movimiento: showControls = false
```

### Estado: pausado

```
isPlaying: false
showControls: true (siempre visible cuando pausado)
→ Timer cancelado
→ Controles permanecen visibles indefinidamente
```

### Estado: hover sobre video

```
mousemove → debounce(50ms) → showControls = true
                           → resetTimer(3000ms)
```

### Estado: fullscreen

```
toggleFullscreen(containerRef) → el.requestFullscreen()
document "fullscreenchange" → isFullscreen = true
→ El reproductor ocupa 100vw × 100vh
→ Los controles siguen funcionando igual
→ Escape key / F11 → exitFullscreen → isFullscreen = false
```

### Estado: seekbar drag

```
mousedown en track → seekFromEvent(clientX)
                   → video.currentTime = ratio × duration
                   → React re-render via timeupdate event
```

---

## 6. Accesibilidad del reproductor

### Barra de progreso (WCAG 2.1 AA)

```html
<div
  role="slider"
  aria-label="Video progress"
  aria-valuemin="0"
  aria-valuemax="1455"
  aria-valuenow="957"
  aria-valuetext="15:57 of 24:15"
  tabIndex={0}
>
```

Navegación con teclado:
- `←` → retrocede 5 segundos
- `→` → avanza 5 segundos
- `Home` → ir al inicio (pendiente implementar)
- `End` → ir al final (pendiente implementar)

### Botones de control

Todos los botones deben tener `aria-label` descriptivo cuando son solo iconográficos:

```tsx
<button aria-label="Pause">           {/* ✅ */}
<button aria-label="Play">            {/* ✅ */}
<button aria-label="Rewind 10 seconds">
<button aria-label="Forward 10 seconds">
<button aria-label={state.isMuted ? "Unmute" : "Mute"}>
<button aria-label={state.isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}>
```

### Captions (subtítulos)

```html
<video>
  <track kind="captions" label="English" srcLang="en" default />
  <!-- Agregar más tracks por idioma cuando haya archivos .vtt -->
</video>
```

### Controles ocultos

Cuando `showControls = false`, los controles tienen `aria-hidden="true"` y `pointer-events: none`. Esto evita que los lectores de pantalla lean controles invisibles.

---

## 7. Compatibilidad cross-browser

### Barra de progreso personalizada

El input range nativo tiene estilos diferentes en cada navegador. Se usa un `<div>` custom con lógica de click en lugar de `<input type="range">` para control total del estilo.

**Consideración:** el `<div>` custom requiere implementar `aria-*` manualmente (ya incluido).

### Fullscreen API

```typescript
// Prefijos requeridos en algunos navegadores legacy:
el.requestFullscreen?.()         // estándar
|| el.webkitRequestFullscreen?.() // Safari legacy
|| el.mozRequestFullScreen?.()    // Firefox legacy

// Ya manejado por Next.js con target ES2017+
// Los navegadores modernos no necesitan prefijos
```

### Autoplay policy

Los navegadores modernos bloquean autoplay con audio. Para iniciar reproducción automática:

```typescript
// Iniciar muteado (permitido) → usuario puede activar audio
video.muted = true;
void video.play();
```

### HLS en Safari

Safari soporta HLS nativo sin librería:

```typescript
if (Hls.isSupported()) {
  // Chrome, Firefox, Edge
  const hls = new Hls();
  hls.loadSource(hlsUrl);
  hls.attachMedia(video);
} else if (video.canPlayType("application/vnd.apple.mpegurl")) {
  // Safari — HLS nativo
  video.src = hlsUrl;
}
```

---

## 8. Hoja de ruta: video real con HLS

### Paso 1: instalar HLS.js

```bash
pnpm add hls.js
pnpm add -D @types/hls.js
```

### Paso 2: nuevo hook `useHlsPlayer`

```typescript
// src/hooks/useHlsPlayer.ts
"use client";

import { useEffect, useRef } from "react";
import Hls from "hls.js";

export function useHlsPlayer(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  src: string | undefined
) {
  const hlsRef = useRef<Hls | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return;

    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,          // Web Worker para decodificación
        lowLatencyMode: false,       // true para simulcasts en vivo
        maxBufferLength: 30,         // segundos de buffer adelantado
      });

      hlsRef.current = hls;
      hls.loadSource(src);
      hls.attachMedia(video);

      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal) {
          console.error("HLS fatal error:", data);
          hls.destroy();
        }
      });

      return () => {
        hls.destroy();
        hlsRef.current = null;
      };
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
    }
  }, [src, videoRef]);

  return hlsRef;
}
```

### Paso 3: selección de calidad

HLS.js expone niveles de calidad:

```typescript
// Obtener niveles disponibles
hls.levels // Array<Level> con { height, bitrate, name }

// Forzar calidad específica
hls.currentLevel = 2; // índice del nivel

// Auto quality (adaptativo)
hls.currentLevel = -1;
```

### Paso 4: thumbnails de preview en seekbar

Al hacer hover sobre la seekbar, mostrar un thumbnail del timestamp:

```typescript
// Requiere un archivo VTT de thumbnails o generación server-side
// El thumbnail se posiciona absolute sobre el track
```

---

## 9. Problemas conocidos y decisiones de diseño

### Decisión: div custom vs input[type=range] para la seekbar

**Alternativa evaluada:** `<input type="range">` con CSS para remover estilos nativos.

**Problema:** los estilos de `::-webkit-slider-thumb` y `::-moz-range-thumb` son inconsistentes entre navegadores y requieren reglas de vendor prefix extensas.

**Decisión:** usar `<div>` con `role="slider"` y `aria-*` manual. Da control total del DOM y estilos. El costo es implementar la accesibilidad manualmente, que ya está hecho.

### Decisión: debounce vs throttle en handleMouseMove

**Throttle** ejecuta la función a intervalos regulares durante el evento continuo.
**Debounce** ejecuta la función solo después de que el evento se detiene.

Para mostrar controles: se usa **debounce(50ms)** que actúa casi como throttle a 20fps pero con el beneficio adicional de no ejecutar la función mientras el mouse sigue moviéndose rápidamente.

### Problema conocido: iOS Safari y Fullscreen

En iOS Safari, la API `requestFullscreen()` no está disponible en `<video>` dentro de un `<div>`. En su lugar, iOS tiene `webkitEnterFullscreen()` solo en el elemento `<video>` directamente.

**Solución pendiente:**

```typescript
const toggleFullscreen = () => {
  const video = videoRef.current;
  const container = containerRef.current;

  // iOS Safari
  if ('webkitEnterFullscreen' in (video ?? {})) {
    (video as HTMLVideoElement & { webkitEnterFullscreen: () => void })
      .webkitEnterFullscreen();
    return;
  }

  // Estándar
  if (!document.fullscreenElement) {
    void container?.requestFullscreen();
  } else {
    void document.exitFullscreen();
  }
};
```

### Problema conocido: tiempo inicial

Al montar el componente, `playerState.duration` es `0` hasta que el video carga metadata. El `initialDuration` del hook permite pasar la duración conocida desde los datos del episodio para renderizar la seekbar correctamente antes de que cargue el video.

```typescript
usePlayerControls(episode.duration) // 1455 segundos desde la API
```

### Pendiente: Picture-in-Picture

```typescript
// API disponible en Chrome/Safari modernos
if ('pictureInPictureEnabled' in document) {
  void video.requestPictureInPicture();
}
```
