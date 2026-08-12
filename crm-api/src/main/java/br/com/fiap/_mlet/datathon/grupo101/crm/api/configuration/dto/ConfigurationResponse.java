package br.com.fiap._mlet.datathon.grupo101.crm.api.configuration.dto;

import br.com.fiap._mlet.datathon.grupo101.crm.api.configuration.RuntimeConfiguration;
import java.time.OffsetDateTime;

public record ConfigurationResponse(
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
        OffsetDateTime activatedAt,
        String provider,
        int expectedPropagationSeconds) {

    public static ConfigurationResponse from(RuntimeConfiguration configuration) {
        return new ConfigurationResponse(
                configuration.version(),
                configuration.policyMode(),
                configuration.killSwitch(),
                configuration.adaptiveTrafficPercentage(),
                configuration.experimentName(),
                configuration.deterministicAllocation(),
                configuration.learningEnabled(),
                configuration.attributionWindowDays(),
                configuration.structuredLogs(),
                configuration.decisionMetrics(),
                configuration.feedbackMetrics(),
                configuration.configurationAudit(),
                configuration.traceSamplingPercentage(),
                configuration.activatedBy(),
                configuration.activationReason(),
                configuration.activatedAt(),
                "OpenFeature + flagd",
                2);
    }
}
