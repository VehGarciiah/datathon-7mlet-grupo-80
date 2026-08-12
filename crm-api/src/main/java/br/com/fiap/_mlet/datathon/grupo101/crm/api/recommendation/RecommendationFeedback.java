package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation;

import java.time.OffsetDateTime;

public record RecommendationFeedback(
        int reward,
        String source,
        OffsetDateTime observedAt,
        OffsetDateTime receivedAt,
        boolean learningApplied,
        String upstreamStatus,
        String reason
) {
}
