# Sprint 2 — Catálogo de ejercicios

**Requerimiento:** R02
**Depende de:** Sprint 1
**Duración sugerida:** 4-5 días hábiles

## Objetivo
Todos los ejercicios del Compendio accesibles como catálogo consultable y filtrable.

## Alcance

### Incluye

- Catálogo semilla con ejercicios oficiales del Compendio (fuente de verdad)
- Modelado de tipos para ejercicios y metadatos de filtrado
- Servicio de lectura/consulta (solo lectura)
- Pantalla `/catalog` protegida por autenticación
- Filtros por grupo muscular, foco y texto
- Indicador visual para sustituciones aprobadas

### No incluye

- Edición o alta manual de ejercicios por usuario
- Persistencia remota (backend)
- Lógica de asignación de ejercicios a sesiones (Sprint 3)

## Historias de usuario

1. Como usuario autenticado, quiero abrir `/catalog` para consultar ejercicios válidos del sistema.
2. Como usuario, quiero filtrar por grupo muscular y foco para encontrar ejercicios más rápido.
3. Como usuario, quiero buscar por nombre en tiempo real para localizar ejercicios específicos.
4. Como usuario, quiero ver qué ejercicios son sustituciones aprobadas para respetar el compendio.

## Backlog técnico

### 1) Dominio y contratos

- [ ] Definir modelo `Exercise` en `core/models/exercise.model.ts`:
  ```typescript
  interface Exercise {
    id: string;             // slug único, ej: "press-banca-barra"
    name: string;           // "Press banca con barra"
    muscleGroup: MuscleGroup; // 'pecho' | 'espalda' | 'hombro' | ...
    focus: ExerciseFocus;   // 'fuerza' | 'hipertrofia' | 'aislamiento' | 'metabolico' | 'compuesto' | 'estabilidad'
    block: 'A' | 'B' | 'both'; // Según Compendio
    equipment?: string[];   // 'barra', 'mancuernas', 'polea', 'maquina'
    notes?: string;
    isSubstitution?: boolean; // true para prensa parcial
    substitutes?: string;     // id del ejercicio que reemplaza
  }
  ```
- [ ] Definir enums/types `MuscleGroup`, `ExerciseFocus`

### 2) Fuente de datos

- [ ] Crear `src/assets/data/exercises.json` con los ejercicios del Compendio:
  - Pecho: Press banca barra, Press inclinado mancuernas, Fondos en paralelas, Cruce de poleas, Pec deck, Push-ups (finisher)
  - Espalda: Remo barra T, Remo pecho apoyado, Remo polea baja, Dominadas, Jalón al pecho, Pullover polea, Face pulls
  - Hombro: Press militar mancuernas, Elevaciones laterales, Elevaciones frontales, Pájaros, Encogimientos
  - Bíceps: Curl barra Z, Curl inclinado, Curl predicador, Curl polea, Curl martillo, 21s
  - Tríceps: Press cerrado, Copa mancuerna overhead, Press francés, Extensión polea, Extensión unilateral, Fondos
  - Cuádriceps: Hack squat/Smith talones elevados, Prensa inclinada, Búlgaras, Extensión rodilla, Prensa parcial (sustituto sissy squat)
  - Glúteo/Isquios: Hip thrust, Abducción máquina, Pull-through, Peso muerto rumano, Curl femoral, RDL unilateral
  - Pantorrilla: Elevación de pie, Elevación sentado, Tibialis raise
  - Core: Plancha, Side plank, Rueda abdominal, Elevaciones de piernas

### 3) Capa de acceso

- [ ] Crear `ExerciseCatalogService` en `core/services/exercise-catalog.service.ts`:
  - Carga `exercises.json` vía `HttpClient` al inicializar
  - `exercises = signal<Exercise[]>([])`
  - `getByMuscleGroup(group)`, `getById(id)`, `search(query)`
- [ ] Registrar `HttpClient` en `app.config.ts` con `provideHttpClient()`

### 4) UI de catálogo

- [ ] Crear `CatalogComponent` en `features/catalog/catalog.component.ts`:
  - Filtros: grupo muscular (chips), foco (select), buscador por nombre
  - Grid de cards: nombre, grupo, foco, notas
  - Cards con Tailwind, filtros con Angular Material
- [ ] Agregar ruta `/catalog` protegida en `app.routes.ts`
- [ ] Agregar link "Catálogo" en navbar

### 5) Calidad mínima

- [ ] Manejar estado vacío (sin resultados)
- [ ] Manejar error de carga de JSON con mensaje amigable
- [ ] Evitar errores en consola durante navegación y filtrado

## Plan de ejecución sugerido

### Día 1

- Modelos y tipos (`Exercise`, `MuscleGroup`, `ExerciseFocus`)
- Seed inicial de `exercises.json`

### Día 2

- `ExerciseCatalogService` con carga y consultas base
- Validación manual de integridad del JSON

### Día 3

- `CatalogComponent` con render de lista completa
- Ruta protegida `/catalog`

### Día 4

- Filtros (chips, select, búsqueda en tiempo real)
- Indicador de sustitución para Prensa parcial

### Día 5 (buffer)

- Ajustes de UX
- Limpieza de errores
- Cierre de criterio de aceptación

## Criterio de aceptación

1. `/catalog` muestra los 40+ ejercicios agrupados
2. Filtro por grupo muscular funciona (click en chip filtra)
3. Buscador por nombre filtra en tiempo real
4. Cada ejercicio muestra grupo, foco y notas si existen
5. Prensa parcial aparece con indicador de sustitución
6. No hay errores en consola

## Definición de terminado (DoD)

- Se cumple todo el criterio de aceptación
- El catálogo es solo lectura (sin UI de edición)
- Build de Angular pasa sin errores
- Sin errores de runtime al abrir `/catalog` y aplicar filtros
- Documento de sprint actualizado con checklist completo

## Checklist de QA manual

- [ ] Usuario no autenticado no entra a `/catalog`
- [ ] Usuario autenticado sí entra a `/catalog`
- [ ] Se visualiza listado completo sin filtros
- [ ] Filtro por grupo devuelve resultados correctos
- [ ] Filtro por foco devuelve resultados correctos
- [ ] Búsqueda por texto es sensible a coincidencia parcial
- [ ] Combinación de filtros funciona sin romper UI
- [ ] Prensa parcial se identifica como sustitución de sissy squat
