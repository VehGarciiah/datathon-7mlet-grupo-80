package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto;

import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.StoredRecommendation;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

public record RecommendationResponse(
        UUID id,
        long opportunityId,
        String opportunityExternalId,
        String recommendedChannel,
        String policyId,
        String policyVersion,
        String modelVersion,
        boolean exploration,
        boolean usedFallback,
        boolean causalClaim,
        String reason,
        Map<String, Object> evidence,
        OffsetDateTime createdAt,
        RecommendationFeedbackResponse feedback
) {
    public static RecommendationResponse from(StoredRecommendation value) {
        return new RecommendationResponse(
                value.id(),
                value.opportunityId(),
                value.opportunityExternalId(),
                value.recommendedChannel(),
                value.policyId(),
                value.policyVersion(),
                value.modelVersion(),
                value.exploration(),
                value.usedFallback(),
                false,
                value.reason(),
                value.evidence(),
                value.createdAt(),
                RecommendationFeedbackResponse.from(value.feedback()));
    }
}
