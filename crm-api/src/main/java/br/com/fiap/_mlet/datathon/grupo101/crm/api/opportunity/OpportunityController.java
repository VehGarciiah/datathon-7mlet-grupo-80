package br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity;

import br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.dto.EligibilityUpdateRequest;
import br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.dto.OpportunityResponse;
import br.com.fiap._mlet.datathon.grupo101.crm.api.shared.web.PageResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/opportunities")
@Tag(name = "Oportunidades", description = "Oportunidades de contato importadas da base histórica")
public class OpportunityController {

    private final OpportunityService service;

    public OpportunityController(OpportunityService service) {
        this.service = service;
    }

    @GetMapping
    @Operation(summary = "Lista oportunidades sem revelar o desfecho histórico")
    public PageResponse<OpportunityResponse> findAll(
            @RequestParam(defaultValue = "") String search,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return service.findAll(search, page, size);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Consulta uma oportunidade")
    public OpportunityResponse findById(@PathVariable @Min(1) long id) {
        return service.findById(id);
    }

    @PatchMapping("/{id}/eligibility")
    @Operation(summary = "Altera autorização e canais elegíveis antes da recomendação")
    public OpportunityResponse updateEligibility(
            @PathVariable @Min(1) long id,
            @Valid @RequestBody EligibilityUpdateRequest request) {
        return service.updateEligibility(id, request);
    }
}
