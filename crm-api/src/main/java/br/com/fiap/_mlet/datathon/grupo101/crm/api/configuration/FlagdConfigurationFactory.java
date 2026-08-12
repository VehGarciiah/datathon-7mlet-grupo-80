package br.com.fiap._mlet.datathon.grupo101.crm.api.configuration;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class FlagdConfigurationFactory {

    public Map<String, Object> create(RuntimeConfiguration configuration) {
        Map<String, Object> flags = new LinkedHashMap<>();
        flags.put("configuration-version", flag(configuration.version()));
        flags.put("policy-mode", flag(configuration.policyMode()));
        flags.put("kill-switch", flag(configuration.killSwitch()));
        flags.put("adaptive-traffic-percentage", flag(configuration.adaptiveTrafficPercentage()));
        flags.put("experiment-name", flag(configuration.experimentName()));
        flags.put("deterministic-allocation", flag(configuration.deterministicAllocation()));
        flags.put("learning-enabled", flag(configuration.learningEnabled()));
        flags.put("attribution-window-days", flag(configuration.attributionWindowDays()));
        flags.put("structured-logs", flag(configuration.structuredLogs()));
        flags.put("decision-metrics", flag(configuration.decisionMetrics()));
        flags.put("feedback-metrics", flag(configuration.feedbackMetrics()));
        flags.put("configuration-audit", flag(configuration.configurationAudit()));
        flags.put("trace-sampling-percentage", flag(configuration.traceSamplingPercentage()));

        Map<String, Object> metadata = Map.of(
                "flagSetId", "crm-runtime",
                "configurationVersion", configuration.version(),
                "activatedAt", configuration.activatedAt().toString());
        Map<String, Object> definition = new LinkedHashMap<>();
        definition.put("$schema", "https://flagd.dev/schema/v0/flags.json");
        definition.put("metadata", metadata);
        definition.put("flags", flags);
        return definition;
    }

    private Map<String, Object> flag(Object value) {
        return Map.of(
                "state", "ENABLED",
                "variants", Map.of("configured", value),
                "defaultVariant", "configured");
    }
}
