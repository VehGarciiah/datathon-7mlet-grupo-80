package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client;

import br.com.fiap._mlet.datathon.grupo101.crm.api.shared.error.UpstreamServiceException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Component
public class RecommendationApiClient {

    private final RestClient restClient;

    public RecommendationApiClient(RestClient recommendationRestClient) {
        this.restClient = recommendationRestClient;
    }

    public RecommendationDecision recommend(RecommendationRequest request) {
        try {
            RecommendationDecision response = restClient.post()
                    .uri("/v1/recommendations")
                    .body(request)
                    .retrieve()
                    .body(RecommendationDecision.class);
            if (response == null) {
                throw new UpstreamServiceException(
                        "O motor retornou uma resposta vazia.", HttpStatus.BAD_GATEWAY, null);
            }
            return response;
        } catch (RestClientResponseException exception) {
            throw new UpstreamServiceException(
                    "O motor de recomendações rejeitou a requisição: " + exception.getResponseBodyAsString(),
                    exception.getStatusCode(),
                    exception);
        } catch (ResourceAccessException exception) {
            throw new UpstreamServiceException(
                    "O motor de recomendações está indisponível.",
                    HttpStatus.SERVICE_UNAVAILABLE,
                    exception);
        }
    }

    public FeedbackDecision feedback(FeedbackRequest request) {
        try {
            FeedbackDecision response = restClient.post()
                    .uri("/v1/feedback")
                    .body(request)
                    .retrieve()
                    .body(FeedbackDecision.class);
            if (response == null) {
                throw new UpstreamServiceException(
                        "O motor retornou uma resposta vazia ao registrar feedback.",
                        HttpStatus.BAD_GATEWAY,
                        null);
            }
            return response;
        } catch (RestClientResponseException exception) {
            throw new UpstreamServiceException(
                    "O motor de recomendações rejeitou o feedback: " + exception.getResponseBodyAsString(),
                    exception.getStatusCode(),
                    exception);
        } catch (ResourceAccessException exception) {
            throw new UpstreamServiceException(
                    "O motor de recomendações está indisponível.",
                    HttpStatus.SERVICE_UNAVAILABLE,
                    exception);
        }
    }

    public record RecommendationRequest(
            @com.fasterxml.jackson.annotation.JsonProperty("context") Context context,
            @com.fasterxml.jackson.annotation.JsonProperty("eligible_actions") List<String> eligibleActions,
            @com.fasterxml.jackson.annotation.JsonProperty("contact_authorized") boolean contactAuthorized,
            @com.fasterxml.jackson.annotation.JsonProperty("do_not_contact") boolean doNotContact,
            @com.fasterxml.jackson.annotation.JsonProperty("targeting_key") String targetingKey
    ) {
    }

    public record Context(
            @com.fasterxml.jackson.annotation.JsonProperty("mes_contato") String month,
            @com.fasterxml.jackson.annotation.JsonProperty("dia_semana") String weekday,
            @com.fasterxml.jackson.annotation.JsonProperty("resultado_campanha_anterior") String previousOutcome,
            @com.fasterxml.jackson.annotation.JsonProperty("dias_desde_ultimo_contato") Integer daysSincePreviousContact,
            @com.fasterxml.jackson.annotation.JsonProperty("contatos_campanhas_anteriores") int previousCampaignContacts,
            @com.fasterxml.jackson.annotation.JsonProperty("tentativas_anteriores_campanha_atual") int currentCampaignPreviousAttempts,
            @com.fasterxml.jackson.annotation.JsonProperty("taxa_variacao_emprego") java.math.BigDecimal employmentVariationRate,
            @com.fasterxml.jackson.annotation.JsonProperty("indice_precos_consumidor") java.math.BigDecimal consumerPriceIndex,
            @com.fasterxml.jackson.annotation.JsonProperty("indice_confianca_consumidor") java.math.BigDecimal consumerConfidenceIndex,
            @com.fasterxml.jackson.annotation.JsonProperty("euribor_3_meses") java.math.BigDecimal euribor3Months,
            @com.fasterxml.jackson.annotation.JsonProperty("numero_empregados") java.math.BigDecimal employedCount,
            @com.fasterxml.jackson.annotation.JsonProperty("nunca_contatado_anteriormente") int neverContactedBefore
    ) {
    }

    public record RecommendationDecision(
            @com.fasterxml.jackson.annotation.JsonProperty("recommendation_id") UUID recommendationId,
            @com.fasterxml.jackson.annotation.JsonProperty("recommended_action") String recommendedAction,
            @com.fasterxml.jackson.annotation.JsonProperty("policy_id") String policyId,
            @com.fasterxml.jackson.annotation.JsonProperty("policy_version") String policyVersion,
            @com.fasterxml.jackson.annotation.JsonProperty("model_version") String modelVersion,
            @com.fasterxml.jackson.annotation.JsonProperty("is_exploration") boolean exploration,
            @com.fasterxml.jackson.annotation.JsonProperty("used_fallback") boolean usedFallback,
            String reason,
            Map<String, Object> evidence,
            @com.fasterxml.jackson.annotation.JsonProperty("created_at") OffsetDateTime createdAt
    ) {
    }

    public record FeedbackRequest(
            @com.fasterxml.jackson.annotation.JsonProperty("recommendation_id") UUID recommendationId,
            int reward,
            @com.fasterxml.jackson.annotation.JsonProperty("observed_at") OffsetDateTime observedAt
    ) {
    }

    public record FeedbackDecision(
            @com.fasterxml.jackson.annotation.JsonProperty("recommendation_id") UUID recommendationId,
            String status,
            @com.fasterxml.jackson.annotation.JsonProperty("learning_applied") boolean learningApplied,
            String reason
    ) {
    }
}
