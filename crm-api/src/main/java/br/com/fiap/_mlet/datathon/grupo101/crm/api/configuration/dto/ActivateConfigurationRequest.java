package br.com.fiap._mlet.datathon.grupo101.crm.api.configuration.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ActivateConfigurationRequest(
        @NotNull @Min(1) Long expectedVersion,
        @NotBlank @Size(max = 100) String operator,
        @NotBlank @Size(min = 10, max = 500) String reason,
        @NotBlank
        @Pattern(regexp = "approved|approved_adaptive|adaptive_demo")
        String policyMode,
        @NotNull Boolean killSwitch,
        @NotNull @Min(0) @Max(100) Integer adaptiveTrafficPercentage,
        @NotNull @Size(max = 100) String experimentName,
        @NotNull Boolean deterministicAllocation,
        @NotNull Boolean learningEnabled,
        @NotNull @Min(1) @Max(30) Integer attributionWindowDays,
        @NotNull Boolean structuredLogs,
        @NotNull Boolean decisionMetrics,
        @NotNull Boolean feedbackMetrics,
        @NotNull Boolean configurationAudit,
        @NotNull @Min(0) @Max(100) Integer traceSamplingPercentage) {
}
