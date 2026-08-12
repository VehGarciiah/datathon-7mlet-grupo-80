package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("crm.recommendation-api")
public record RecommendationApiProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout
) {
}
