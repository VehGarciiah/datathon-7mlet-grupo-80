import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  input,
  output,
} from '@angular/core';
import { FluentHelpComponent } from './fluent-help.component';

@Component({
  selector: 'app-fluent-slider',
  imports: [FluentHelpComponent],
  template: `
    <span class="slider-heading">
      <span class="slider-label">
        <label [for]="controlId()">{{ label() }}</label>
        @if (helpText()) {
          <app-fluent-help [controlId]="controlId()" [label]="label()" [text]="helpText()" />
        }
      </span>
      <output [for]="controlId()">{{ formattedValue() }}</output>
    </span>
    @if (description()) {
      <span class="slider-description" [id]="descriptionId()">{{ description() }}</span>
    }
    <fluent-slider
      [id]="controlId()"
      size="medium"
      [value]="value().toString()"
      [min]="min().toString()"
      [max]="max().toString()"
      [step]="step().toString()"
      [disabled]="disabled()"
      [attr.aria-describedby]="description() ? descriptionId() : null"
      (change)="onChange($event)"
    ></fluent-slider>
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--spacingVerticalS);
    }
    .slider-heading {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--spacingHorizontalM);
    }
    label {
      color: var(--colorNeutralForeground1);
      font-weight: var(--fontWeightSemibold);
    }
    .slider-label {
      display: flex;
      min-inline-size: 0;
      align-items: center;
      gap: var(--spacingHorizontalS);
    }
    output {
      min-inline-size: 52px;
      padding: var(--spacingVerticalXXS) var(--spacingHorizontalS);
      border-radius: var(--borderRadiusMedium);
      background: var(--colorNeutralBackground3);
      color: var(--colorNeutralForeground2);
      text-align: center;
      font-variant-numeric: tabular-nums;
    }
    .slider-description {
      color: var(--colorNeutralForeground3);
      font-size: var(--fontSizeBase200);
      line-height: var(--lineHeightBase200);
    }
    fluent-slider {
      inline-size: 100%;
    }
  `,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FluentSliderComponent {
  readonly controlId = input.required<string>();
  readonly label = input.required<string>();
  readonly description = input('');
  readonly helpText = input('');
  readonly value = input.required<number>();
  readonly min = input(0);
  readonly max = input(100);
  readonly step = input(1);
  readonly suffix = input('');
  readonly disabled = input(false);
  readonly valueChange = output<number>();

  protected descriptionId(): string {
    return `${this.controlId()}-description`;
  }

  protected formattedValue(): string {
    return `${this.value()}${this.suffix()}`;
  }

  protected onChange(event: Event): void {
    const value = Number((event.currentTarget as HTMLElement & { value: string }).value);
    if (Number.isFinite(value)) this.valueChange.emit(value);
  }
}
