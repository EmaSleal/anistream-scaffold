import { Component, inject, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { GoogleSigninButtonModule } from '@abacritt/angularx-social-login';

@Component({
  selector: 'app-login',
  imports: [MatCardModule, MatIconModule, GoogleSigninButtonModule],
  template: `
    <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-slate-700 p-6">
      <mat-card class="max-w-md w-full p-8">
        <div class="flex flex-col items-center text-center">
          <div class="w-16 h-16 rounded-full bg-slate-900 flex items-center justify-center mb-4">
            <mat-icon class="!text-white !text-3xl !w-8 !h-8">fitness_center</mat-icon>
          </div>
          <h1 class="text-2xl font-bold text-gray-900 mb-1">Registro de Ejercicios</h1>
          <p class="text-gray-600 text-sm mb-6">
            Sistema PPL A/B con ciclo de 6 semanas
          </p>

          <asl-google-signin-button type="standard" size="large" theme="outline" text="signin_with"></asl-google-signin-button>

          <p class="text-xs text-gray-500 mt-6">
            Tus datos se guardan localmente en este navegador durante la Etapa 1.
          </p>
        </div>
      </mat-card>
    </div>
  `,
})
export class LoginComponent {
}
