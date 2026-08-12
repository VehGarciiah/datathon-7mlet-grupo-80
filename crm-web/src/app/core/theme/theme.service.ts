import { DOCUMENT, isPlatformBrowser } from '@angular/common';
import { computed, inject, Injectable, PLATFORM_ID, signal } from '@angular/core';

export type ThemeMode = 'light' | 'dark';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  private readonly platformId = inject(PLATFORM_ID);
  private readonly modeState = signal<ThemeMode>('light');

  readonly mode = this.modeState.asReadonly();
  readonly isDark = computed(() => this.modeState() === 'dark');

  async initialize(): Promise<void> {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }

    const stored = window.localStorage.getItem('crm-theme');
    const preferred: ThemeMode = window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';
    await this.apply(stored === 'light' || stored === 'dark' ? stored : preferred, false);
  }

  async toggle(): Promise<void> {
    await this.apply(this.isDark() ? 'light' : 'dark', true);
  }

  private async apply(mode: ThemeMode, persist: boolean): Promise<void> {
    const [{ webDarkTheme, webLightTheme }, { setTheme }] = await Promise.all([
      import('@fluentui/tokens'),
      import('@fluentui/web-components/theme/set-theme.js'),
    ]);
    setTheme(mode === 'dark' ? webDarkTheme : webLightTheme, this.document);
    this.document.documentElement.style.colorScheme = mode;
    this.document.documentElement.dataset['theme'] = mode;
    this.modeState.set(mode);
    if (persist) {
      window.localStorage.setItem('crm-theme', mode);
    }
  }
}
