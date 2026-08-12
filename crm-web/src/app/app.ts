import { afterNextRender, ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { CrmApiService } from './core/api/crm-api.service';
import { ThemeService } from './core/theme/theme.service';
import { FluentButtonComponent } from './shared/ui/fluent-button.component';
import { FluentIconComponent } from './shared/ui/fluent-icon.component';

@Component({
  selector: 'app-root',
  imports: [RouterLink, RouterLinkActive, RouterOutlet, FluentButtonComponent, FluentIconComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  private readonly api = inject(CrmApiService);
  protected readonly theme = inject(ThemeService);
  protected readonly apiState = signal<'connecting' | 'connected' | 'unavailable'>('connecting');

  constructor() {
    afterNextRender(() => {
      void this.theme.initialize();
      this.api.getHealth().subscribe({
        next: (health) => this.apiState.set(health.status === 'UP' ? 'connected' : 'unavailable'),
        error: () => this.apiState.set('unavailable'),
      });
    });
  }
}
