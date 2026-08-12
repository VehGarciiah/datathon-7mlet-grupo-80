import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    title: 'Operação | CRM de recomendações',
    loadComponent: () =>
      import('./features/opportunities/opportunities-page.component').then(
        (module) => module.OpportunitiesPageComponent,
      ),
  },
  {
    path: 'configuracoes',
    title: 'Configurações | CRM de recomendações',
    loadComponent: () =>
      import('./features/settings/settings-page.component').then(
        (module) => module.SettingsPageComponent,
      ),
  },
  { path: '**', redirectTo: '' },
];
