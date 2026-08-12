package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto;

import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.StoredRecommendation;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient.FeedbackDecision;
import java.util.UUID;

public record FeedbackResultResponse(
        UUID recommendationId,
        String simulationStatus,
        Integer reward,
        String source,
        boolean feedbackSent,
        boolean learningApplied,
        String reason
) {
    public static FeedbackResultResponse counterfactualUnknown(StoredRecommendation recommendation) {
        return new FeedbackResultResponse(
                recommendation.id(),
                "COUNTERFACTUAL_UNKNOWN",
                null,
                null,
                false,
                false,
                "O canal recomendado difere do canal histórico; não existe reward factual observável.");
    }

    public static FeedbackResultResponse recorded(
            StoredRecommendation recommendation,
            int reward,
            String source,
            FeedbackDecision decision) {
        return new FeedbackResultResponse(
                recommendation.id(),
                "FACTUAL_OBSERVED",
                reward,
                source,
                true,
                decision.learningApplied(),
                decision.reason());
    }
}
