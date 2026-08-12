package br.com.fiap._mlet.datathon.grupo101.crm.api.configuration;

import java.time.OffsetDateTime;

public record RuntimeConfiguration(
        long version,
        String policyMode,
        boolean killSwitch,
        int adaptiveTrafficPercentage,
        String experimentName,
        boolean deterministicAllocation,
        boolean learningEnabled,
        int attributionWindowDays,
        boolean structuredLogs,
        boolean decisionMetrics,
        boolean feedbackMetrics,
        boolean configurationAudit,
        int traceSamplingPercentage,
        String activatedBy,
        String activationReason,
        OffsetDateTime activatedAt) {
}
