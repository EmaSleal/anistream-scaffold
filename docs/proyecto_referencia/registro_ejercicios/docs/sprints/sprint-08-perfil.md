# Sprint 8 — Perfil y notificaciones

**Requerimientos:** R11, R12
**Depende de:** Sprint 7

## Objetivo
Acabados finales: pantalla de perfil con preferencias y notificaciones/avisos al usuario.

## Tareas

- [ ] Extender modelo `UserPreferences` en `core/models/user-preferences.model.ts`:
  ```typescript
  interface UserPreferences {
    userId: string;
    weightUnit: 'kg' | 'lb';
    systemStartDate: string; // ISO
    notificationsEnabled: boolean;
  }
  ```
- [ ] Crear `PreferencesService` en `core/services/preferences.service.ts`:
  - Persiste bajo clave `preferences.{userId}`
  - Signal reactiva para `weightUnit`
- [ ] Crear `ProfileComponent` en `features/profile/profile.component.ts`:
  - Avatar + nombre + email (readonly, desde Google)
  - Selector unidad de peso (kg/lb) con Material radio group
  - Fecha de inicio del sistema (readonly)
  - Toggle "Habilitar notificaciones del navegador"
- [ ] Integrar conversión de unidad en displays:
  - Agregar pipe `weightDisplay` que convierta según preferencia
  - `getWeight(kg: number): string` (solo display, no muta datos guardados)
  - Aplicar en `SessionLogComponent`, `ComparisonComponent`, `DashboardComponent`
- [ ] **Notificaciones (opcional):**
  - `NotificationService` que usa Web Notifications API
  - Al iniciar sesión del día: `Notification.requestPermission()`
  - Schedule: si es el día y hora de entrenamiento configurada y user no abrió la sesión → notificar
- [ ] **Banners in-app:**
  - Component `AppBannerComponent` en `shared/components/`
  - Reglas:
    - Si es semana 5 y no se han reducido volúmenes → "Deload obligatorio"
    - Si `detectFatigueAccumulation()` → "Posible fatiga acumulada"
    - Si es semana 4 (Pico) → "Semana de Pico: máxima intensidad controlada"
  - Se muestran en el top del layout con color según severidad
- [ ] Ruta `/profile`
- [ ] Link "Perfil" en navbar (menú usuario)

## Criterio de aceptación

1. `/profile` muestra info de Google y permite cambiar unidad de peso
2. Cambiar de kg a lb actualiza todos los displays sin tocar datos guardados
3. Toggle de notificaciones pide permiso al navegador
4. Banners aparecen según las reglas
5. Todas las preferencias persisten al recargar
