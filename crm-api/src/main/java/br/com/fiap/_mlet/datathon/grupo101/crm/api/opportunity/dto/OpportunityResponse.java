package br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.dto;

import br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.Opportunity;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OpportunityResponse(
        long id,
        String externalId,
        String month,
        String weekday,
        String previousOutcome,
        Integer daysSincePreviousContact,
        int previousCampaignContacts,
        int currentCampaignPreviousAttempts,
        BigDecimal employmentVariationRate,
        BigDecimal consumerPriceIndex,
        BigDecimal consumerConfidenceIndex,
        BigDecimal euribor3Months,
        BigDecimal employedCount,
        boolean neverContactedBefore,
        boolean contactAuthorized,
        boolean doNotContact,
        List<String> eligibleChannels,
        boolean historicalOutcomeAvailable,
        Instant createdAt
) {
    public static OpportunityResponse from(Opportunity opportunity) {
        return new OpportunityResponse(
                opportunity.id(),
                opportunity.externalId(),
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
                opportunity.neverContactedBefore(),
                opportunity.contactAuthorized(),
                opportunity.doNotContact(),
                opportunity.eligibleChannels(),
                true,
                opportunity.createdAt());
    }
}
