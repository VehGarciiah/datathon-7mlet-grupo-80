import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, input } from '@angular/core';

export type FluentBadgeColor =
  'subtle' | 'brand' | 'danger' | 'important' | 'informative' | 'severe' | 'success' | 'warning';

@Component({
  selector: 'app-fluent-badge',
  template: `
    <fluent-badge
      [attr.appearance]="appearance()"
      [attr.color]="color()"
      shape="rounded"
      size="medium"
    >
      <ng-content />
    </fluent-badge>
  `,
  styles: ':host { display: inline-flex; }',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FluentBadgeComponent {
  readonly appearance = input<'outline' | 'filled' | 'ghost' | 'tint'>('tint');
  readonly color = input<FluentBadgeColor>('subtle');
}
