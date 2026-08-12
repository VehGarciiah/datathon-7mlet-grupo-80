import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  inject,
  input,
} from '@angular/core';
import { FluentButtonComponent } from './fluent-button.component';
import { FluentIconComponent } from './fluent-icon.component';

@Component({
  selector: 'app-fluent-help',
  imports: [FluentButtonComponent, FluentIconComponent],
  template: `
    <app-fluent-button
      class="icon-only help-trigger"
      appearance="transparent"
      [controlId]="triggerId()"
      [iconOnly]="true"
      [ariaLabel]="'Ajuda: ' + label()"
    >
      <app-fluent-icon name="help" />
    </app-fluent-button>
  `,
  styles: `
    :host {
      display: inline-flex;
      flex: 0 0 auto;
      align-items: center;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FluentHelpComponent {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  readonly controlId = input.required<string>();
  readonly label = input.required<string>();
  readonly text = input.required<string>();

  constructor() {
    afterNextRender(() => this.mountTooltip());
  }

  protected triggerId(): string {
    return `${this.controlId()}-help`;
  }

  private mountTooltip(): void {
    const tooltip = this.host.nativeElement.ownerDocument.createElement('fluent-tooltip');
    tooltip.classList.add('crm-help-tooltip');
    tooltip.setAttribute('anchor', this.triggerId());
    tooltip.setAttribute('positioning', 'above');
    tooltip.setAttribute('delay', '300');
    tooltip.textContent = this.text();
    this.host.nativeElement.append(tooltip);
  }
}
