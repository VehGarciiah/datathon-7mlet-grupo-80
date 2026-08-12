import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, input } from '@angular/core';

@Component({
  selector: 'app-fluent-spinner',
  template: `<fluent-spinner
    appearance="primary"
    [attr.size]="size()"
    [attr.aria-label]="label()"
  ></fluent-spinner>`,
  styles: ':host { display: inline-flex; }',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FluentSpinnerComponent {
  readonly label = input('Carregando');
  readonly size = input<'small' | 'medium' | 'large'>('medium');
}
