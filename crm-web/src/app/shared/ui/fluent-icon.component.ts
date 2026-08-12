import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type FluentIconName =
  | 'search'
  | 'refresh'
  | 'moon'
  | 'sun'
  | 'phone'
  | 'call'
  | 'people'
  | 'contact'
  | 'sparkle'
  | 'brain'
  | 'success'
  | 'error'
  | 'dismiss'
  | 'previous'
  | 'next'
  | 'info'
  | 'history'
  | 'open'
  | 'navigation'
  | 'settings'
  | 'beaker'
  | 'shield'
  | 'branch'
  | 'data'
  | 'target'
  | 'save'
  | 'reset'
  | 'lock'
  | 'document'
  | 'pulse'
  | 'warning'
  | 'help';

@Component({
  selector: 'app-fluent-icon',
  template: `<span class="fluent-icon" [class]="cssClass()" aria-hidden="true"></span>`,
  styles: `
    :host {
      display: inline-flex;
      color: inherit;
    }
    .fluent-icon {
      display: inline-block;
      inline-size: var(--crm-icon-size);
      block-size: var(--crm-icon-size);
      background: currentColor;
      mask: var(--crm-icon) center / contain no-repeat;
    }
    .icon-search {
      --crm-icon: url('/icons/search_20_regular.svg');
    }
    .icon-refresh {
      --crm-icon: url('/icons/arrow_clockwise_20_regular.svg');
    }
    .icon-moon {
      --crm-icon: url('/icons/weather_moon_20_regular.svg');
    }
    .icon-sun {
      --crm-icon: url('/icons/weather_sunny_20_regular.svg');
    }
    .icon-phone {
      --crm-icon: url('/icons/phone_20_regular.svg');
    }
    .icon-call {
      --crm-icon: url('/icons/call_20_regular.svg');
    }
    .icon-people {
      --crm-icon: url('/icons/people_20_regular.svg');
    }
    .icon-contact {
      --crm-icon: url('/icons/contact_card_20_regular.svg');
    }
    .icon-sparkle {
      --crm-icon: url('/icons/sparkle_20_regular.svg');
    }
    .icon-brain {
      --crm-icon: url('/icons/brain_circuit_20_regular.svg');
    }
    .icon-success {
      --crm-icon: url('/icons/checkmark_circle_20_regular.svg');
    }
    .icon-error {
      --crm-icon: url('/icons/dismiss_circle_20_regular.svg');
    }
    .icon-dismiss {
      --crm-icon: url('/icons/dismiss_20_regular.svg');
    }
    .icon-previous {
      --crm-icon: url('/icons/chevron_left_20_regular.svg');
    }
    .icon-next {
      --crm-icon: url('/icons/chevron_right_20_regular.svg');
    }
    .icon-info {
      --crm-icon: url('/icons/info_20_regular.svg');
    }
    .icon-history {
      --crm-icon: url('/icons/history_20_regular.svg');
    }
    .icon-open {
      --crm-icon: url('/icons/open_20_regular.svg');
    }
    .icon-navigation {
      --crm-icon: url('/icons/navigation_20_regular.svg');
    }
    .icon-settings {
      --crm-icon: url('/icons/settings_20_regular.svg');
    }
    .icon-beaker {
      --crm-icon: url('/icons/beaker_20_regular.svg');
    }
    .icon-shield {
      --crm-icon: url('/icons/shield_checkmark_20_regular.svg');
    }
    .icon-branch {
      --crm-icon: url('/icons/branch_fork_20_regular.svg');
    }
    .icon-data {
      --crm-icon: url('/icons/data_usage_20_regular.svg');
    }
    .icon-target {
      --crm-icon: url('/icons/target_arrow_20_regular.svg');
    }
    .icon-save {
      --crm-icon: url('/icons/save_20_regular.svg');
    }
    .icon-reset {
      --crm-icon: url('/icons/arrow_reset_20_regular.svg');
    }
    .icon-lock {
      --crm-icon: url('/icons/lock_closed_20_regular.svg');
    }
    .icon-document {
      --crm-icon: url('/icons/document_data_20_regular.svg');
    }
    .icon-pulse {
      --crm-icon: url('/icons/pulse_20_regular.svg');
    }
    .icon-warning {
      --crm-icon: url('/icons/warning_20_regular.svg');
    }
    .icon-help {
      --crm-icon: url('/icons/question_circle_20_regular.svg');
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FluentIconComponent {
  readonly name = input.required<FluentIconName>();
  protected readonly cssClass = computed(() => `fluent-icon icon-${this.name()}`);
}
