import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  input,
  output,
} from '@angular/core';
import { FluentHelpComponent } from './fluent-help.component';

@Component({
  selector: 'app-fluent-switch',
  imports: [FluentHelpComponent],
  template: `
    <span class="switch-field">
      <span class="switch-copy">
        <span class="switch-label">
          <label [for]="controlId()">{{ label() }}</label>
          @if (helpText()) {
            <app-fluent-help [controlId]="controlId()" [label]="label()" [text]="helpText()" />
          }
        </span>
        @if (description()) {
          <span [id]="descriptionId()">{{ description() }}</span>
        }
      </span>
      <fluent-switch
        [id]="controlId()"
        [checked]="checked()"
        [disabled]="disabled()"
        [attr.aria-describedby]="description() ? descriptionId() : null"
        (change)="onChange($event)"
      ></fluent-switch>
    </span>
  `,
  styles: `
    :host {
      display: block;
    }
    .switch-field {
      display: flex;
      min-block-size: var(--crm-interactive-size);
      align-items: center;
      justify-content: space-between;
      gap: var(--spacingHorizontalL);
    }
    .switch-copy {
      display: grid;
      min-inline-size: 0;
      gap: var(--spacingVerticalXXS);
    }
    label {
      color: var(--colorNeutralForeground1);
      font-weight: var(--fontWeightSemibold);
      cursor: pointer;
    }
    .switch-label {
      display: flex;
      min-inline-size: 0;
      align-items: center;
      gap: var(--spacingHorizontalS);
    }
    .switch-copy span {
      color: var(--colorNeutralForeground3);
      font-size: var(--fontSizeBase200);
      line-height: var(--lineHeightBase200);
    }
    fluent-switch {
      flex: 0 0 auto;
    }
    fluent-switch[disabled] + label,
    fluent-switch[disabled] {
      cursor: not-allowed;
    }
  `,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FluentSwitchComponent {
  readonly controlId = input.required<string>();
  readonly label = input.required<string>();
  readonly description = input('');
  readonly helpText = input('');
  readonly checked = input(false);
  readonly disabled = input(false);
  readonly checkedChange = output<boolean>();

  protected descriptionId(): string {
    return `${this.controlId()}-description`;
  }

  protected onChange(event: Event): void {
    this.checkedChange.emit((event.currentTarget as HTMLElement & { checked: boolean }).checked);
  }
}
