# Sprint 5 — Ciclo de entrenamiento y restricciones

**Requerimientos:** R04, R05
**Depende de:** Sprint 4

## Objetivo
El sistema calcula automáticamente en qué semana del ciclo está el usuario y ajusta las restricciones/avisos del formulario de sesión.

## Tareas

- [ ] Definir modelos en `core/models/cycle.model.ts`:
  ```typescript
  type CyclePhase = 'adaptacion' | 'progresion' | 'sobrecarga' | 'pico' | 'deload' | 'reinicio';

  interface CyclePhaseConfig {
    week: number;                    // 1-6
    phase: CyclePhase;
    label: string;                   // "Adaptación"
    rirTarget: { min: number; max: number }; // {2, 3}
    volumeLevel: 'bajo' | 'medio' | 'medio-alto' | 'alto';
    allowDropsets: boolean;
    allowFailure: boolean;
    allowFinisher: boolean;
    extraSetsOnCompounds: number;
    description: string;
    warnings: string[];              // ["Esta semana es Deload. Sin dropsets, sin fallo."]
  }

  interface TrainingCycle {
    id: string;
    userId: string;
    startDate: string;               // ISO date (lunes de semana 1)
    endDate?: string;
    currentWeek: number;             // calculado
    status: 'active' | 'completed';
  }
  ```
- [ ] Crear `src/assets/data/cycle-phases.json` con las 6 fases (según tabla en CLAUDE.md)
- [ ] Crear `CycleService` en `core/services/cycle.service.ts`:
  - Carga config de fases
  - `activeCycle = signal<TrainingCycle | null>(null)` (leído de localStorage)
  - `currentPhaseConfig = computed(() => {...})` basado en semana actual
  - `currentWeek = computed(() => diffInWeeks(today, startDate) + 1)`
  - `startNewCycle(startDate)`
  - `completeCycle()`
  - `getCycleHistory()`
  - Persiste bajo clave `cycles.{userId}`
- [ ] Crear `CycleStatusComponent` en `features/cycle/cycle-status.component.ts`:
  - Card destacada con: "Semana X de 6 — {Fase}"
  - Badge con color según fase (verde adaptación, azul progresión, amarillo sobrecarga, rojo pico, gris deload, verde claro reinicio)
  - RIR objetivo
  - Lista de warnings/recomendaciones de la fase
- [ ] Crear `CycleManagerComponent` en `features/cycle/cycle-manager.component.ts`:
  - Si no hay ciclo activo: CTA "Iniciar ciclo" con date picker
  - Si hay ciclo activo: mostrar status + botón "Cerrar ciclo"
  - Si se acaba de completar semana 6: CTA "Iniciar nuevo ciclo"
  - Historial colapsable de ciclos anteriores
- [ ] Integrar `CycleStatusComponent` en `RoutineComponent` (top)
- [ ] Integrar restricciones en `SessionLogComponent`:
  - RIR objetivo dinámico leído de `cycleService.currentPhaseConfig()`
  - Banner de warnings (Material alert/snackbar) si existen
  - Al completar sesión: stamp `cycleWeek` en el SessionLog
  - Si user marca RIR < phase.rirTarget.min → dialog de confirmación ("Esta semana el RIR objetivo es X–Y. ¿Seguro querés registrar RIR Z?")
- [ ] Ruta `/cycle` con `CycleManagerComponent`
- [ ] Link "Ciclo" en navbar

## Criterio de aceptación

1. Sin ciclo iniciado, `/cycle` permite crearlo con fecha de inicio
2. Con ciclo activo, se muestra semana correcta según fecha actual
3. La vista de rutina muestra "Semana N — Fase"
4. El form de sesión muestra RIR objetivo según la fase y avisos cuando corresponde (especialmente Deload)
5. Intentar registrar RIR fuera de rango pide confirmación
6. Al completar ciclo, se archiva y se puede iniciar otro
7. Semana 1 bloquea fallo; Semana 5 bloquea dropsets y finisher
