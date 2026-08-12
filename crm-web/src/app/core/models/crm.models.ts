export type ContactChannel = 'celular' | 'telefone';

export interface Opportunity {
  id: number;
  externalId: string;
  month: string;
  weekday: string;
  previousOutcome: string;
  daysSincePreviousContact: number | null;
  previousCampaignContacts: number;
  currentCampaignPreviousAttempts: number;
  employmentVariationRate: number;
  consumerPriceIndex: number;
  consumerConfidenceIndex: number;
  euribor3Months: number;
  employedCount: number;
  neverContactedBefore: boolean;
  contactAuthorized: boolean;
  doNotContact: boolean;
  eligibleChannels: ContactChannel[];
  historicalOutcomeAvailable: boolean;
  createdAt: string;
}

export interface PageResponse<T> {
  content: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}

export interface EligibilityUpdate {
  contactAuthorized: boolean;
  doNotContact: boolean;
  eligibleChannels: ContactChannel[];
}

export interface Recommendation {
  id: string;
  opportunityId: number;
  opportunityExternalId: string;
  recommendedChannel: ContactChannel;
  policyId: string;
  policyVersion: string;
  modelVersion: string;
  exploration: boolean;
  usedFallback: boolean;
  causalClaim: boolean;
  reason: string;
  evidence: Record<string, unknown>;
  createdAt: string;
  feedback: RecommendationFeedback | null;
}

export interface RecommendationFeedback {
  reward: 0 | 1;
  source: 'MANUAL' | 'HISTORICAL';
  observedAt: string;
  receivedAt: string;
  learningApplied: boolean;
  status: string;
  reason: string;
}

export interface FeedbackResult {
  recommendationId: string;
  simulationStatus: string;
  reward: number | null;
  source: string;
  feedbackSent: boolean;
  learningApplied: boolean;
  reason: string;
}

export type PolicyMode = 'approved' | 'approved_adaptive' | 'adaptive_demo';

export interface RuntimeConfiguration {
  version: number;
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
  activatedBy: string;
  activationReason: string;
  activatedAt: string;
  provider: string;
  expectedPropagationSeconds: number;
}

export interface ActivateRuntimeConfiguration {
  expectedVersion: number;
  operator: string;
  reason: string;
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

export interface ApiProblem {
  title?: string;
  detail?: string;
  message?: string;
}
