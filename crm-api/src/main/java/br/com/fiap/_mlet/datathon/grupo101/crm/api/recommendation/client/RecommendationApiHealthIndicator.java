package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client;

import java.util.Map;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component("recommendationApi")
public class RecommendationApiHealthIndicator implements HealthIndicator {

    private final RestClient restClient;

    public RecommendationApiHealthIndicator(RestClient recommendationRestClient) {
        this.restClient = recommendationRestClient;
    }

    @Override
    public Health health() {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> readiness = restClient.get()
                    .uri("/ready")
                    .retrieve()
                    .body(Map.class);
            if (readiness != null && "ready".equals(readiness.get("status"))) {
                return Health.up()
                        .withDetail("policyId", readiness.get("active_policy_id"))
                        .withDetail("policyVersion", readiness.get("active_policy_version"))
                        .withDetail("modelVersion", readiness.get("model_version"))
                        .build();
            }
            return Health.down().withDetail("reason", "Motor ainda não está pronto.").build();
        } catch (Exception exception) {
            return Health.down()
                    .withDetail("reason", "Motor de recomendações indisponível.")
                    .build();
        }
    }
}
