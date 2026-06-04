# Sprints — Registro de Ejercicios

Plan de implementación por iteraciones. La Etapa 1 (Frontend + localStorage) abarca los Sprints 0–8.
La Etapa 2 (Backend real) se define al cerrar el Sprint 7.

## Estado

| # | Sprint | Requerimientos | Estado |
|---|--------|----------------|--------|
| 0 | [Setup del proyecto](sprint-00-setup.md) | — | 🟢 Completado |
| 1 | [Autenticación Google](sprint-01-auth.md) | R01 | 🟢 Completado |
| 2 | [Catálogo de ejercicios](sprint-02-catalogo.md) | R02 | ⚪ Pendiente |
| 3 | [Rutina semanal](sprint-03-rutina.md) | R03 | ⚪ Pendiente |
| 4 | [Registro de sesión](sprint-04-registro-sesion.md) | R06 | ⚪ Pendiente |
| 5 | [Ciclo + restricciones](sprint-05-ciclo.md) | R04, R05 | ⚪ Pendiente |
| 6 | [Historial + KPIs](sprint-06-historial-kpis.md) | R07, R08 | ⚪ Pendiente |
| 7 | [Dashboard + volumen](sprint-07-dashboard.md) | R09, R10 | ⚪ Pendiente |
| 8 | [Perfil + notificaciones](sprint-08-perfil.md) | R11, R12 | ⚪ Pendiente |

Leyenda: ⚪ Pendiente • 🟡 En curso • 🟢 Completado • 🔴 Bloqueado

## Stack

- Angular 19 (standalone components + signals)
- Tailwind CSS + Angular Material
- `@abacritt/angularx-social-login` para Google OAuth
- localStorage + JSON seeds en `src/assets/data/`
- Jasmine/Karma (testing)

## Regla de oro

Cada sprint debe completarse con su criterio de aceptación validado antes de pasar al siguiente. No mezclar scope entre sprints.
