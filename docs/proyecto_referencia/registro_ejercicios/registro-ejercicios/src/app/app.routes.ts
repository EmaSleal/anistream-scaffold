import { Routes } from '@angular/router';
import { authGuard, publicGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'routine' },
  {
    path: 'login',
    canActivate: [publicGuard],
    loadComponent: () =>
      import('./features/auth/login.component').then((m) => m.LoginComponent),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./shared/components/app-layout.component').then((m) => m.AppLayoutComponent),
    children: [
      {
        path: 'routine',
        loadComponent: () =>
          import('./features/routine/routine.component').then((m) => m.RoutineComponent),
      },
      {
        path: 'catalog',
        loadComponent: () =>
          import('./features/catalog/catalog.component').then((m) => m.CatalogComponent),
      },
    ],
  },
  { path: '**', redirectTo: 'routine' },
];
