# Sprint 6 — Historial y KPIs de progresión

**Requerimientos:** R07, R08
**Depende de:** Sprint 5

## Objetivo
El user puede ver su historial de sesiones, comparar contra la semana anterior y obtener KPIs de progresión calculados automáticamente.

## Tareas

- [ ] Crear `HistoryService` en `core/services/history.service.ts`:
  - `getSessionsByWeek(cycleId, weekNumber)`
  - `getPreviousSession(sessionType, currentDate)` → última sesión completada del mismo tipo antes de la fecha
  - `compareExercise(current: ExerciseLog, previous: ExerciseLog | null): ExerciseComparison`
    - Retorna: `'improved' | 'equal' | 'worse' | 'new'`
    - Criterio: compara máximo peso × reps y volumen total (peso × reps × sets)
- [ ] Crear `ProgressionService` en `core/services/progression.service.ts`:
  - Config de compuestos clave:
    ```typescript
    const KEY_COMPOUNDS: Record<SessionType, string> = {
      'pull-a': 'remo-barra-t',
      'push-a': 'press-banca-barra',
      'leg-a': 'hack-squat',
      'pull-b': 'dominadas',
      'push-b': 'press-militar-mancuernas',
      'leg-b': 'hip-thrust',
    };
    ```
  - `getWeeklyKPIs(cycleId, weekNumber)`:
    - `totalExercises`, `progressedExercises`, `progressionPercent`
    - `compoundsProgressed` (de los 6 clave)
    - `isolationsProgressionPercent`
  - `detectFatigueAccumulation(cycleId)` → true si últimas 2 semanas bajaron %
  - `suggestDoubleProgression(exerciseId, lastSet)`: si alcanzó top del rango de reps sugerido → sugerir +peso; si no → sugerir +reps
- [ ] Crear `HistoryComponent` en `features/history/history.component.ts`:
  - Timeline vertical con todas las sesiones completadas
  - Filtros: por tipo de sesión, por semana del ciclo, por rango de fechas
  - Click en sesión abre `ComparisonComponent`
- [ ] Crear `ComparisonComponent` en `features/history/comparison.component.ts`:
  - Vista lado-a-lado: sesión actual (izq) vs sesión previa del mismo tipo (der)
  - Por ejercicio: tabla de sets con diferencias destacadas
  - Iconos: ↑ verde (mejor), = amarillo (igual), ↓ rojo (peor), ✨ nuevo
  - Header con KPIs de la comparación
- [ ] Integrar sugerencia de doble progresión en `SessionLogComponent`:
  - Al abrir un ejercicio, llamar a `suggestDoubleProgression()`
  - Si alcanzó top del rango: banner "Ya llegaste al máximo de reps la semana pasada. Probá subir peso esta vez"
- [ ] Agregar alerta global en `RoutineComponent` si `detectFatigueAccumulation()` retorna true: banner naranja "Posible fatiga acumulada (2 semanas sin progresar). Considerá aplicar deload anticipado."
- [ ] Ruta `/history` y `/history/:id` (comparación)

## Criterio de aceptación

1. `/history` muestra todas las sesiones completadas en orden cronológico inverso
2. Filtros funcionan
3. Al abrir una sesión se ve la comparación con la previa del mismo tipo
4. Iconos de progresión son correctos
5. En form de sesión, si corresponde, aparece la sugerencia de doble progresión
6. Si hay fatiga acumulada detectable, banner en rutina aparece
7. KPIs de semana visibles (precondición para Sprint 7)
