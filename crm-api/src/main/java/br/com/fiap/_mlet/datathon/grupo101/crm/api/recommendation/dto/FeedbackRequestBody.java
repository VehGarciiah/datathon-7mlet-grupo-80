package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.OffsetDateTime;

public record FeedbackRequestBody(
        @Min(0) @Max(1) int reward,
        @NotNull OffsetDateTime observedAt
) {
}
