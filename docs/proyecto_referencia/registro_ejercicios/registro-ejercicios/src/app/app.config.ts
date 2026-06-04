import { ApplicationConfig, importProvidersFrom, provideZoneChangeDetection } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import {
  GoogleLoginProvider,
  SOCIAL_AUTH_CONFIG,
  SocialAuthServiceConfig,
  SocialLoginModule,
} from '@abacritt/angularx-social-login';

import { routes } from './app.routes';
import { environment } from '../environments/environment';

const socialAuthConfig: SocialAuthServiceConfig = {
  autoLogin: false,
  providers: [
    {
      id: GoogleLoginProvider.PROVIDER_ID,
      provider: new GoogleLoginProvider(environment.googleClientId, {
        oneTapEnabled: false,
      }),
    },
  ],
  onError: (err) => console.error('[SocialAuth]', err),
};

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(),
    provideAnimationsAsync(),
    importProvidersFrom(SocialLoginModule),
    { provide: SOCIAL_AUTH_CONFIG, useValue: socialAuthConfig },
  ],
};
