# Sprint 1 — Autenticación con Google

**Requerimiento:** R01
**Depende de:** Sprint 0

## Objetivo
Usuario puede iniciar sesión con Google, la sesión persiste al recargar, y las rutas protegidas redirigen a login si no hay usuario.

## Tareas

- [ ] Obtener Google OAuth Client ID desde Google Cloud Console
  - Crear proyecto en GCP
  - Habilitar Google Identity API
  - Crear credenciales OAuth 2.0 tipo "Web application"
  - Origen autorizado: `http://localhost:4200`
  - Guardar Client ID en `src/environments/environment.ts` (crear si no existe)
- [ ] Configurar `SocialAuthServiceConfig` en `app.config.ts` con `GoogleLoginProvider`
- [ ] Crear modelo `AuthUser` en `core/models/auth-user.model.ts` (id, email, name, photoUrl)
- [ ] Crear `AuthService` en `core/services/auth.service.ts`:
  - `currentUser = signal<AuthUser | null>(null)`
  - `isAuthenticated = computed(() => !!currentUser())`
  - `login()`: llama a `GoogleLoginProvider`, mapea respuesta a `AuthUser`, guarda en localStorage
  - `logout()`: limpia signal + localStorage + llama `socialAuthService.signOut()`
  - `init()`: intenta restaurar sesión de localStorage al arrancar
- [ ] Crear `authGuard` (CanActivateFn) que redirige a `/login` si no autenticado
- [ ] Crear `LoginComponent` en `features/auth/login.component.ts`:
  - Pantalla centrada con logo/título
  - Botón "Iniciar con Google" estilizado
  - Al loguear: redirect a `/routine`
- [ ] Crear `NavbarComponent` en `shared/components/navbar.component.ts`:
  - Avatar + nombre del usuario
  - Botón logout
- [ ] Actualizar `app.routes.ts`:
  - `/login` → `LoginComponent` (pública)
  - Resto → protegido por `authGuard`
- [ ] Actualizar `AppComponent`: si autenticado muestra navbar + router-outlet; si no, solo router-outlet

## Criterio de aceptación

1. Al entrar a la app sin sesión, redirige a `/login`
2. Click en "Iniciar con Google" abre popup de Google
3. Tras login exitoso, redirige a `/routine` (placeholder por ahora)
4. Navbar muestra foto y nombre del usuario
5. Recargar la página preserva la sesión (no vuelve a pedir login)
6. Click en logout limpia sesión y redirige a `/login`
7. localStorage contiene clave `auth.user` con el JSON del usuario mientras haya sesión
