# Sprint 4 — Registro de sesión

**Requerimiento:** R06
**Depende de:** Sprint 3

## Objetivo
Core del sistema. El usuario puede registrar una sesión completa: sets con peso/reps/RIR por ejercicio, notas, e indicadores de bienestar post-sesión.

## Tareas

- [ ] Definir modelos en `core/models/session-log.model.ts`:
  ```typescript
  interface SetLog {
    weight: number;
    reps: number;
    rir: number;           // 0-5
  }

  interface ExerciseLog {
    exerciseId: string;
    sets: SetLog[];
    notes?: string;
  }

  interface WellnessLog {
    fatigue: number;        // 1-10
    energy: number;         // 1-10
    sleep: number;          // 1-10
    stress: number;         // 1-10
    pain: {
      shoulders: number;    // 0-10
      elbows: number;
      knees: number;
      lumbar: number;
    };
  }

  type SessionStatus = 'draft' | 'completed';

  interface SessionLog {
    id: string;             // UUID
    userId: string;
    sessionType: SessionType;
    date: string;           // ISO date
    status: SessionStatus;
    exercises: ExerciseLog[];
    wellness?: WellnessLog;
    cycleWeek?: number;     // se llena en Sprint 5
  }
  ```
- [ ] Crear `LocalStorageAdapter<T>` en `core/services/storage/local-storage.adapter.ts` (IStorageAdapter)
- [ ] Crear `SessionLogService` en `core/services/session-log.service.ts`:
  - `createDraft(sessionType)` → nuevo SessionLog status=draft con exercises vacíos mapeados desde template
  - `updateDraft(id, patch)`
  - `complete(id)` → status=completed
  - `getById(id)`, `getAll()`, `getByDate(date)`, `getDraft(sessionType)` (devuelve draft del día si existe)
  - Persiste bajo clave `sessions.{userId}` como array
- [ ] Crear `SessionLogComponent` en `features/session/session-log.component.ts`:
  - Recibe `:type` (sessionType) y `:id?` (si existe draft)
  - Header: nombre sesión, fecha, RIR objetivo (por ahora hardcoded a 2)
  - Por cada ejercicio:
    - Nombre + técnica sugerida + reps objetivo
    - Tabla de sets editable (peso / reps / RIR)
    - Botón "+ Agregar set"
    - Campo de notas colapsable
  - Sección final: `WellnessFormComponent` con sliders de Material
  - Botones: "Guardar borrador" (sticky bottom), "Completar sesión"
  - Autoguardado del draft cada 30s
- [ ] Crear `WellnessFormComponent` (reutilizable en Sprint 7)
- [ ] Ruta `/session/:type` → abre draft del día o crea uno nuevo
- [ ] Ruta `/session/:type/:id` → abre específico
- [ ] En `RoutineComponent`: click en sesión del día hoy → `/session/:type`

## Criterio de aceptación

1. User puede abrir la sesión de hoy y llenar todos los ejercicios con sets
2. Puede agregar y quitar sets
3. Puede escribir notas por ejercicio
4. Sliders de wellness funcionan
5. "Guardar borrador" persiste y al volver se restaura el estado
6. "Completar sesión" marca status=completed y bloquea edición
7. Recargar la página durante una sesión no pierde datos
8. En localStorage hay entrada `sessions.{userId}` con el array actualizado
