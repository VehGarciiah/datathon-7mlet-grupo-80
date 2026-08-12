import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable, TimeoutError, timeout } from 'rxjs';
import {
  ActivateRuntimeConfiguration,
  ApiProblem,
  EligibilityUpdate,
  FeedbackResult,
  Opportunity,
  PageResponse,
  Recommendation,
  RuntimeConfiguration,
} from '../models/crm.models';

@Injectable({ providedIn: 'root' })
export class CrmApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api/v1';
  private readonly requestTimeoutMilliseconds = 12_000;

  getHealth(): Observable<{ status: string }> {
    return this.bounded(this.http.get<{ status: string }>('/actuator/health/readiness'));
  }

  getOpportunities(search: string, page: number, size = 20): Observable<PageResponse<Opportunity>> {
    const params = new HttpParams()
      .set('search', search.trim())
      .set('page', page)
      .set('size', size);
    return this.bounded(
      this.http.get<PageResponse<Opportunity>>(`${this.baseUrl}/opportunities`, { params }),
    );
  }

  getOpportunity(id: number): Observable<Opportunity> {
    return this.bounded(this.http.get<Opportunity>(`${this.baseUrl}/opportunities/${id}`));
  }

  updateEligibility(id: number, update: EligibilityUpdate): Observable<Opportunity> {
    return this.bounded(
      this.http.patch<Opportunity>(`${this.baseUrl}/opportunities/${id}/eligibility`, update),
    );
  }

  getRecommendations(opportunityId: number): Observable<Recommendation[]> {
    return this.bounded(
      this.http.get<Recommendation[]>(
        `${this.baseUrl}/opportunities/${opportunityId}/recommendations`,
      ),
    );
  }

  createRecommendation(opportunityId: number): Observable<Recommendation> {
    return this.bounded(
      this.http.post<Recommendation>(
        `${this.baseUrl}/opportunities/${opportunityId}/recommendations`,
        null,
      ),
    );
  }

  sendFeedback(recommendationId: string, reward: 0 | 1): Observable<FeedbackResult> {
    return this.bounded(
      this.http.post<FeedbackResult>(
        `${this.baseUrl}/recommendations/${recommendationId}/feedback`,
        { reward, observedAt: new Date().toISOString() },
      ),
    );
  }

  simulateHistorical(recommendationId: string): Observable<FeedbackResult> {
    return this.bounded(
      this.http.post<FeedbackResult>(
        `${this.baseUrl}/recommendations/${recommendationId}/simulate-historical`,
        null,
      ),
    );
  }

  getActiveConfiguration(): Observable<RuntimeConfiguration> {
    return this.bounded(
      this.http.get<RuntimeConfiguration>(`${this.baseUrl}/configurations/active`),
    );
  }

  activateConfiguration(
    configuration: ActivateRuntimeConfiguration,
  ): Observable<RuntimeConfiguration> {
    return this.bounded(
      this.http.post<RuntimeConfiguration>(
        `${this.baseUrl}/configurations/activate`,
        configuration,
      ),
    );
  }

  private bounded<T>(request: Observable<T>): Observable<T> {
    return request.pipe(timeout({ first: this.requestTimeoutMilliseconds }));
  }
}

export function readableApiError(error: unknown): string {
  if (error instanceof TimeoutError) {
    return 'O CRM demorou mais que o esperado para responder. Tente novamente.';
  }
  if (error instanceof HttpErrorResponse) {
    const problem = error.error as ApiProblem | string | null;
    if (typeof problem === 'string' && problem.trim()) {
      return problem;
    }
    if (problem && typeof problem === 'object') {
      return (
        problem.detail ?? problem.message ?? problem.title ?? 'A operação não pôde ser concluída.'
      );
    }
    if (error.status === 0) {
      return 'Não foi possível conectar ao CRM. Confirme se os containers estão online.';
    }
  }
  return 'Ocorreu um erro inesperado. Tente novamente.';
}
