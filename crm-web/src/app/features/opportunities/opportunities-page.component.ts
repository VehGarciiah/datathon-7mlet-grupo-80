import { DOCUMENT, isPlatformBrowser } from '@angular/common';
import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnDestroy,
  PLATFORM_ID,
  signal,
} from '@angular/core';
import { finalize, forkJoin, Subscription } from 'rxjs';
import { CrmApiService, readableApiError } from '../../core/api/crm-api.service';
import {
  ContactChannel,
  FeedbackResult,
  Opportunity,
  PageResponse,
  Recommendation,
} from '../../core/models/crm.models';
import { FluentBadgeColor, FluentBadgeComponent } from '../../shared/ui/fluent-badge.component';
import { FluentButtonComponent } from '../../shared/ui/fluent-button.component';
import { FluentCheckboxComponent } from '../../shared/ui/fluent-checkbox.component';
import { FluentIconComponent, FluentIconName } from '../../shared/ui/fluent-icon.component';
import { FluentSpinnerComponent } from '../../shared/ui/fluent-spinner.component';
import { FluentTextInputComponent } from '../../shared/ui/fluent-text-input.component';

interface LiveMessage {
  kind: 'success' | 'error' | 'info';
  text: string;
}

type FeedbackConfirmation =
  | { kind: 'manual'; recommendation: Recommendation; reward: 0 | 1 }
  | { kind: 'historical'; recommendation: Recommendation };

interface DecisionFeedbackView {
  kind: 'none' | 'recorded' | 'inconclusive';
  terminal: boolean;
  title: string;
  historyLabel: string;
  historyDetail: string;
  description: string;
  reason: string;
  badgeColor: FluentBadgeColor;
  icon: FluentIconName;
}

@Component({
  selector: 'app-opportunities-page',
  imports: [
    FluentBadgeComponent,
    FluentButtonComponent,
    FluentCheckboxComponent,
    FluentIconComponent,
    FluentSpinnerComponent,
    FluentTextInputComponent,
  ],
  templateUrl: './opportunities-page.component.html',
  styleUrl: './opportunities-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OpportunitiesPageComponent implements OnDestroy {
  private readonly api = inject(CrmApiService);
  private readonly document = inject(DOCUMENT);
  private readonly platformId = inject(PLATFORM_ID);
  private searchTimer: ReturnType<typeof setTimeout> | undefined;
  private pageRequest?: Subscription;
  private detailRequest?: Subscription;
  private feedbackTrigger?: HTMLElement;

  protected readonly pageData = signal<PageResponse<Opportunity> | null>(null);
  protected readonly selected = signal<Opportunity | null>(null);
  protected readonly selectedId = signal<number | null>(null);
  protected readonly recommendations = signal<Recommendation[]>([]);
  protected readonly feedbackResults = signal<Record<string, FeedbackResult>>({});
  protected readonly feedbackConfirmation = signal<FeedbackConfirmation | null>(null);
  protected readonly search = signal('');
  protected readonly currentPage = signal(0);
  protected readonly pageLoading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly eligibilitySaving = signal(false);
  protected readonly recommendationCreating = signal(false);
  protected readonly feedbackAction = signal('');
  protected readonly pageError = signal('');
  protected readonly detailError = signal('');
  protected readonly liveMessage = signal<LiveMessage | null>(null);

  protected readonly draftAuthorized = signal(false);
  protected readonly draftDoNotContact = signal(false);
  protected readonly draftCellphone = signal(false);
  protected readonly draftLandline = signal(false);

  protected readonly opportunities = computed(() => this.pageData()?.content ?? []);
  protected readonly totalElements = computed(() => this.pageData()?.totalElements ?? 0);
  protected readonly authorizedOnPage = computed(
    () =>
      this.opportunities().filter((item) => item.contactAuthorized && !item.doNotContact).length,
  );
  protected readonly historicalOnPage = computed(
    () => this.opportunities().filter((item) => item.historicalOutcomeAvailable).length,
  );
  protected readonly firstVisibleItem = computed(() => {
    const page = this.pageData();
    return page && page.totalElements > 0 ? page.page * page.size + 1 : 0;
  });
  protected readonly lastVisibleItem = computed(() => {
    const page = this.pageData();
    return page ? Math.min((page.page + 1) * page.size, page.totalElements) : 0;
  });
  protected readonly hasPreviousPage = computed(() => (this.pageData()?.page ?? 0) > 0);
  protected readonly hasNextPage = computed(() => {
    const page = this.pageData();
    return !!page && page.page + 1 < page.totalPages;
  });
  protected readonly latestRecommendation = computed(() => this.recommendations()[0] ?? null);
  protected readonly canRecommend = computed(() => {
    return (
      this.selected() !== null &&
      !this.eligibilityChanged() &&
      this.draftAuthorized() &&
      !this.draftDoNotContact() &&
      (this.draftCellphone() || this.draftLandline())
    );
  });
  protected readonly eligibilityChanged = computed(() => {
    const item = this.selected();
    if (!item) return false;
    return (
      item.contactAuthorized !== this.draftAuthorized() ||
      item.doNotContact !== this.draftDoNotContact() ||
      item.eligibleChannels.includes('celular') !== this.draftCellphone() ||
      item.eligibleChannels.includes('telefone') !== this.draftLandline()
    );
  });

  constructor() {
    afterNextRender(() => {
      this.loadPage();
    });
  }

  ngOnDestroy(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.pageRequest?.unsubscribe();
    this.detailRequest?.unsubscribe();
  }

  protected onSearchChange(value: string): void {
    if (this.eligibilityChanged()) return;
    this.search.set(value);
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.currentPage.set(0);
      this.loadPage();
    }, 350);
  }

  protected refresh(): void {
    if (this.eligibilityChanged()) {
      this.showMessage(
        'info',
        'Salve ou descarte as alterações de elegibilidade antes de atualizar.',
      );
      return;
    }
    this.loadPage(true);
  }

  protected clearSearch(): void {
    if (this.eligibilityChanged()) return;
    this.search.set('');
    this.currentPage.set(0);
    this.loadPage();
  }

  protected goToPage(direction: -1 | 1): void {
    const next = this.currentPage() + direction;
    if (next < 0 || next >= (this.pageData()?.totalPages ?? 0)) return;
    this.currentPage.set(next);
    this.loadPage();
  }

  protected selectOpportunity(item: Opportunity): void {
    if (this.selectedId() === item.id && !this.detailError()) return;
    if (this.eligibilityChanged()) {
      this.showMessage(
        'info',
        'Salve ou descarte as alterações de elegibilidade antes de abrir outra oportunidade.',
      );
      return;
    }
    this.selectImmediately(item);
    this.loadDetail(item.id);
    this.scrollToDetailOnCompactLayout();
  }

  protected retryDetail(): void {
    const id = this.selectedId();
    if (id !== null) this.loadDetail(id);
  }

  protected setAuthorized(value: boolean): void {
    this.draftAuthorized.set(value);
    if (value) this.draftDoNotContact.set(false);
  }

  protected setDoNotContact(value: boolean): void {
    this.draftDoNotContact.set(value);
    if (value) this.draftAuthorized.set(false);
  }

  protected saveEligibility(): void {
    const item = this.selected();
    if (!item) return;

    const channels: ContactChannel[] = [];
    if (this.draftCellphone()) channels.push('celular');
    if (this.draftLandline()) channels.push('telefone');
    if (channels.length === 0) {
      this.showMessage('error', 'Selecione pelo menos um canal elegível.');
      return;
    }

    this.eligibilitySaving.set(true);
    this.api
      .updateEligibility(item.id, {
        contactAuthorized: this.draftAuthorized(),
        doNotContact: this.draftDoNotContact(),
        eligibleChannels: channels,
      })
      .pipe(finalize(() => this.eligibilitySaving.set(false)))
      .subscribe({
        next: (updated) => {
          this.selected.set(updated);
          this.syncDraft(updated);
          this.replaceOpportunity(updated);
          this.showMessage('success', 'Elegibilidade atualizada.');
        },
        error: (error) => this.showMessage('error', readableApiError(error)),
      });
  }

  protected discardEligibilityChanges(): void {
    const item = this.selected();
    if (!item || !this.eligibilityChanged()) return;
    this.syncDraft(item);
    this.showMessage('info', 'Alterações de elegibilidade descartadas.');
  }

  protected createRecommendation(): void {
    const item = this.selected();
    if (!item || !this.canRecommend()) return;

    this.recommendationCreating.set(true);
    this.api
      .createRecommendation(item.id)
      .pipe(finalize(() => this.recommendationCreating.set(false)))
      .subscribe({
        next: (recommendation) => {
          this.recommendations.update((items) => [recommendation, ...items]);
          this.showMessage(
            'success',
            `Recomendação criada: ${this.channelLabel(recommendation.recommendedChannel)}.`,
          );
        },
        error: (error) => this.showMessage('error', readableApiError(error)),
      });
  }

  protected requestFeedback(
    event: MouseEvent,
    recommendation: Recommendation,
    reward: 0 | 1,
  ): void {
    this.rememberFeedbackTrigger(event);
    this.feedbackConfirmation.set({ kind: 'manual', recommendation, reward });
    this.focusFeedbackConfirmation();
  }

  protected requestHistoricalSimulation(event: MouseEvent, recommendation: Recommendation): void {
    this.rememberFeedbackTrigger(event);
    this.feedbackConfirmation.set({ kind: 'historical', recommendation });
    this.focusFeedbackConfirmation();
  }

  protected confirmFeedback(): void {
    const pending = this.feedbackConfirmation();
    if (!pending) return;
    this.feedbackConfirmation.set(null);
    if (pending.kind === 'manual') {
      this.sendFeedback(pending.recommendation, pending.reward);
    } else {
      this.simulateHistorical(pending.recommendation);
    }
  }

  protected cancelFeedbackConfirmation(): void {
    this.feedbackConfirmation.set(null);
    queueMicrotask(() => this.feedbackTrigger?.focus());
  }

  protected dismissMessage(): void {
    this.liveMessage.set(null);
  }

  private sendFeedback(recommendation: Recommendation, reward: 0 | 1): void {
    const actionId = `${recommendation.id}:feedback`;
    this.feedbackAction.set(actionId);
    this.api
      .sendFeedback(recommendation.id, reward)
      .pipe(finalize(() => this.feedbackAction.set('')))
      .subscribe({
        next: (result) => {
          this.storeFeedback(result);
          this.showMessage(
            'success',
            reward === 1 ? 'Conversão registrada.' : 'Contato sem conversão registrado.',
          );
        },
        error: (error) => this.showMessage('error', readableApiError(error)),
      });
  }

  private simulateHistorical(recommendation: Recommendation): void {
    const actionId = `${recommendation.id}:simulation`;
    this.feedbackAction.set(actionId);
    this.api
      .simulateHistorical(recommendation.id)
      .pipe(finalize(() => this.feedbackAction.set('')))
      .subscribe({
        next: (result) => {
          this.storeFeedback(result);
          this.showMessage(
            'info',
            result.feedbackSent
              ? 'Resultado histórico compatível aplicado à simulação.'
              : result.reason || 'Não existe resultado factual para o canal recomendado.',
          );
        },
        error: (error) => this.showMessage('error', readableApiError(error)),
      });
  }

  protected feedbackStatus(recommendation: Recommendation): DecisionFeedbackView {
    const sessionFeedback = this.feedbackResults()[recommendation.id];
    if (sessionFeedback && !sessionFeedback.feedbackSent) {
      const reason = sessionFeedback.reason || 'Não existe resultado factual observável.';
      return {
        kind: 'inconclusive',
        terminal: false,
        title: 'Simulação inconclusiva',
        historyLabel: 'Simulação inconclusiva',
        historyDetail: 'Nenhum feedback terminal foi registrado',
        description: reason,
        reason: '',
        badgeColor: 'warning',
        icon: 'warning',
      };
    }
    if (sessionFeedback?.feedbackSent) {
      return this.recordedFeedbackView(
        sessionFeedback.source,
        sessionFeedback.reward,
        sessionFeedback.learningApplied,
        sessionFeedback.reason,
        null,
      );
    }
    if (recommendation.feedback) {
      return this.recordedFeedbackView(
        recommendation.feedback.source,
        recommendation.feedback.reward,
        recommendation.feedback.learningApplied,
        recommendation.feedback.reason,
        recommendation.feedback.observedAt,
      );
    }
    return {
      kind: 'none',
      terminal: false,
      title: 'Sem feedback',
      historyLabel: 'Sem feedback',
      historyDetail: 'Nenhum resultado foi informado para esta decisão',
      description: '',
      reason: '',
      badgeColor: 'subtle',
      icon: 'info',
    };
  }

  protected isFeedbackBusy(recommendationId: string): boolean {
    return this.feedbackAction().startsWith(recommendationId);
  }

  protected channelLabel(channel: ContactChannel): string {
    return channel === 'celular' ? 'Celular' : 'Telefone';
  }

  protected channelIcon(channel: ContactChannel): 'phone' | 'call' {
    return channel === 'celular' ? 'phone' : 'call';
  }

  protected outcomeLabel(outcome: string): string {
    const labels: Record<string, string> = {
      sucesso: 'Sucesso',
      fracasso: 'Sem sucesso',
      inexistente: 'Sem contato anterior',
    };
    return labels[outcome] ?? outcome;
  }

  protected statusColor(item: Opportunity): FluentBadgeColor {
    if (item.doNotContact) return 'danger';
    return item.contactAuthorized ? 'success' : 'warning';
  }

  protected statusLabel(item: Opportunity): string {
    if (item.doNotContact) return 'Não contatar';
    return item.contactAuthorized ? 'Autorizada' : 'Sem autorização';
  }

  protected formatDate(value: string): string {
    return new Intl.DateTimeFormat('pt-BR', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(new Date(value));
  }

  protected formatNumber(value: number | null, digits = 1): string {
    if (value === null) return 'Não disponível';
    return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: digits }).format(value);
  }

  private recordedFeedbackView(
    source: string,
    reward: number | null,
    learningApplied: boolean,
    reason: string,
    observedAt: string | null,
  ): DecisionFeedbackView {
    const simulated = source === 'HISTORICAL';
    const converted = reward === 1;
    const outcome = converted ? 'Converteu' : 'Não converteu';
    const sourceLabel = simulated ? 'Simulado' : 'Operador';
    const historyDetail = simulated
      ? 'Resultado histórico usado na simulação'
      : 'Feedback fornecido pelo operador';

    return {
      kind: 'recorded',
      terminal: true,
      title: simulated
        ? `Simulação histórica: ${outcome.toLocaleLowerCase('pt-BR')}`
        : converted
          ? 'Conversão registrada'
          : 'Contato sem conversão registrado',
      historyLabel: `${sourceLabel} · ${outcome}`,
      historyDetail: observedAt
        ? `${historyDetail} · ${this.formatDate(observedAt)}`
        : historyDetail,
      description: learningApplied
        ? 'Registrado e usado para atualizar a política adaptativa.'
        : 'Registrado para auditoria; a política ativa não foi atualizada.',
      reason,
      badgeColor: converted ? 'success' : 'danger',
      icon: converted ? 'success' : 'error',
    };
  }

  private loadPage(preserveSelection = false): void {
    this.pageRequest?.unsubscribe();
    this.pageLoading.set(true);
    this.pageError.set('');
    this.pageRequest = this.api
      .getOpportunities(this.search(), this.currentPage())
      .pipe(finalize(() => this.pageLoading.set(false)))
      .subscribe({
        next: (page) => {
          this.pageData.set(page);
          const selectedId = preserveSelection ? this.selected()?.id : null;
          const matching = page.content.find((item) => item.id === selectedId);
          if (matching) {
            this.selectImmediately(matching);
            this.loadDetail(matching.id);
          } else if (page.content.length > 0) {
            this.selectImmediately(page.content[0]);
            this.loadDetail(page.content[0].id);
          } else {
            this.selected.set(null);
            this.selectedId.set(null);
            this.recommendations.set([]);
          }
        },
        error: (error) => {
          this.pageError.set(readableApiError(error));
          this.pageData.set(null);
        },
      });
  }

  private loadDetail(id: number): void {
    this.detailRequest?.unsubscribe();
    this.detailLoading.set(true);
    this.detailError.set('');
    this.feedbackConfirmation.set(null);
    this.detailRequest = forkJoin({
      opportunity: this.api.getOpportunity(id),
      recommendations: this.api.getRecommendations(id),
    })
      .pipe(finalize(() => this.detailLoading.set(false)))
      .subscribe({
        next: ({ opportunity, recommendations }) => {
          if (this.selectedId() !== id) return;
          this.selected.set(opportunity);
          this.recommendations.set(recommendations);
          this.feedbackResults.set({});
          this.syncDraft(opportunity);
        },
        error: (error) => {
          if (this.selectedId() === id) this.detailError.set(readableApiError(error));
        },
      });
  }

  private selectImmediately(item: Opportunity): void {
    this.selectedId.set(item.id);
    this.selected.set(item);
    this.recommendations.set([]);
    this.feedbackResults.set({});
    this.syncDraft(item);
  }

  private syncDraft(item: Opportunity): void {
    this.draftAuthorized.set(item.contactAuthorized);
    this.draftDoNotContact.set(item.doNotContact);
    this.draftCellphone.set(item.eligibleChannels.includes('celular'));
    this.draftLandline.set(item.eligibleChannels.includes('telefone'));
  }

  private replaceOpportunity(updated: Opportunity): void {
    const page = this.pageData();
    if (!page) return;
    this.pageData.set({
      ...page,
      content: page.content.map((item) => (item.id === updated.id ? updated : item)),
    });
  }

  private storeFeedback(result: FeedbackResult): void {
    this.feedbackResults.update((results) => ({
      ...results,
      [result.recommendationId]: result,
    }));
  }

  private showMessage(kind: LiveMessage['kind'], text: string): void {
    this.liveMessage.set({ kind, text });
  }

  private rememberFeedbackTrigger(event: MouseEvent): void {
    this.feedbackTrigger =
      event.currentTarget instanceof HTMLElement ? event.currentTarget : undefined;
  }

  private focusFeedbackConfirmation(): void {
    setTimeout(() => this.document.getElementById('feedback-confirmation')?.focus());
  }

  private scrollToDetailOnCompactLayout(): void {
    if (!isPlatformBrowser(this.platformId) || !window.matchMedia('(max-width: 1120px)').matches) {
      return;
    }
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.document.getElementById('detail-panel')?.scrollIntoView({
      behavior: reducedMotion ? 'auto' : 'smooth',
      block: 'start',
    });
  }
}
