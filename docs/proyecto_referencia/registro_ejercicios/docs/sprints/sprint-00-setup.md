# Sprint 0 — Setup del proyecto

## Objetivo
Proyecto Angular 19 inicializado, estilos configurados, estructura de carpetas creada y servidor de desarrollo levantando.

## Scope
- Scaffolding de Angular
- Tailwind CSS + Angular Material
- `@abacritt/angularx-social-login` instalado (config se hace en Sprint 1)
- Estructura `core/`, `features/`, `shared/`
- Routing base con lazy loading

## Tareas

- [ ] Verificar Node ≥ 20 y npm disponibles
- [ ] `ng new registro-ejercicios --style=scss --ssr=false --skip-git --defaults`
- [ ] Instalar Tailwind CSS v3 y configurar `tailwind.config.js` con paths a `src/**/*.{html,ts}`
- [ ] Agregar directivas `@tailwind` en `styles.scss`
- [ ] `ng add @angular/material` (tema a elegir: Azure/Blue, typography + animations)
- [ ] `npm install @abacritt/angularx-social-login`
- [ ] Crear carpetas: `src/app/core/{models,services,guards,tokens}`, `src/app/features/`, `src/app/shared/{components,pipes}`
- [ ] Configurar `app.routes.ts` con ruta vacía → redirige a `/login` (por ahora placeholder)
- [ ] `AppComponent`: shell con `<router-outlet />`
- [ ] Verificar `ng serve` en `http://localhost:4200`

## Criterio de aceptación

1. `ng serve` levanta sin errores
2. Se puede aplicar una clase de Tailwind (ej. `text-blue-500`) y se ve reflejada
3. Se puede usar un componente de Angular Material (ej. `<mat-button>`) y se ve estilizado
4. Estructura de carpetas creada
5. No hay errores en consola del navegador

## Notas

- Si el proyecto Angular vive en subfolder `registro-ejercicios/`, todos los paths posteriores serán relativos a ese subfolder
- No configurar OAuth aún — eso es Sprint 1
