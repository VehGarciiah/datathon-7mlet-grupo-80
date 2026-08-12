package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto;

import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.RecommendationFeedback;
import java.time.OffsetDateTime;

public record RecommendationFeedbackResponse(
        int reward,
        String source,
        OffsetDateTime observedAt,
        OffsetDateTime receivedAt,
        boolean learningApplied,
        String status,
        String reason
) {
    public static RecommendationFeedbackResponse from(RecommendationFeedback value) {
        if (value == null) {
            return null;
        }
        return new RecommendationFeedbackResponse(
                value.reward(),
                value.source(),
                value.observedAt(),
                value.receivedAt(),
                value.learningApplied(),
                value.upstreamStatus(),
                value.reason());
    }
}
