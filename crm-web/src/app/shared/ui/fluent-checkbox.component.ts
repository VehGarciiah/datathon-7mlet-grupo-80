import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  input,
  output,
} from '@angular/core';

@Component({
  selector: 'app-fluent-checkbox',
  template: `
    <span class="checkbox-field">
      <fluent-checkbox
        [id]="controlId()"
        size="medium"
        [checked]="checked()"
        [disabled]="disabled()"
        (change)="onChange($event)"
      ></fluent-checkbox>
      <label [for]="controlId()"><ng-content /></label>
    </span>
  `,
  styles: `
    :host {
      display: block;
    }
    .checkbox-field {
      display: flex;
      align-items: center;
      min-block-size: var(--crm-interactive-size);
      gap: var(--spacingHorizontalS);
    }
    label {
      cursor: pointer;
      color: var(--colorNeutralForeground1);
    }
    fluent-checkbox[disabled] + label {
      cursor: not-allowed;
      color: var(--colorNeutralForegroundDisabled);
    }
  `,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FluentCheckboxComponent {
  readonly controlId = input.required<string>();
  readonly checked = input(false);
  readonly disabled = input(false);
  readonly checkedChange = output<boolean>();

  protected onChange(event: Event): void {
    this.checkedChange.emit((event.currentTarget as HTMLElement & { checked: boolean }).checked);
  }
}
