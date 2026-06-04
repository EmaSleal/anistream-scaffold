# Requerimientos — App de Registro de Ejercicios

## Visión general

App web Angular que digitaliza el sistema de entrenamiento Push/Pull/Legs A/B. Permite registrar sesiones, controlar el ciclo de 6 semanas, aplicar restricciones automáticas por fase y visualizar KPIs de progresión.

---

## Mapa de dependencias (ruta crítica)

```
R01 (Auth)
  └── R02 (Catálogo ejercicios)
        └── R03 (Estructura rutina)
              ├── R04 (Ciclo de entrenamiento)
              │     └── R05 (Restricciones por fase)
              └── R06 (Registro de sesión)
                    ├── R07 (Historial y comparación)
                    │     └── R08 (KPIs de progresión)
                    │           └── R09 (Dashboard semanal)
                    └── R10 (Volumen por grupo muscular)
                          └── R09
```

**Ruta crítica:** R01 → R02 → R03 → R06 → R07 → R08 → R09

---

## Requerimientos por capa

---

### CAPA 1 — Fundación (sin esto nada funciona)

#### R01 — Autenticación con Google
**Depende de:** nada
**Prioridad:** CRÍTICA

- Login con Google OAuth 2.0
- Sesión persistente (recordar usuario)
- Logout
- Cada usuario tiene sus propios datos aislados
- Pantalla de bienvenida si no hay sesión

---

#### R02 — Catálogo de ejercicios
**Depende de:** R01
**Prioridad:** CRÍTICA

- Catálogo precargado con todos los ejercicios del Compendio
- Cada ejercicio tiene: nombre, grupo muscular, foco (fuerza/hipertrofia/aislamiento/metabólico), bloque permitido (A/B/ambos), observaciones
- Ejercicios no editables por el usuario (son la fuente de verdad)
- Sustituciones aprobadas registradas: Prensa parcial reemplaza Sissy squat
- Restricciones registradas: Sin péndulo, sin sissy squat

---

### CAPA 2 — Estructura (define qué se hace y cuándo)

#### R03 — Estructura de la rutina semanal
**Depende de:** R02
**Prioridad:** CRÍTICA

- 6 sesiones definidas: Pull A, Push A, Leg A, Pull B, Push B, Leg B
- Cada sesión tiene sus ejercicios asignados según el Compendio (no editables)
- Visualización de la semana: qué sesión corresponde cada día
- El usuario puede marcar qué días de la semana entrena (ej: lun/mié/vie/sáb para las 6 sesiones distribuidas)
- Validar: no repetir ejercicios entre A y B del mismo grupo muscular

---

#### R04 — Ciclo de entrenamiento (6 semanas)
**Depende de:** R03
**Prioridad:** ALTA

- Crear un ciclo con fecha de inicio
- Seguimiento automático de en qué semana del ciclo está el usuario (1 al 6)
- Mostrar la fase actual: Adaptación / Progresión / Sobrecarga / Pico / Deload / Reinicio
- Mostrar parámetros de la fase: RIR objetivo, volumen esperado, técnicas habilitadas
- Al completar semana 6 → opción de iniciar nuevo ciclo
- Historial de ciclos anteriores

---

#### R05 — Restricciones automáticas por fase del ciclo
**Depende de:** R04
**Prioridad:** ALTA

- Semana 1: bloquear series al fallo, bloquear dropsets, mostrar aviso de enfoque en técnica
- Semana 2: habilitar progresión, mostrar KPI de +1–2 reps objetivo
- Semana 3: habilitar 1 set extra en compuestos, habilitar dropsets en aislamientos
- Semana 4: habilitar fallo solo en última serie de máximo 3 ejercicios
- Semana 5 (Deload): bloquear dropsets, finisher y series al fallo; reducir volumen sugerido -40% a -50%
- Semana 6: sugerir cargas de semana 2 como referencia de baseline
- Las restricciones se muestran como avisos en el formulario de registro, no bloquean el guardado (el usuario puede sobrescribir con confirmación)

---

### CAPA 3 — Registro (el núcleo de uso diario)

#### R06 — Registro de sesión
**Depende de:** R03, R04
**Prioridad:** CRÍTICA

- Seleccionar sesión del día (Pull A, Push A, etc.)
- Para cada ejercicio de la sesión registrar: peso (kg/lb), repeticiones, series completadas, RIR percibido (0–4), notas opcionales
- Indicador de RIR objetivo según fase del ciclo actual
- Registrar indicadores de bienestar post-sesión: fatiga percibida (1–10), dolor articular por zona (hombros/codos/rodillas/lumbar, 0–10), energía (1–10), calidad de sueño (1–10), estrés (1–10)
- Timestamp automático de la sesión
- Sesión guardable como borrador y completable después
- Marcar sesión como completada

---

### CAPA 4 — Análisis (convierte datos en decisiones)

#### R07 — Historial y comparación entre semanas
**Depende de:** R06
**Prioridad:** ALTA

- Ver el historial de todas las sesiones registradas
- Para cada ejercicio: comparar peso/reps con la misma sesión de la semana anterior
- Indicador visual: progresó / igual / bajó
- Aplicar regla de doble progresión: si llegó al máximo de reps → sugerir subir peso; si no → sugerir subir reps

---

#### R08 — KPIs de progresión
**Depende de:** R07
**Prioridad:** ALTA

- % de ejercicios que progresaron en la semana (objetivo ≥ 70%)
- Progresión en ejercicios compuestos clave: ≥ 4/6 (Pull A: Remo barra T, Push A: Press banca, Leg A: Hack/Smith, Pull B: Dominadas, Push B: Press militar, Leg B: Hip thrust)
- Progresión en aislamientos: ≥ 60%
- Alerta si progresión cae 2 semanas seguidas → fatiga acumulada
- Semáforo por KPI: verde / amarillo / rojo

---

#### R09 — Dashboard semanal
**Depende de:** R08, R10
**Prioridad:** ALTA

- Vista resumen de la semana con todos los KPIs en un semáforo
- KPIs mostrados: cumplimiento de sesiones (6/6), progresión compuestos, fatiga percibida, dolor articular, energía general
- Decisión estratégica sugerida al cerrar la semana según condición: seguir progresión / reducir aislamientos / ajustar ejercicios / aplicar deload anticipado
- Resumen semanal con preguntas de cierre: ¿Progresé en compuestos? ¿Me siento recuperado? ¿Hay dolor acumulado?
- Vista histórica de dashboards por semana

---

#### R10 — Control de volumen por grupo muscular
**Depende de:** R06
**Prioridad:** MEDIA

- Calcular series semanales por grupo muscular a partir de las sesiones registradas
- Comparar contra rangos objetivo del Compendio (ej: Pecho 12–20, Espalda 14–22)
- Indicador visual si está por debajo, dentro o fuera del rango
- Alertar si algún grupo está fuera de rango

---

### CAPA 5 — Extras (mejoran la experiencia, no son bloqueantes)

#### R11 — Perfil de usuario
**Depende de:** R01
**Prioridad:** BAJA

- Nombre y foto desde Google
- Unidad de peso preferida (kg / lb)
- Fecha de inicio del sistema

---

#### R12 — Notificaciones / recordatorios
**Depende de:** R03
**Prioridad:** BAJA

- Recordatorio del día de entrenamiento según la distribución semanal configurada
- Aviso cuando se detecta fatiga acumulada (2 semanas sin progresión)
- Aviso de deload obligatorio (semana 5)

---

## Orden de implementación recomendado

| Fase | Requerimientos | Resultado entregable |
|------|---------------|---------------------|
| 1 | R01 | Usuario puede loguearse con Google |
| 2 | R02 | Catálogo de ejercicios disponible |
| 3 | R03 | Rutina semanal visible con sus sesiones |
| 4 | R06 | Usuario puede registrar una sesión completa |
| 5 | R04 + R05 | Sistema sabe en qué semana del ciclo está y aplica restricciones |
| 6 | R07 + R08 | Comparación semanal y KPIs de progresión |
| 7 | R10 + R09 | Dashboard con semáforo y control de volumen |
| 8 | R11 + R12 | Perfil y notificaciones |

---

## Restricciones de diseño (no negociables)

1. Los ejercicios del catálogo no son modificables por el usuario
2. La arquitectura de sesiones (qué ejercicios van en qué día) no cambia
3. El ciclo de 6 semanas debe respetarse; el sistema debe comunicar activamente la fase actual
4. Todo el sistema opera en español
5. Los datos son por usuario (Google UID como identificador)
