import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const createdAt = '2026-08-10T12:00:00Z';

const opportunities = [
  {
    id: 1,
    externalId: 'OP-000003',
    month: 'mai',
    weekday: 'segunda-feira',
    previousOutcome: 'sucesso',
    daysSincePreviousContact: 7,
    previousCampaignContacts: 2,
    currentCampaignPreviousAttempts: 1,
    employmentVariationRate: 1.1,
    consumerPriceIndex: 93.2,
    consumerConfidenceIndex: -40.1,
    euribor3Months: 4.8,
    employedCount: 5191,
    neverContactedBefore: false,
    contactAuthorized: true,
    doNotContact: false,
    eligibleChannels: ['celular', 'telefone'],
    historicalOutcomeAvailable: true,
    createdAt,
  },
  {
    id: 2,
    externalId: 'OP-000004',
    month: 'mai',
    weekday: 'terça-feira',
    previousOutcome: 'inexistente',
    daysSincePreviousContact: null,
    previousCampaignContacts: 0,
    currentCampaignPreviousAttempts: 2,
    employmentVariationRate: 1.1,
    consumerPriceIndex: 93.2,
    consumerConfidenceIndex: -40.1,
    euribor3Months: 4.8,
    employedCount: 5191,
    neverContactedBefore: true,
    contactAuthorized: false,
    doNotContact: false,
    eligibleChannels: ['celular'],
    historicalOutcomeAvailable: false,
    createdAt,
  },
] as const;

const activeConfiguration = {
  version: 1,
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
  activatedBy: 'system',
  activationReason: 'Configuração inicial segura.',
  activatedAt: createdAt,
  provider: 'OpenFeature + flagd',
  expectedPropagationSeconds: 2,
};

test.beforeEach(async ({ page }) => {
  await page.route('**/actuator/health/readiness', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"UP"}' });
  });
  await page.route('**/api/v1/configurations/active', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(activeConfiguration),
    });
  });
  await page.route('**/api/v1/opportunities**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const recommendationMatch = url.pathname.match(
      /^\/api\/v1\/opportunities\/(\d+)\/recommendations$/,
    );
    if (recommendationMatch && request.method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      return;
    }
    const detailMatch = url.pathname.match(/^\/api\/v1\/opportunities\/(\d+)$/);
    if (detailMatch && request.method() === 'GET') {
      const opportunity = opportunities.find((item) => item.id === Number(detailMatch[1]));
      await route.fulfill({
        status: opportunity ? 200 : 404,
        contentType: 'application/json',
        body: JSON.stringify(opportunity ?? { detail: 'Oportunidade não encontrada.' }),
      });
      return;
    }
    if (url.pathname === '/api/v1/opportunities' && request.method() === 'GET') {
      const search = (url.searchParams.get('search') ?? '').toLowerCase();
      const filtered = opportunities.filter((item) =>
        item.externalId.toLowerCase().includes(search),
      );
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          content: filtered,
          page: 0,
          size: 20,
          totalElements: filtered.length,
          totalPages: filtered.length > 0 ? 1 : 0,
        }),
      });
      return;
    }
    await route.fallback();
  });
});

async function waitForQueue(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Priorize o próximo contato' })).toBeVisible();
  await expect(page.getByRole('button', { name: /OP-\d+/ }).first()).toBeVisible();
}

async function waitForSettings(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/configuracoes');
  await expect(page.getByRole('heading', { name: 'Configurações do ecossistema' })).toBeVisible();
  await expect(page.locator('fluent-dropdown#policy-mode')).toBeVisible();
  await page.waitForFunction(() => customElements.get('fluent-dropdown') !== undefined);
}

async function waitForVisualTransitions(page: import('@playwright/test').Page): Promise<void> {
  await page.evaluate(() =>
    Promise.allSettled(document.getAnimations().map((animation) => animation.finished)),
  );
}

test('carrega a fila real e permite selecionar uma oportunidade', async ({ page }) => {
  await waitForQueue(page);

  const firstOpportunity = page.getByRole('button', { name: /OP-\d+/ }).first();
  await firstOpportunity.focus();
  await page.keyboard.press('Enter');

  await expect(firstOpportunity).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('heading', { name: 'Elegibilidade de contato' })).toBeVisible();
  await expect(page.getByText('Recomendação assistida por modelo')).toBeVisible();
});

test('protege alterações de elegibilidade antes de trocar ou recomendar', async ({ page }) => {
  await waitForQueue(page);
  await expect(page.getByRole('heading', { name: 'Elegibilidade de contato' })).toBeVisible();

  await page.locator('fluent-checkbox#do-not-contact').evaluate((element) => {
    const checkbox = element as HTMLElement & { checked: boolean };
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
  });

  await expect(page.getByText('Existem alterações não salvas.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Gerar recomendação' })).toBeDisabled();

  const secondOpportunity = page.getByRole('button', { name: /OP-000004/ });
  await secondOpportunity.click();
  await expect(page.getByText(/Salve ou descarte as alterações/)).toBeVisible();
  await expect(page.getByRole('button', { name: /OP-000003/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  await page.getByRole('button', { name: 'Descartar alterações' }).click();
  await secondOpportunity.click();
  await expect(secondOpportunity).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('heading', { name: 'OP-000004' })).toBeVisible();
});

test('busca informa estado vazio e oferece limpeza imediata', async ({ page }) => {
  await waitForQueue(page);
  await page
    .locator('fluent-text-input')
    .first()
    .evaluate((element) => {
      const input = element as HTMLElement & { value: string };
      input.value = 'inexistente';
      input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
    });

  await expect(
    page.getByRole('heading', { name: 'Nenhuma oportunidade encontrada' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Limpar busca' }).first().click();
  await expect(page.getByRole('button', { name: /OP-000003/ })).toBeVisible();
});

test('gera uma recomendação e registra feedback pela interface', async ({ page }) => {
  const recommendationId = '11111111-1111-4111-8111-111111111111';

  await page.route('**/api/v1/opportunities/*/recommendations', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        id: recommendationId,
        opportunityId: 1,
        opportunityExternalId: 'OP-000003',
        recommendedChannel: 'celular',
        policyId: 'best_historical_action',
        policyVersion: '1.0.0',
        modelVersion: '1.0.0',
        exploration: false,
        usedFallback: false,
        causalClaim: false,
        reason: 'Canal com melhor evidência histórica no conjunto de treino.',
        evidence: { causal_claim: false },
        createdAt: new Date().toISOString(),
        feedback: null,
      }),
    });
  });
  await page.route(`**/api/v1/recommendations/${recommendationId}/feedback`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        recommendationId,
        simulationStatus: 'RECORDED',
        reward: 1,
        source: 'MANUAL',
        feedbackSent: true,
        learningApplied: true,
        reason: 'Feedback registrado.',
      }),
    });
  });

  await waitForQueue(page);
  await page.getByRole('button', { name: 'Gerar recomendação' }).click();
  await expect(
    page.getByText('Canal com melhor evidência histórica no conjunto de treino.'),
  ).toBeVisible();

  const convertedButton = page.getByRole('button', { name: 'Converteu', exact: true });
  await convertedButton.click();
  await expect(page.getByRole('alertdialog')).toContainText('Confirmar conversão?');
  await expect(page.getByRole('alertdialog')).toBeFocused();
  await page.getByRole('button', { name: 'Cancelar' }).click();
  await expect(convertedButton).toBeFocused();

  await convertedButton.click();
  await page.getByRole('button', { name: 'Confirmar resultado' }).click();
  await expect(page.getByText('Conversão registrada.')).toBeVisible();
  await expect(page.getByText('Operador · Converteu', { exact: true })).toBeVisible();
  await expect(
    page.getByText('Registrado e usado para atualizar a política adaptativa.'),
  ).toBeVisible();
});

test('mostra no histórico se o feedback foi do operador, simulado ou não informado', async ({
  page,
}) => {
  const recommendation = (
    id: string,
    recommendationCreatedAt: string,
    feedbackValue: Record<string, unknown> | null,
  ) => ({
    id,
    opportunityId: 1,
    opportunityExternalId: 'OP-000003',
    recommendedChannel: id.endsWith('1') ? 'celular' : 'telefone',
    policyId: 'best_historical_action',
    policyVersion: '1.0.0',
    modelVersion: '1.0.0',
    exploration: false,
    usedFallback: false,
    causalClaim: false,
    reason: 'Canal recomendado para demonstração.',
    evidence: { causal_claim: false },
    createdAt: recommendationCreatedAt,
    feedback: feedbackValue,
  });
  const feedback = (reward: 0 | 1, source: 'MANUAL' | 'HISTORICAL') => ({
    reward,
    source,
    observedAt: '2026-08-11T20:30:00Z',
    receivedAt: '2026-08-11T20:30:01Z',
    learningApplied: false,
    status: 'recorded',
    reason: 'Feedback registrado para auditoria.',
  });

  await page.route('**/api/v1/opportunities/1/recommendations', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        recommendation(
          '00000000-0000-4000-8000-000000000001',
          '2026-08-11T20:30:00Z',
          feedback(1, 'MANUAL'),
        ),
        recommendation(
          '00000000-0000-4000-8000-000000000002',
          '2026-08-11T20:29:00Z',
          feedback(0, 'MANUAL'),
        ),
        recommendation(
          '00000000-0000-4000-8000-000000000003',
          '2026-08-11T20:28:00Z',
          feedback(1, 'HISTORICAL'),
        ),
        recommendation(
          '00000000-0000-4000-8000-000000000004',
          '2026-08-11T20:27:00Z',
          feedback(0, 'HISTORICAL'),
        ),
        recommendation('00000000-0000-4000-8000-000000000005', '2026-08-11T20:26:00Z', null),
      ]),
    });
  });

  await waitForQueue(page);

  const history = page.locator('section[aria-labelledby="history-title"]');
  await expect(history.getByText('Operador · Converteu', { exact: true })).toBeVisible();
  await expect(history.getByText('Operador · Não converteu', { exact: true })).toBeVisible();
  await expect(history.getByText('Simulado · Converteu', { exact: true })).toBeVisible();
  await expect(history.getByText('Simulado · Não converteu', { exact: true })).toBeVisible();
  await expect(history.getByText('Sem feedback', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Converteu', exact: true })).toHaveCount(0);
});

test('não apresenta violações WCAG 2.2 AA detectáveis em temas claro e escuro', async ({
  page,
}) => {
  await waitForQueue(page);

  for (const themeName of ['claro', 'escuro']) {
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(accessibilityScanResults.violations, `Tema ${themeName}`).toEqual([]);

    if (themeName === 'claro') {
      await page.getByRole('button', { name: 'Ativar tema escuro' }).click();
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
      await waitForVisualTransitions(page);
    }
  }
});

test('faz reflow entre 320 e 1440 pixels sem rolagem horizontal', async ({ page }) => {
  await waitForQueue(page);

  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByRole('heading', { name: 'Priorize o próximo contato' })).toBeVisible();
    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasHorizontalOverflow, `Viewport ${width}px`).toBe(false);
  }
});

test('preserva navegação por teclado, reduced motion, forced colors e RTL', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce', forcedColors: 'active' });
  await waitForQueue(page);

  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Ir para o conteúdo principal' })).toBeFocused();

  await page.evaluate(() => document.documentElement.setAttribute('dir', 'rtl'));
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
});

test('navega para o laboratório e salva um rascunho sem alterar o runtime', async ({ page }) => {
  await waitForQueue(page);
  await page.getByRole('link', { name: 'Configurações' }).click();
  await expect(page).toHaveURL(/\/configuracoes$/);
  await expect(page.getByText('Baseline fixa de rollback')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Salvar rascunho' })).toBeDisabled();
  await page.waitForFunction(() => customElements.get('fluent-dropdown') !== undefined);

  await page.getByRole('combobox', { name: 'Modo da política' }).click();
  await page.getByRole('option', { name: /Adaptativa de demonstração/ }).click();

  await page.locator('fluent-text-input#experiment-name').evaluate((element) => {
    const control = element as HTMLElement & { value: string };
    control.value = 'demo-thompson-agosto';
    control.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
  });
  await expect(page.getByRole('button', { name: 'Salvar rascunho' })).toBeEnabled();

  await expect(page.getByText('100% do tráfego iria para a política adaptativa.')).toBeVisible();
  await page.getByRole('button', { name: 'Salvar rascunho' }).click();
  await expect(
    page.getByText('Rascunho salvo neste navegador. Nenhuma política em execução foi alterada.'),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Ativar configuração' })).toBeDisabled();

  await page.reload();
  await expect(page.locator('.review-summary dd').first()).toHaveText('Adaptativa de demonstração');
  await expect(page.getByText('Baseline fixa de rollback')).toBeVisible();
});

test('dropdown Fluent inicia e muda de valor sem erros no navegador', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });

  await waitForSettings(page);
  await page.getByRole('combobox', { name: 'Modo da política' }).click();
  await page.getByRole('option', { name: /Adaptativa de demonstração/ }).click();
  await expect(page.getByText('100% do tráfego iria para a política adaptativa.')).toBeVisible();
  expect(errors).toEqual([]);
});

test('ativa uma configuração versionada pelo control plane OpenFeature', async ({ page }) => {
  let activationPayload: Record<string, unknown> | null = null;
  await page.route('**/api/v1/configurations/active', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(activeConfiguration),
    });
  });
  await page.route('**/api/v1/configurations/activate', async (route) => {
    activationPayload = (await route.request().postDataJSON()) as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...activeConfiguration,
        ...activationPayload,
        version: 2,
        activatedBy: activationPayload['operator'],
        activationReason: activationPayload['reason'],
      }),
    });
  });

  await waitForSettings(page);
  await page.getByRole('combobox', { name: 'Modo da política' }).click();
  await page.getByRole('option', { name: /Adaptativa de demonstração/ }).click();

  for (const [selector, value] of [
    ['fluent-text-input#experiment-name', 'demo-openfeature'],
    ['fluent-text-input#activation-operator', 'Jean Bezerra'],
    ['fluent-text-input#activation-reason', 'Demonstração do rollout adaptativo'],
  ] as const) {
    await page.locator(selector).evaluate((element, inputValue) => {
      const control = element as HTMLElement & { value: string };
      control.value = inputValue;
      control.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
    }, value);
  }

  await expect(page.getByRole('button', { name: 'Ativar configuração' })).toBeEnabled();
  await page.getByRole('button', { name: 'Ativar configuração' }).click();

  await expect(page.getByText(/Configuração v2 ativada/)).toBeVisible();
  await expect(page.getByText('v2', { exact: true })).toBeVisible();
  expect(activationPayload).toMatchObject({
    expectedVersion: 1,
    policyMode: 'adaptive_demo',
    adaptiveTrafficPercentage: 100,
    operator: 'Jean Bezerra',
  });
});

test('configurações não apresentam violações WCAG detectáveis nos dois temas', async ({ page }) => {
  await waitForSettings(page);

  for (const themeName of ['claro', 'escuro']) {
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(accessibilityScanResults.violations, `Configurações · tema ${themeName}`).toEqual([]);

    if (themeName === 'claro') {
      await page.getByRole('button', { name: 'Ativar tema escuro' }).click();
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
      await waitForVisualTransitions(page);
    }
  }
});

test('configurações fazem reflow entre 320 e 1440 pixels', async ({ page }) => {
  await waitForSettings(page);

  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByRole('heading', { name: 'Configurações do ecossistema' })).toBeVisible();
    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasHorizontalOverflow, `Configurações · viewport ${width}px`).toBe(false);
  }
});

test('explica todas as configurações em linguagem simples pelo botão de ajuda', async ({
  page,
}) => {
  await waitForSettings(page);

  const helpButtons = page.getByRole('button', { name: /^Ajuda:/ });
  await expect(helpButtons).toHaveCount(28);

  await page.getByRole('button', { name: 'Ajuda: Modo da política' }).click();
  await expect(
    page.locator('fluent-tooltip').filter({
      hasText:
        'Escolhe a regra que decide o canal. A baseline repete uma estratégia estável; os modos adaptativos podem aprender com novos resultados.',
    }),
  ).toBeVisible();
});

test('atalhos laterais levam à seção correta e informam a localização atual', async ({ page }) => {
  await waitForSettings(page);

  const observabilityShortcut = page.getByRole('link', { name: 'Observabilidade' });
  await observabilityShortcut.click();

  await expect(page).toHaveURL(/\/configuracoes#observability$/);
  await expect(page.locator('#observability')).toBeFocused();
  await expect(observabilityShortcut).toHaveAttribute('aria-current', 'location');
  await expect(page.getByRole('heading', { name: 'Observabilidade' })).toBeInViewport();
});
