import {
  afterNextRender,
  afterRenderEffect,
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  ElementRef,
  input,
  output,
  viewChild,
} from '@angular/core';
import { FluentHelpComponent } from './fluent-help.component';

export interface FluentDropdownOption {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
}

@Component({
  selector: 'app-fluent-dropdown',
  imports: [FluentHelpComponent],
  template: `
    <span class="field-label">
      <label [for]="controlId()">{{ label() }}</label>
      @if (helpText()) {
        <app-fluent-help [controlId]="controlId()" [label]="label()" [text]="helpText()" />
      }
    </span>
    @if (description()) {
      <span class="field-description" [id]="descriptionId()">{{ description() }}</span>
    }
    <fluent-dropdown
      #dropdown
      [id]="controlId()"
      appearance="outline"
      size="large"
      type="select"
      [disabled]="disabled()"
      (click)="syncAriaSoon()"
      (keydown)="syncAriaSoon()"
      (change)="onChange($event)"
    >
      <fluent-listbox role="listbox">
        @for (option of options(); track option.value) {
          <fluent-option
            [value]="option.value"
            [attr.text]="option.label"
            [selected]="option.value === value()"
            [disabled]="option.disabled ?? false"
            role="option"
            [attr.aria-selected]="option.value === value()"
          >
            {{ option.label }}
            @if (option.description) {
              <span slot="description">{{ option.description }}</span>
            }
          </fluent-option>
        }
      </fluent-listbox>
    </fluent-dropdown>
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--spacingVerticalS);
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
      color: var(--colorNeutralForeground3);
      font-size: var(--fontSizeBase200);
      line-height: var(--lineHeightBase200);
    }
    fluent-dropdown {
      inline-size: 100%;
      min-block-size: var(--crm-interactive-size);
    }
  `,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FluentDropdownComponent {
  private readonly dropdown = viewChild<ElementRef<HTMLElement>>('dropdown');
  readonly controlId = input.required<string>();
  readonly label = input.required<string>();
  readonly description = input('');
  readonly helpText = input('');
  readonly options = input.required<readonly FluentDropdownOption[]>();
  readonly value = input.required<string>();
  readonly disabled = input(false);
  readonly valueChange = output<string>();

  constructor() {
    afterNextRender(() => setTimeout(() => this.syncControlAria()));
    afterRenderEffect(() => {
      const value = this.value();
      const dropdown = this.dropdown()?.nativeElement as
        (HTMLElement & { value: string }) | undefined;
      if (dropdown && dropdown.value !== value) {
        dropdown.value = value;
      }
      setTimeout(() => this.syncControlAria());
    });
  }

  protected descriptionId(): string {
    return `${this.controlId()}-description`;
  }

  protected onChange(event: Event): void {
    this.valueChange.emit((event.currentTarget as HTMLElement & { value: string }).value);
    this.syncAriaSoon();
  }

  protected syncAriaSoon(): void {
    queueMicrotask(() => this.syncControlAria());
    setTimeout(() => this.syncControlAria());
  }

  private syncControlAria(): void {
    const host = this.dropdown()?.nativeElement as (HTMLElement & { open?: boolean }) | undefined;
    const control =
      host?.querySelector<HTMLElement>('[role="combobox"]') ??
      host?.shadowRoot?.querySelector<HTMLElement>('[role="combobox"]');
    if (!control) return;
    control.setAttribute('aria-label', this.label());
    control.setAttribute('aria-expanded', String(host?.open === true));
    if (this.description()) {
      control.setAttribute('aria-describedby', this.descriptionId());
    } else {
      control.removeAttribute('aria-describedby');
    }
  }
}
