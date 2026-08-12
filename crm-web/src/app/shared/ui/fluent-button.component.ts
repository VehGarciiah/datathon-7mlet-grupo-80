import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  input,
  output,
} from '@angular/core';

export type FluentButtonAppearance = 'primary' | 'outline' | 'subtle' | 'transparent';

@Component({
  selector: 'app-fluent-button',
  template: `
    <fluent-button
      [id]="controlId()"
      [attr.appearance]="appearance()"
      [attr.type]="type()"
      role="button"
      [attr.aria-label]="ariaLabel() || null"
      [attr.aria-disabled]="disabled()"
      [attr.icon-only]="iconOnly() ? '' : null"
      [disabled]="disabled()"
      (click)="onClick($event)"
    >
      <ng-content />
    </fluent-button>
  `,
  styles: `
    :host {
      display: inline-flex;
    }
    fluent-button {
      min-block-size: var(--crm-interactive-size);
    }
    :host(.stretch),
    :host(.stretch) fluent-button {
      inline-size: 100%;
    }
    :host(.icon-only) fluent-button {
      min-inline-size: var(--crm-interactive-size);
    }
  `,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FluentButtonComponent {
  readonly controlId = input('');
  readonly appearance = input<FluentButtonAppearance>('outline');
  readonly type = input<'button' | 'submit' | 'reset'>('button');
  readonly disabled = input(false);
  readonly iconOnly = input(false);
  readonly ariaLabel = input('');
  readonly pressed = output<MouseEvent>();

  protected onClick(event: MouseEvent): void {
    if (!this.disabled()) {
      this.pressed.emit(event);
    }
  }
}
