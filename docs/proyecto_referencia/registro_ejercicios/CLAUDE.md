# Registro de Ejercicios — Contexto del Proyecto

## Descripción general

App web Angular con login Google para registrar y controlar un sistema de entrenamiento Push/Pull/Legs en formato A/B. El sistema no es una rutina simple: es un framework integrado de 4 capas que debe preservarse exactamente como está definido.

## Stack
- Angular (frontend)
- Google OAuth (autenticación)
- Backend por definir (Firebase o similar recomendado por compatibilidad con Google Auth)

---

## Los 4 documentos del sistema (fuente de verdad)

### 1. Compendio de Ejercicios y Metodología
Marco operativo. Define qué ejercicios son válidos y cómo se organizan.

**Principios no negociables:**
- División Push / Pull / Legs con variantes A/B
- No repetir ejercicios entre bloques A/B del mismo grupo muscular
- Compuestos primero, aislamientos después
- RIR 1–3, tempo controlado en aislamientos (2–3s negativa)
- Sin péndulo, sin sissy squat — sustituto aprobado: prensa parcial

**Ejercicios por grupo:**

| Grupo | Ejercicios |
|-------|-----------|
| Pecho | Press banca con barra, Press inclinado mancuernas, Fondos en paralelas, Cruce de poleas, Pec deck, Push-ups (finisher) |
| Espalda | Remo barra T, Remo pecho apoyado, Remo en polea baja, Dominadas, Jalón al pecho, Pullover en polea, Face pulls |
| Hombro | Press militar mancuernas, Elevaciones laterales (dropset), Elevaciones frontales, Pájaros, Encogimientos |
| Bíceps | Curl barra Z, Curl inclinado, Curl predicador, Curl en polea, Curl martillo, 21s |
| Tríceps | Press cerrado, Copa mancuerna (overhead), Press francés, Extensión en polea, Extensión unilateral, Fondos |
| Cuádriceps | Hack squat/Smith talones elevados, Prensa inclinada, Búlgaras, Extensión de rodilla (dropset), Prensa parcial* |
| Glúteo/Isquios | Hip thrust (pausa), Abducción en máquina, Pull-through, Peso muerto rumano, Curl femoral, RDL unilateral |
| Pantorrilla | Elevación de pie, Elevación sentado, Tibialis raise |
| Core | Plancha, Side plank, Rueda abdominal, Elevaciones de piernas |

*Prensa parcial reemplaza sissy squat.

**Separación de tren inferior:**
- Día A → Cuádriceps + Pantorrilla
- Día B → Glúteo + Isquios

---

### 2. Rutina de Ejercicios Organizada
Plan táctico diario. Traduce el compendio en sesiones concretas.

**Estructura semanal (6 sesiones):**

| Sesión | Tipo | Grupos musculares |
|--------|------|-------------------|
| Pull A | Tirón A | Espalda grosor (Remo barra T, Remo pecho, Remo polea) + Bíceps |
| Push A | Empuje A | Pecho (Press banca, Fondos, Pec deck) + Tríceps + Hombro |
| Leg A  | Piernas A | Cuádriceps + Pantorrilla + Core |
| Pull B | Tirón B | Espalda amplitud (Dominadas, Jalón, Pullover) + Bíceps |
| Push B | Empuje B | Hombro (Press militar, Elevaciones) + Pecho accesorios + Tríceps |
| Leg B  | Piernas B | Glúteo + Isquios + Pantorrilla + Core |

**Regla de arquitectura:** No modificar qué ejercicios van en qué día. Solo se ajusta carga y repeticiones.

---

### 3. Ciclo de Entrenamiento (6 semanas)
Control estratégico del tiempo y la fatiga.

| Semana | Enfoque | Intensidad | Volumen | Restricciones activas |
|--------|---------|------------|---------|----------------------|
| 1 | Adaptación | RIR 2–3 | Medio | Sin fallo, sin dropsets |
| 2 | Progresión | RIR 2 | Medio-Alto | +1–2 reps por ejercicio |
| 3 | Sobrecarga | RIR 1–2 | Alto | +1 set en compuestos, +1 dropset en aislamientos |
| 4 | Pico | RIR 0–1 | Alto | Fallo solo en última serie de 2–3 ejercicios |
| 5 | Deload | RIR 3–4 | Bajo (-40 a -50%) | Sin dropsets, sin finisher, sin fallo |
| 6 | Reinicio | RIR 2 | Medio | Cargas de semana 2, técnica mejorada |

**Reglas de progresión (no negociables):**
1. Doble progresión: si llegás al máximo de reps → subís peso; si no → aumentás reps
2. Prioridad: Compuestos > Multiarticulares > Aislamientos
3. Si hay fatiga: quitás 1 ejercicio accesorio, no tocás compuestos

---

### 4. Dashboard Semanal de Entrenamiento (KPI Framework)
Sistema de control y toma de decisiones.

**KPIs ejecutivos (semáforo):**

| KPI | Objetivo | Alerta |
|-----|----------|--------|
| Cumplimiento de sesiones | 6/6 | < 5/6 |
| Progresión en compuestos | ≥ 70% | < 70% dos semanas seguidas |
| Fatiga percibida | ≤ 7/10 | > 8 = riesgo alto |
| Dolor articular | 0–2/10 | ≥ 5 = ajustar volumen inmediato |
| Energía general | ≥ 7/10 | < 6 = rendimiento comprometido |

**Ejercicios clave para tracking de progresión:**
- Pull A: Remo barra T
- Push A: Press banca
- Leg A: Hack/Smith
- Pull B: Dominadas
- Push B: Press militar
- Leg B: Hip thrust

**Métricas de progresión:**
- % ejercicios que progresan: ≥ 70%
- Progresión en compuestos: ≥ 4/6 ejercicios clave
- Progresión en aislamientos: ≥ 60%

**Control de volumen semanal por grupo (series):**

| Grupo | Mínimo | Máximo |
|-------|--------|--------|
| Pecho | 12 | 20 |
| Espalda | 14 | 22 |
| Hombro | 12 | 20 |
| Bíceps | 10 | 16 |
| Tríceps | 10 | 16 |
| Cuádriceps | 14 | 20 |
| Isquios/Glúteo | 14 | 20 |
| Pantorrilla | 12 | 20 |

**Salud articular (zonas a monitorear):** Hombros, Codos, Rodillas, Lumbar

**Decisiones automáticas:**

| Condición | Acción |
|-----------|--------|
| Todo bien | Seguir progresión |
| Fatiga alta | Reducir aislamientos |
| Dolor articular | Ajustar ejercicios |
| Estancamiento 2 semanas | Aplicar deload anticipado |

---

## Flujo operativo del sistema

```
Compendio → define qué es válido
    ↓
Rutina → define qué hacés cada día
    ↓
Ciclo → define cómo evoluciona semana a semana
    ↓
Dashboard → define si está funcionando
```

El usuario ejecuta la rutina diaria → registra datos → compara con semana anterior → ajusta según KPIs → sigue la fase del ciclo vigente.

---

## Convenciones de desarrollo

- Idioma de la UI: Español
- El sistema NO debe permitir improvisar: validar restricciones del ciclo al registrar
- Los ejercicios del compendio son la única fuente válida, no agregar ejercicios arbitrarios
- Cada sesión registrada debe poder compararse con la misma sesión de la semana anterior
