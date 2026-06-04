import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import {
  SocialAuthService,
  SocialUser,
  GoogleLoginProvider,
} from '@abacritt/angularx-social-login';
import { AuthUser } from '../models/auth-user.model';

const STORAGE_KEY = 'auth.user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly socialAuth = inject(SocialAuthService);
  private readonly router = inject(Router);

  private readonly _currentUser = signal<AuthUser | null>(this.restoreFromStorage());
  readonly currentUser = this._currentUser.asReadonly();
  readonly isAuthenticated = computed(() => this._currentUser() !== null);

  constructor() {
    this.socialAuth.authState.subscribe((user: SocialUser | null) => {
      if (user) {
        this.setUser(this.mapSocialUser(user));
        void this.router.navigate(['/routine']);
      }
    });
  }

  async login(): Promise<void> {
    const user = await this.socialAuth.signIn(GoogleLoginProvider.PROVIDER_ID);
    this.setUser(this.mapSocialUser(user));
    await this.router.navigate(['/routine']);
  }

  async logout(): Promise<void> {
    try {
      await this.socialAuth.signOut(true);
    } catch {
      // ignore: user may not be logged into Google SDK state
    }
    this._currentUser.set(null);
    localStorage.removeItem(STORAGE_KEY);
    await this.router.navigate(['/login']);
  }

  private setUser(user: AuthUser): void {
    this._currentUser.set(user);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  }

  private restoreFromStorage(): AuthUser | null {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AuthUser;
    } catch {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
  }

  private mapSocialUser(user: SocialUser): AuthUser {
    return {
      id: user.id ?? '',
      email: user.email ?? '',
      name: user.name ?? 'Usuario',
      photoUrl: user.photoUrl ?? '',
    };
  }
}
