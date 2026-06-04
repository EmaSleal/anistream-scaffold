# Sprint 7 — Dashboard semanal y control de volumen

**Requerimientos:** R09, R10
**Depende de:** Sprint 6

## Objetivo
Vista ejecutiva semanal con semáforo de KPIs, control de volumen por grupo muscular y decisión estratégica sugerida.

## Tareas

- [ ] Crear `VolumeService` en `core/services/volume.service.ts`:
  - Rangos objetivo (del Compendio):
    ```typescript
    const VOLUME_TARGETS: Record<MuscleGroup, [number, number]> = {
      pecho: [12, 20],
      espalda: [14, 22],
      hombro: [12, 20],
      biceps: [10, 16],
      triceps: [10, 16],
      cuadriceps: [14, 20],
      'gluteo-isquios': [14, 20],
      pantorrilla: [12, 20],
      core: [0, 99],
    };
    ```
  - `calculateWeeklyVolume(cycleId, weekNumber)` → `Record<MuscleGroup, { sets, target, status }>`
  - `status`: `'below' | 'in-range' | 'above'`
- [ ] Crear `DashboardService` en `core/services/dashboard.service.ts`:
  - Consolida datos de `ProgressionService` + `VolumeService` + sesiones + wellness
  - `getWeeklyDashboard(cycleId, weekNumber)`:
    - `sessionCompliance: { completed, target }` → 6/6
    - `compoundsProgressed: number`
    - `avgFatigue`, `maxPain`, `avgEnergy` (desde wellness)
    - `volumeByGroup`
    - `suggestedAction`: regla:
      - Si sessionCompliance < 5/6 → "Reagendar sesiones faltantes"
      - Si maxPain ≥ 5 → "Ajustar ejercicios que causan dolor"
      - Si avgFatigue > 8 → "Reducir aislamientos"
      - Si progressionPercent < 70% dos semanas → "Aplicar deload anticipado"
      - Si todo OK → "Seguir progresión"
- [ ] Crear `SemaforoComponent` reusable en `shared/components/semaforo.component.ts`:
  - Input: kpi, value, target, direction ('higher-is-better' | 'lower-is-better')
  - Output visual: punto verde/amarillo/rojo según umbrales
- [ ] Crear `KpiCardComponent` reusable (label, valor, semáforo, subtítulo)
- [ ] Crear `DashboardComponent` en `features/dashboard/dashboard.component.ts`:
  - **Sección 1 — Resumen ejecutivo (semáforo 5 KPIs):**
    - Cumplimiento de sesiones 6/6
    - Progresión en compuestos ≥70%
    - Fatiga percibida ≤7/10
    - Dolor articular 0–2/10
    - Energía general ≥7/10
  - **Sección 2 — Tracking de rendimiento:**
    - Tabla de los 6 compuestos clave con: peso, reps, RIR, variación vs semana anterior
  - **Sección 3 — Control de volumen:**
    - Barras horizontales por grupo muscular
    - Barra resaltada verde/amarillo/rojo según rango
  - **Sección 4 — Fatiga y salud articular:**
    - Promedios de la semana (fatiga, energía, sueño, estrés)
    - Dolor por zona (máximo)
  - **Sección 5 — Decisión estratégica:**
    - Card grande con la acción sugerida
    - Checklist: ¿Progresé en compuestos? ¿Me siento recuperado? ¿Hay dolor acumulado?
  - Selector de semana (ver dashboards pasados)
- [ ] Crear `WeekClosureComponent` en `features/dashboard/week-closure.component.ts`:
  - Modal que se abre al completar la 6ª sesión de la semana
  - Checklist de cierre semanal
  - Confirma decisión sugerida o permite override
- [ ] Ruta `/dashboard` y `/dashboard/week/:number`
- [ ] Link "Dashboard" en navbar

## Criterio de aceptación

1. `/dashboard` muestra todos los KPIs con colores correctos
2. Tabla de compuestos clave muestra variación vs semana anterior
3. Barras de volumen reflejan estado correcto por grupo muscular
4. Decisión sugerida aparece según reglas
5. Se puede navegar a dashboards de semanas anteriores
6. Al completar la 6ª sesión de una semana, se abre modal de cierre
7. Todos los datos agregan correctamente desde los SessionLog del localStorage

## Hito

Al completar este sprint, **la Etapa 1 (Frontend + localStorage) está funcionalmente completa**. El usuario puede usar el sistema durante un ciclo completo de 6 semanas sin backend.
