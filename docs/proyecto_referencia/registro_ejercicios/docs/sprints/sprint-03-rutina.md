# Sprint 3 — Rutina semanal

**Requerimiento:** R03
**Depende de:** Sprint 2

## Objetivo
Las 6 sesiones (Pull A/B, Push A/B, Leg A/B) están definidas con sus ejercicios y el usuario puede configurar qué día de la semana entrena cada una.

## Tareas

- [ ] Definir modelos en `core/models/session-template.model.ts`:
  ```typescript
  type SessionType = 'pull-a' | 'push-a' | 'leg-a' | 'pull-b' | 'push-b' | 'leg-b';

  interface SessionExercise {
    exerciseId: string;
    order: number;
    targetSets: number;      // 3-4
    targetReps: string;      // "8-12"
    technique?: 'dropset' | 'pause' | 'partial';
    notes?: string;
  }

  interface SessionTemplate {
    id: SessionType;
    name: string;            // "Pull A"
    muscleGroups: MuscleGroup[];
    exercises: SessionExercise[];
  }
  ```
- [ ] Crear `src/assets/data/routine.json` con las 6 sesiones:
  - **Pull A (Grosor):** Remo barra T → Remo pecho apoyado → Remo polea baja → Curl barra Z → Curl predicador → Face pulls
  - **Push A (Pecho dominante):** Press banca → Press inclinado mancuernas → Fondos paralelas → Pec deck → Press cerrado → Extensión polea
  - **Leg A (Cuádriceps + Pantorrilla):** Hack squat/Smith → Prensa inclinada → Búlgaras → Extensión rodilla → Prensa parcial → Elevación de pie → Elevación sentado → Plancha
  - **Pull B (Amplitud):** Dominadas → Jalón al pecho → Pullover polea → Curl inclinado → Curl martillo → 21s → Face pulls
  - **Push B (Hombro dominante):** Press militar mancuernas → Elevaciones laterales → Elevaciones frontales → Pájaros → Encogimientos → Cruce poleas → Press francés → Extensión unilateral
  - **Leg B (Glúteo + Isquios):** Hip thrust → Peso muerto rumano → Pull-through → Abducción máquina → Curl femoral → RDL unilateral → Elevación de pie → Rueda abdominal
- [ ] Validar en test unitario: ningún ejercicio se repite entre Pull A/Pull B, Push A/Push B, Leg A/Leg B
- [ ] Crear `RoutineService` en `core/services/routine.service.ts`:
  - Carga `routine.json`
  - `getSession(type)`, `getAllSessions()`
- [ ] Crear `UserScheduleService` en `core/services/user-schedule.service.ts`:
  - Modelo `WeeklySchedule = Record<DayOfWeek, SessionType | null>`
  - Guarda en localStorage bajo clave `schedule.{userId}`
  - Default: L=pull-a, M=push-a, X=leg-a, J=pull-b, V=push-b, S=leg-b, D=descanso
- [ ] Crear `RoutineComponent` en `features/routine/routine.component.ts`:
  - Vista semanal con 7 columnas (L–D)
  - Cada columna muestra la sesión asignada o "Descanso"
  - Hoy resaltado
  - Click en una sesión navega a `/session/:type` (placeholder por ahora)
- [ ] Crear `ScheduleConfigComponent`:
  - Editor: dropdown por día para elegir sesión
  - Guarda cambios en `UserScheduleService`
- [ ] Agregar rutas `/routine` y `/routine/config`
- [ ] Link "Mi rutina" en navbar como página default post-login

## Criterio de aceptación

1. `/routine` muestra la semana con las 6 sesiones distribuidas
2. Al abrir una sesión se ven sus ejercicios con orden, sets y reps objetivo
3. Config de días permite cambiar la distribución y persiste al recargar
4. Test unitario valida no-repetición A/B pasa
5. Día actual resaltado en la vista semanal
