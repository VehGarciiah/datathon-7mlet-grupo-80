import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  input,
  output,
} from '@angular/core';
import { FluentHelpComponent } from './fluent-help.component';

@Component({
  selector: 'app-fluent-text-input',
  imports: [FluentHelpComponent],
  template: `
    @if (label()) {
      <span class="field-label">
        <label [for]="controlId()">{{ label() }}</label>
        @if (helpText()) {
          <app-fluent-help [controlId]="controlId()" [label]="label()" [text]="helpText()" />
        }
      </span>
    }
    @if (description()) {
      <span class="field-description" [id]="descriptionId()">{{ description() }}</span>
    }
    <fluent-text-input
      [id]="controlId()"
      appearance="outline"
      control-size="large"
      [attr.type]="type()"
      [value]="value()"
      [placeholder]="placeholder()"
      [attr.aria-label]="ariaLabel()"
      [attr.aria-describedby]="description() ? descriptionId() : null"
      [disabled]="disabled()"
      (input)="onInput($event)"
    >
      <ng-content />
    </fluent-text-input>
  `,
  styles: `
    :host,
    fluent-text-input {
      display: block;
      inline-size: 100%;
    }
    fluent-text-input {
      min-block-size: var(--crm-interactive-size);
    }
    label {
      color: var(--colorNeutralForeground1);
      font-weight: var(--fontWeightSemibold);
    }
    .field-label {
      display: flex;
      min-block-size: var(--crm-interactive-size);
      align-items: center;
      justify-content: space-between;
      gap: var(--spacingHorizontalS);
    }
    .field-description {
      display: block;
      margin-block: calc(var(--spacingVerticalS) * -1) var(--spacingVerticalS);
      color: var(--colorNeutralForeground3);
      font-size: var(--fontSizeBase200);
      line-height: var(--lineHeightBase200);
    }
  `,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FluentTextInputComponent {
  readonly controlId = input('');
  readonly label = input('');
  readonly description = input('');
  readonly helpText = input('');
  readonly type = input<'email' | 'password' | 'tel' | 'text' | 'url'>('text');
  readonly value = input('');
  readonly placeholder = input('');
  readonly ariaLabel = input.required<string>();
  readonly disabled = input(false);
  readonly valueChange = output<string>();

  protected descriptionId(): string {
    return `${this.controlId()}-description`;
  }

  protected onInput(event: Event): void {
    this.valueChange.emit((event.currentTarget as HTMLElement & { value: string }).value);
  }
}
