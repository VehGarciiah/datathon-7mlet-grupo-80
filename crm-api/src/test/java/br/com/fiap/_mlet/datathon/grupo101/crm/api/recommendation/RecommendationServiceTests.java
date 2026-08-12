package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.OpportunityService;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient.FeedbackDecision;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient.FeedbackRequest;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto.FeedbackResultResponse;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto.RecommendationResponse;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class RecommendationServiceTests {

    private final OpportunityService opportunityService = mock(OpportunityService.class);
    private final RecommendationApiClient client = mock(RecommendationApiClient.class);
    private final RecommendationRepository repository = mock(RecommendationRepository.class);
    private final RecommendationService service =
            new RecommendationService(opportunityService, client, repository);

    @Test
    void shouldNotInventRewardWhenRecommendedChannelDiffersFromHistoricalChannel() {
        UUID id = UUID.randomUUID();
        StoredRecommendation recommendation = new StoredRecommendation(
                id,
                10,
                "OP-000010",
                "celular",
                "fixed-policy",
                "1",
                "model-1",
                false,
                false,
                "decisão",
                Map.of(),
                OffsetDateTime.now(ZoneOffset.UTC),
                "telefone",
                1,
                null);
        when(repository.findById(id)).thenReturn(java.util.Optional.of(recommendation));
        when(repository.hasFeedback(id)).thenReturn(false);

        FeedbackResultResponse result = service.simulateHistorical(id);

        assertThat(result.simulationStatus()).isEqualTo("COUNTERFACTUAL_UNKNOWN");
        assertThat(result.reward()).isNull();
        assertThat(result.feedbackSent()).isFalse();
        verifyNoInteractions(client);
        verify(repository, never()).saveFeedback(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.anyInt(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any());
    }

    @Test
    void shouldSendHistoricalRewardOnlyForTheObservedChannel() {
        UUID id = UUID.randomUUID();
        StoredRecommendation recommendation = recommendation(
                id, "celular", "celular", 1);
        when(repository.findById(id)).thenReturn(java.util.Optional.of(recommendation));
        when(repository.hasFeedback(id)).thenReturn(false);
        FeedbackDecision decision = new FeedbackDecision(id, "recorded", true, "feedback aplicado");
        when(client.feedback(org.mockito.ArgumentMatchers.any())).thenReturn(decision);

        FeedbackResultResponse result = service.simulateHistorical(id);

        assertThat(result.simulationStatus()).isEqualTo("FACTUAL_OBSERVED");
        assertThat(result.reward()).isEqualTo(1);
        assertThat(result.feedbackSent()).isTrue();
        var feedbackCaptor = org.mockito.ArgumentCaptor.forClass(FeedbackRequest.class);
        verify(client).feedback(feedbackCaptor.capture());
        assertThat(feedbackCaptor.getValue().reward()).isEqualTo(1);
        verify(repository).saveFeedback(
                org.mockito.ArgumentMatchers.eq(id),
                org.mockito.ArgumentMatchers.eq(1),
                org.mockito.ArgumentMatchers.eq("HISTORICAL"),
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.eq(decision));
    }

    @Test
    void shouldExposePersistedOperatorFeedbackInRecommendationHistory() {
        UUID id = UUID.randomUUID();
        OffsetDateTime observedAt = OffsetDateTime.now(ZoneOffset.UTC).minusMinutes(2);
        OffsetDateTime receivedAt = observedAt.plusSeconds(1);
        RecommendationFeedback feedback = new RecommendationFeedback(
                0,
                "MANUAL",
                observedAt,
                receivedAt,
                false,
                "recorded",
                "Feedback registrado para auditoria.");
        StoredRecommendation recommendation = new StoredRecommendation(
                id,
                10,
                "OP-000010",
                "celular",
                "fixed-policy",
                "1",
                "model-1",
                false,
                false,
                "decisÃ£o",
                Map.of(),
                observedAt.minusMinutes(5),
                "celular",
                1,
                feedback);

        RecommendationResponse result = RecommendationResponse.from(recommendation);

        assertThat(result.feedback()).isNotNull();
        assertThat(result.feedback().reward()).isZero();
        assertThat(result.feedback().source()).isEqualTo("MANUAL");
        assertThat(result.feedback().observedAt()).isEqualTo(observedAt);
        assertThat(result.feedback().learningApplied()).isFalse();
    }

    private StoredRecommendation recommendation(
            UUID id, String recommendedChannel, String historicalChannel, int historicalReward) {
        return new StoredRecommendation(
                id,
                10,
                "OP-000010",
                recommendedChannel,
                "fixed-policy",
                "1",
                "model-1",
                false,
                false,
                "decisão",
                Map.of(),
                OffsetDateTime.now(ZoneOffset.UTC),
                historicalChannel,
                historicalReward,
                null);
    }
}
