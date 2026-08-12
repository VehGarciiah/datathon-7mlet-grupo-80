package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation;

import br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.Opportunity;
import br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.OpportunityService;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient.Context;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient.FeedbackDecision;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient.FeedbackRequest;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient.RecommendationDecision;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient.RecommendationRequest;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto.FeedbackRequestBody;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto.FeedbackResultResponse;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto.RecommendationResponse;
import br.com.fiap._mlet.datathon.grupo101.crm.api.shared.error.BusinessRuleException;
import br.com.fiap._mlet.datathon.grupo101.crm.api.shared.error.ResourceNotFoundException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class RecommendationService {

    private final OpportunityService opportunityService;
    private final RecommendationApiClient client;
    private final RecommendationRepository repository;

    public RecommendationService(
            OpportunityService opportunityService,
            RecommendationApiClient client,
            RecommendationRepository repository) {
        this.opportunityService = opportunityService;
        this.client = client;
        this.repository = repository;
    }

    public RecommendationResponse create(long opportunityId) {
        Opportunity opportunity = opportunityService.getRequired(opportunityId);
        validateEligibility(opportunity);

        RecommendationDecision decision = client.recommend(toRequest(opportunity));
        if (!opportunity.eligibleChannels().contains(decision.recommendedAction())) {
            throw new BusinessRuleException("O motor retornou um canal que não está elegível para a oportunidade.");
        }
        repository.save(opportunity.id(), decision);
        return RecommendationResponse.from(required(decision.recommendationId()));
    }

    public RecommendationResponse findById(UUID id) {
        return RecommendationResponse.from(required(id));
    }

    public List<RecommendationResponse> findByOpportunity(long opportunityId) {
        opportunityService.getRequired(opportunityId);
        return repository.findByOpportunityId(opportunityId).stream()
                .map(RecommendationResponse::from)
                .toList();
    }

    public FeedbackResultResponse recordManualFeedback(UUID id, FeedbackRequestBody request) {
        StoredRecommendation recommendation = required(id);
        if (repository.hasFeedback(id)) {
            throw new BusinessRuleException("Esta recomendação já possui feedback terminal.");
        }
        FeedbackDecision decision = client.feedback(
                new FeedbackRequest(id, request.reward(), request.observedAt()));
        repository.saveFeedback(id, request.reward(), "MANUAL", request.observedAt(), decision);
        return FeedbackResultResponse.recorded(
                recommendation, request.reward(), "MANUAL", decision);
    }

    public FeedbackResultResponse simulateHistorical(UUID id) {
        StoredRecommendation recommendation = required(id);
        if (repository.hasFeedback(id)) {
            throw new BusinessRuleException("Esta recomendação já possui feedback terminal.");
        }
        if (!recommendation.recommendedChannel().equals(recommendation.historicalChannel())) {
            return FeedbackResultResponse.counterfactualUnknown(recommendation);
        }

        OffsetDateTime observedAt = OffsetDateTime.now(ZoneOffset.UTC);
        FeedbackDecision decision = client.feedback(
                new FeedbackRequest(id, recommendation.historicalReward(), observedAt));
        repository.saveFeedback(
                id,
                recommendation.historicalReward(),
                "HISTORICAL",
                observedAt,
                decision);
        return FeedbackResultResponse.recorded(
                recommendation, recommendation.historicalReward(), "HISTORICAL", decision);
    }

    private void validateEligibility(Opportunity opportunity) {
        if (!opportunity.contactAuthorized()) {
            throw new BusinessRuleException("A oportunidade não possui autorização de contato.");
        }
        if (opportunity.doNotContact()) {
            throw new BusinessRuleException("A oportunidade está marcada como não contatar.");
        }
        if (opportunity.eligibleChannels().isEmpty()) {
            throw new BusinessRuleException("A oportunidade não possui canais elegíveis.");
        }
    }

    private RecommendationRequest toRequest(Opportunity opportunity) {
        Context context = new Context(
                opportunity.month(),
                opportunity.weekday(),
                opportunity.previousOutcome(),
                opportunity.daysSincePreviousContact(),
                opportunity.previousCampaignContacts(),
                opportunity.currentCampaignPreviousAttempts(),
                opportunity.employmentVariationRate(),
                opportunity.consumerPriceIndex(),
                opportunity.consumerConfidenceIndex(),
                opportunity.euribor3Months(),
                opportunity.employedCount(),
                opportunity.neverContactedBefore() ? 1 : 0);
        return new RecommendationRequest(
                context,
                opportunity.eligibleChannels(),
                opportunity.contactAuthorized(),
                opportunity.doNotContact(),
                opportunity.externalId());
    }

    private StoredRecommendation required(UUID id) {
        return repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Recomendação %s não encontrada.".formatted(id)));
    }
}
