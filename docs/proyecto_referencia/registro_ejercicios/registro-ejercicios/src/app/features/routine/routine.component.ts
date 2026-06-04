import { Component, inject } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-routine',
  imports: [MatCardModule, MatChipsModule],
  template: `
    <div class="bg-gray-50 p-6">
      <div class="max-w-5xl mx-auto">
        <header class="mb-8">
          <h1 class="text-3xl font-bold text-gray-900">Mi rutina semanal</h1>
          @if (auth.currentUser(); as user) {
            <p class="text-gray-600 mt-1">
              Hola {{ user.name }}. La rutina se implementa en el Sprint 3.
            </p>
          }
        </header>

        <mat-card class="p-6 mb-6">
          <h2 class="text-lg font-semibold mb-4">Estado del proyecto</h2>
          <mat-chip-set>
            <mat-chip class="!bg-green-100">✅ Sprint 0 — Setup</mat-chip>
            <mat-chip class="!bg-green-100">✅ Sprint 1 — Auth</mat-chip>
            <mat-chip class="!bg-gray-200">⚪ Sprint 2 — Catálogo</mat-chip>
            <mat-chip class="!bg-gray-200">⚪ Sprint 3 — Rutina</mat-chip>
            <mat-chip class="!bg-gray-200">⚪ Sprint 4 — Registro</mat-chip>
            <mat-chip class="!bg-gray-200">⚪ Sprint 5 — Ciclo</mat-chip>
            <mat-chip class="!bg-gray-200">⚪ Sprint 6 — KPIs</mat-chip>
            <mat-chip class="!bg-gray-200">⚪ Sprint 7 — Dashboard</mat-chip>
          </mat-chip-set>
        </mat-card>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <mat-card class="p-4">
            <h3 class="font-semibold text-semaforo-green">Progresión</h3>
            <p class="text-sm text-gray-500 mt-1">Pendiente de datos</p>
          </mat-card>
          <mat-card class="p-4">
            <h3 class="font-semibold" style="color: #eab308">Fatiga</h3>
            <p class="text-sm text-gray-500 mt-1">Pendiente de datos</p>
          </mat-card>
          <mat-card class="p-4">
            <h3 class="font-semibold text-semaforo-red">Dolor</h3>
            <p class="text-sm text-gray-500 mt-1">Pendiente de datos</p>
          </mat-card>
        </div>
      </div>
    </div>
  `,
})
export class RoutineComponent {
  readonly auth = inject(AuthService);
}
