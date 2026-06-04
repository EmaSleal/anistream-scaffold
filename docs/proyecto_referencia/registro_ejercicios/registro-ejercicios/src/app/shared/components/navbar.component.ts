import { Component, inject } from '@angular/core';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatMenuModule } from '@angular/material/menu';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-navbar',
  imports: [
    MatToolbarModule,
    MatMenuModule,
    MatButtonModule,
    MatIconModule,
    RouterLink,
    RouterLinkActive,
  ],
  template: `
    <mat-toolbar color="primary" class="!bg-slate-900">
      <a routerLink="/routine" class="font-bold text-lg mr-6 no-underline text-white">
        Registro de Ejercicios
      </a>

      <nav class="flex gap-1">
        <a
          mat-button
          routerLink="/routine"
          routerLinkActive="!bg-white/10"
          class="!text-white"
        >Rutina</a>
        <a
          mat-button
          routerLink="/catalog"
          routerLinkActive="!bg-white/10"
          class="!text-white"
        >Catálogo</a>
      </nav>

      <span class="flex-1"></span>

      @if (auth.currentUser(); as user) {
        <button mat-button [matMenuTriggerFor]="userMenu" class="!text-white">
          <img
            [src]="user.photoUrl"
            [alt]="user.name"
            class="w-8 h-8 rounded-full inline-block mr-2 align-middle"
            referrerpolicy="no-referrer"
          />
          <span>{{ user.name }}</span>
        </button>
        <mat-menu #userMenu="matMenu">
          <div class="px-4 py-2 text-sm text-gray-600">{{ user.email }}</div>
          <button mat-menu-item (click)="logout()">
            <mat-icon>logout</mat-icon>
            <span>Cerrar sesión</span>
          </button>
        </mat-menu>
      }
    </mat-toolbar>
  `,
})
export class NavbarComponent {
  readonly auth = inject(AuthService);

  async logout(): Promise<void> {
    await this.auth.logout();
  }
}
