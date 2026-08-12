package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

public record StoredRecommendation(
        UUID id,
        long opportunityId,
        String opportunityExternalId,
        String recommendedChannel,
        String policyId,
        String policyVersion,
        String modelVersion,
        boolean exploration,
        boolean usedFallback,
        String reason,
        Map<String, Object> evidence,
        OffsetDateTime createdAt,
        String historicalChannel,
        int historicalReward,
        RecommendationFeedback feedback
) {
}
