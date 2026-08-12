package br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.dto;

import jakarta.validation.constraints.NotEmpty;
import java.util.List;

public record EligibilityUpdateRequest(
        boolean contactAuthorized,
        boolean doNotContact,
        @NotEmpty List<String> eligibleChannels
) {
}
