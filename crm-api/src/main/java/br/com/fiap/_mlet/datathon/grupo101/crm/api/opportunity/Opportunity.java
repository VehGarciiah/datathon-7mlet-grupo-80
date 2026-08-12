package br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record Opportunity(
        long id,
        String externalId,
        long sourceEventId,
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
        String historicalChannel,
        int historicalReward,
        Instant createdAt
) {
}
