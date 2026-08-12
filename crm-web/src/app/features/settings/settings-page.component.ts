import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnDestroy,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { CrmApiService, readableApiError } from '../../core/api/crm-api.service';
import { PolicyMode, RuntimeConfiguration } from '../../core/models/crm.models';
import { FluentBadgeComponent } from '../../shared/ui/fluent-badge.component';
import { FluentButtonComponent } from '../../shared/ui/fluent-button.component';
import {
  FluentDropdownComponent,
  FluentDropdownOption,
} from '../../shared/ui/fluent-dropdown.component';
import { FluentIconComponent } from '../../shared/ui/fluent-icon.component';
import { FluentHelpComponent } from '../../shared/ui/fluent-help.component';
import { FluentSliderComponent } from '../../shared/ui/fluent-slider.component';
import { FluentSpinnerComponent } from '../../shared/ui/fluent-spinner.component';
import { FluentSwitchComponent } from '../../shared/ui/fluent-switch.component';
import { FluentTextInputComponent } from '../../shared/ui/fluent-text-input.component';

type SettingSectionId =
  'runtime' | 'traffic' | 'learning' | 'feedback' | 'models' | 'observability' | 'guardrails';

const SETTING_SECTION_IDS: readonly SettingSectionId[] = [
  'runtime',
  'traffic',
  'learning',
  'feedback',
  'models',
  'observability',
  'guardrails',
];

interface ConfigurationDraft {
  policyMode: PolicyMode;
  killSwitch: boolean;
  adaptiveTrafficPercentage: number;
  experimentName: string;
  deterministicAllocation: boolean;
  learningEnabled: boolean;
  attributionWindowDays: number;
  structuredLogs: boolean;
  decisionMetrics: boolean;
  feedbackMetrics: boolean;
  configurationAudit: boolean;
  traceSamplingPercentage: number;
}

interface StoredConfigurationDraft {
  version: 1;
  savedAt: string;
  draft: ConfigurationDraft;
}

interface LiveMessage {
  kind: 'success' | 'info' | 'error';
  text: string;
}

const STORAGE_KEY = 'crm-policy-configuration-draft-v1';

const DEFAULT_DRAFT: ConfigurationDraft = {
  policyMode: 'approved',
  killSwitch: false,
  adaptiveTrafficPercentage: 0,
  experimentName: '',
  deterministicAllocation: true,
  learningEnabled: false,
  attributionWindowDays: 7,
  structuredLogs: true,
  decisionMetrics: true,
  feedbackMetrics: true,
  configurationAudit: true,
  traceSamplingPercentage: 10,
};

@Component({
  selector: 'app-settings-page',
  imports: [
    FluentBadgeComponent,
    FluentButtonComponent,
    FluentDropdownComponent,
    FluentHelpComponent,
    FluentIconComponent,
    FluentSliderComponent,
    FluentSpinnerComponent,
    FluentSwitchComponent,
    FluentTextInputComponent,
  ],
  templateUrl: './settings-page.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsPageComponent implements OnDestroy {
  private readonly api = inject(CrmApiService);
  private sectionObserver?: IntersectionObserver;

  protected readonly modeOptions: readonly FluentDropdownOption[] = [
    {
      value: 'approved',
      label: 'Baseline aprovada',
      description: 'Política fixa validada; não atualiza o posterior.',
    },
    {
      value: 'approved_adaptive',
      label: 'Adaptativa aprovada',
      description: 'Destino para promoção controlada após aprovação.',
    },
    {
      value: 'adaptive_demo',
      label: 'Adaptativa de demonstração',
      description: 'Modo explícito para experimentar o ciclo de feedback.',
    },
  ];

  protected readonly draft = signal<ConfigurationDraft>({ ...DEFAULT_DRAFT });
  protected readonly activeSection = signal<SettingSectionId>('runtime');
  protected readonly controlsReady = signal(false);
  protected readonly savedSnapshot = signal<ConfigurationDraft>({ ...DEFAULT_DRAFT });
  protected readonly activeSnapshot = signal<ConfigurationDraft>({ ...DEFAULT_DRAFT });
  protected readonly activeConfiguration = signal<RuntimeConfiguration | null>(null);
  protected readonly lastSavedAt = signal<string | null>(null);
  protected readonly liveMessage = signal<LiveMessage | null>(null);
  protected readonly activating = signal(false);
  protected readonly configurationLoading = signal(false);
  protected readonly activationOperator = signal('');
  protected readonly activationReason = signal('');

  protected readonly isAdaptive = computed(() => this.draft().policyMode !== 'approved');
  protected readonly modeLabel = computed(() => this.labelForMode(this.draft().policyMode));
  protected readonly changedCount = computed(() => {
    const current = this.draft();
    const saved = this.savedSnapshot();
    return (Object.keys(current) as (keyof ConfigurationDraft)[]).filter(
      (key) => current[key] !== saved[key],
    ).length;
  });
  protected readonly activationChangedCount = computed(() => {
    const current = this.draft();
    const active = this.activeSnapshot();
    return (Object.keys(current) as (keyof ConfigurationDraft)[]).filter(
      (key) => current[key] !== active[key],
    ).length;
  });
  protected readonly canActivate = computed(
    () =>
      this.activeConfiguration() !== null &&
      this.activationChangedCount() > 0 &&
      this.validationIssues().length === 0 &&
      this.activationOperator().trim().length > 0 &&
      this.activationReason().trim().length >= 10 &&
      !this.activating(),
  );
  protected readonly activationGuidance = computed(() => {
    if (this.activeConfiguration() === null) {
      return 'Reconecte o OpenFeature antes de ativar uma versão.';
    }
    if (this.validationIssues().length > 0) {
      return 'Corrija os avisos do rascunho antes de ativar.';
    }
    if (this.activationChangedCount() === 0) {
      return 'Altere ao menos uma configuração para criar uma nova versão.';
    }
    if (!this.activationOperator().trim()) {
      return 'Informe a pessoa responsável pela ativação.';
    }
    if (this.activationReason().trim().length < 10) {
      return 'Explique o motivo da ativação com pelo menos 10 caracteres.';
    }
    return 'Tudo pronto. A ativação criará uma nova versão auditável.';
  });
  protected readonly activeModeLabel = computed(() => {
    const configuration = this.activeConfiguration();
    if (!configuration) return 'Configuração indisponível';
    return configuration.policyMode === 'approved'
      ? 'Baseline fixa de rollback'
      : this.labelForMode(configuration.policyMode);
  });
  protected readonly validationIssues = computed(() => {
    const draft = this.draft();
    const issues: string[] = [];
    if (this.isAdaptive() && draft.adaptiveTrafficPercentage === 0) {
      issues.push('Defina uma parcela de tráfego maior que zero para o modo adaptativo.');
    }
    if (draft.adaptiveTrafficPercentage > 0 && !draft.experimentName.trim()) {
      issues.push('Identifique o experimento antes de salvar uma distribuição de tráfego.');
    }
    if (draft.learningEnabled && !this.isAdaptive()) {
      issues.push('O aprendizado online só pode ser usado por uma política adaptativa.');
    }
    return issues;
  });
  protected readonly impactNotes = computed(() => {
    const draft = this.draft();
    const notes: string[] = [];
    if (draft.killSwitch) {
      notes.push('Kill switch força 100% do tráfego para a baseline aprovada.');
    } else if (this.isAdaptive()) {
      notes.push(`${draft.adaptiveTrafficPercentage}% do tráfego iria para a política adaptativa.`);
      notes.push(
        draft.learningEnabled
          ? 'Feedback terminal atualizaria somente o braço recomendado.'
          : 'As decisões adaptativas não alterariam o posterior.',
      );
    } else {
      notes.push('A baseline fixa permanece responsável por todas as recomendações.');
    }
    notes.push(`Retenção de atribuição: ${draft.attributionWindowDays} dias.`);
    return notes;
  });
  protected readonly draftJson = computed(() =>
    JSON.stringify(
      {
        schema_version: 'ui-draft/1',
        serving: {
          policy_mode: this.draft().policyMode,
          kill_switch: this.draft().killSwitch,
          adaptive_traffic_percentage: this.draft().adaptiveTrafficPercentage,
          experiment_name: this.draft().experimentName || null,
          deterministic_allocation: this.draft().deterministicAllocation,
        },
        feedback: {
          learning_enabled: this.draft().learningEnabled,
          attribution_window_days: this.draft().attributionWindowDays,
          accept_future_clock_skew_seconds: 300,
        },
        observability: {
          structured_logs: this.draft().structuredLogs,
          decision_metrics: this.draft().decisionMetrics,
          feedback_metrics: this.draft().feedbackMetrics,
          configuration_audit: this.draft().configurationAudit,
          trace_sampling_percentage: this.draft().traceSamplingPercentage,
        },
      },
      null,
      2,
    ),
  );

  constructor() {
    afterNextRender(async () => {
      await import('./settings-fluent-elements');
      const hasLocalDraft = this.loadSavedDraft();
      await this.loadActiveConfiguration(hasLocalDraft);
      this.controlsReady.set(true);
      setTimeout(() => {
        this.restoreSectionFromUrl();
        this.observeVisibleSections();
      });
    });
  }

  ngOnDestroy(): void {
    this.sectionObserver?.disconnect();
  }

  protected navigateToSection(event: Event, sectionId: SettingSectionId): void {
    event.preventDefault();
    this.scrollToSection(sectionId, true);
  }

  protected setMode(value: string): void {
    if (!this.isPolicyMode(value)) return;
    if (value === 'approved') {
      this.updateDraft({
        policyMode: value,
        adaptiveTrafficPercentage: 0,
        learningEnabled: false,
      });
      return;
    }
    this.updateDraft({
      policyMode: value,
      adaptiveTrafficPercentage:
        value === 'adaptive_demo' ? 100 : this.draft().adaptiveTrafficPercentage || 10,
      learningEnabled: true,
    });
  }

  protected setKillSwitch(enabled: boolean): void {
    this.updateDraft(
      enabled
        ? {
            killSwitch: true,
            policyMode: 'approved',
            adaptiveTrafficPercentage: 0,
            learningEnabled: false,
          }
        : { killSwitch: false },
    );
  }

  protected updateDraft(change: Partial<ConfigurationDraft>): void {
    this.draft.update((draft) => ({ ...draft, ...change }));
    this.liveMessage.set(null);
  }

  protected saveDraft(): void {
    if (this.validationIssues().length > 0 || this.changedCount() === 0) return;
    const savedAt = new Date().toISOString();
    const snapshot = { ...this.draft() };
    const stored: StoredConfigurationDraft = { version: 1, savedAt, draft: snapshot };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
    this.savedSnapshot.set(snapshot);
    this.lastSavedAt.set(savedAt);
    this.liveMessage.set({
      kind: 'success',
      text: 'Rascunho salvo neste navegador. Nenhuma política em execução foi alterada.',
    });
  }

  protected async activateConfiguration(): Promise<void> {
    const active = this.activeConfiguration();
    if (!active || !this.canActivate()) return;
    this.activating.set(true);
    this.liveMessage.set(null);
    try {
      const draft = this.draft();
      const activated = await firstValueFrom(
        this.api.activateConfiguration({
          expectedVersion: active.version,
          operator: this.activationOperator().trim(),
          reason: this.activationReason().trim(),
          ...draft,
        }),
      );
      this.activeConfiguration.set(activated);
      this.activeSnapshot.set(this.configurationToDraft(activated));
      this.savedSnapshot.set({ ...draft });
      this.persistDraft(draft);
      this.activationReason.set('');
      this.liveMessage.set({
        kind: 'success',
        text: `Configuração v${activated.version} ativada. O flagd deve propagá-la em até ${activated.expectedPropagationSeconds} segundos.`,
      });
    } catch (error) {
      this.liveMessage.set({ kind: 'error', text: readableApiError(error) });
    } finally {
      this.activating.set(false);
    }
  }

  protected setActivationOperator(value: string): void {
    this.activationOperator.set(value);
  }

  protected setActivationReason(value: string): void {
    this.activationReason.set(value);
  }

  protected dismissMessage(): void {
    this.liveMessage.set(null);
  }

  protected async reloadActiveConfiguration(): Promise<void> {
    await this.loadActiveConfiguration(true);
    if (this.activeConfiguration()) {
      this.liveMessage.set({
        kind: 'success',
        text: `Configuração ativa v${this.activeConfiguration()?.version} sincronizada.`,
      });
    }
  }

  protected discardChanges(): void {
    this.draft.set({ ...this.savedSnapshot() });
    this.liveMessage.set({ kind: 'info', text: 'Alterações não salvas foram descartadas.' });
  }

  protected restoreDefaults(): void {
    this.draft.set({ ...DEFAULT_DRAFT });
    this.liveMessage.set({
      kind: 'info',
      text: 'Defaults do projeto restaurados no rascunho. Salve para mantê-los neste navegador.',
    });
  }

  protected formatSavedAt(): string {
    const value = this.lastSavedAt();
    if (!value) return 'Ainda não salvo';
    return new Intl.DateTimeFormat('pt-BR', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(new Date(value));
  }

  protected formatActiveAt(): string {
    const value = this.activeConfiguration()?.activatedAt;
    if (!value) return 'Indisponível';
    return new Intl.DateTimeFormat('pt-BR', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(new Date(value));
  }

  private restoreSectionFromUrl(): void {
    const fragment = window.location.hash.slice(1);
    if (this.isSettingSection(fragment)) {
      this.scrollToSection(fragment, false);
    }
  }

  private scrollToSection(sectionId: SettingSectionId, updateUrl: boolean): void {
    const section = document.getElementById(sectionId);
    if (!section) return;
    this.activeSection.set(sectionId);
    if (updateUrl) {
      const url = new URL(window.location.href);
      url.hash = sectionId;
      window.history.replaceState(null, '', url);
    }
    section.focus({ preventScroll: true });
    section.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'start',
    });
  }

  private isSettingSection(value: string): value is SettingSectionId {
    return SETTING_SECTION_IDS.includes(value as SettingSectionId);
  }

  private loadSavedDraft(): boolean {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    try {
      const stored = JSON.parse(raw) as Partial<StoredConfigurationDraft>;
      if (stored.version !== 1 || !stored.draft || !this.isPolicyMode(stored.draft.policyMode)) {
        return false;
      }
      const normalized = this.normalizeDraft(stored.draft);
      this.draft.set(normalized);
      this.savedSnapshot.set({ ...normalized });
      this.lastSavedAt.set(typeof stored.savedAt === 'string' ? stored.savedAt : null);
      return true;
    } catch {
      localStorage.removeItem(STORAGE_KEY);
      return false;
    }
  }

  private async loadActiveConfiguration(preserveLocalDraft: boolean): Promise<void> {
    if (this.configurationLoading()) return;
    this.configurationLoading.set(true);
    try {
      const active = await firstValueFrom(this.api.getActiveConfiguration());
      const activeDraft = this.configurationToDraft(active);
      this.activeConfiguration.set(active);
      this.activeSnapshot.set(activeDraft);
      if (!preserveLocalDraft) {
        this.draft.set({ ...activeDraft });
        this.savedSnapshot.set({ ...activeDraft });
      }
    } catch (error) {
      this.activeConfiguration.set(null);
      this.liveMessage.set({
        kind: 'error',
        text: `${readableApiError(error)} A ativação permanecerá indisponível.`,
      });
    } finally {
      this.configurationLoading.set(false);
    }
  }

  private observeVisibleSections(): void {
    if (!('IntersectionObserver' in window)) return;
    this.sectionObserver?.disconnect();
    this.sectionObserver = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        if (visible && this.isSettingSection(visible.target.id)) {
          this.activeSection.set(visible.target.id);
        }
      },
      { rootMargin: '-18% 0px -62% 0px', threshold: [0.05, 0.25, 0.5] },
    );
    for (const sectionId of SETTING_SECTION_IDS) {
      const section = document.getElementById(sectionId);
      if (section) this.sectionObserver.observe(section);
    }
  }

  private configurationToDraft(configuration: RuntimeConfiguration): ConfigurationDraft {
    return this.normalizeDraft(configuration);
  }

  private persistDraft(draft: ConfigurationDraft): void {
    const savedAt = new Date().toISOString();
    const stored: StoredConfigurationDraft = { version: 1, savedAt, draft: { ...draft } };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
    this.lastSavedAt.set(savedAt);
  }

  private normalizeDraft(value: Partial<ConfigurationDraft>): ConfigurationDraft {
    const numberInRange = (candidate: unknown, fallback: number, min: number, max: number) =>
      typeof candidate === 'number' && Number.isFinite(candidate)
        ? Math.min(max, Math.max(min, candidate))
        : fallback;
    return {
      policyMode: this.isPolicyMode(value.policyMode) ? value.policyMode : DEFAULT_DRAFT.policyMode,
      killSwitch: value.killSwitch === true,
      adaptiveTrafficPercentage: numberInRange(value.adaptiveTrafficPercentage, 0, 0, 100),
      experimentName: typeof value.experimentName === 'string' ? value.experimentName : '',
      deterministicAllocation: value.deterministicAllocation !== false,
      learningEnabled: value.learningEnabled === true,
      attributionWindowDays: numberInRange(value.attributionWindowDays, 7, 1, 30),
      structuredLogs: value.structuredLogs !== false,
      decisionMetrics: value.decisionMetrics !== false,
      feedbackMetrics: value.feedbackMetrics !== false,
      configurationAudit: value.configurationAudit !== false,
      traceSamplingPercentage: numberInRange(value.traceSamplingPercentage, 10, 0, 100),
    };
  }

  private isPolicyMode(value: unknown): value is PolicyMode {
    return value === 'approved' || value === 'approved_adaptive' || value === 'adaptive_demo';
  }

  private labelForMode(value: PolicyMode): string {
    return this.modeOptions.find((option) => option.value === value)?.label ?? value;
  }
}
