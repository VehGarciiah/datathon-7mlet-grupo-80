package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation;

import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto.FeedbackRequestBody;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto.FeedbackResultResponse;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.dto.RecommendationResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1")
@Tag(name = "Recomendações", description = "Decisões e feedback do simulador")
public class RecommendationController {

    private final RecommendationService service;

    public RecommendationController(RecommendationService service) {
        this.service = service;
    }

    @PostMapping("/opportunities/{opportunityId}/recommendations")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Solicita uma recomendação ao motor de decisão")
    public RecommendationResponse create(@PathVariable @Min(1) long opportunityId) {
        return service.create(opportunityId);
    }

    @GetMapping("/opportunities/{opportunityId}/recommendations")
    @Operation(summary = "Lista as recomendações emitidas para a oportunidade")
    public List<RecommendationResponse> findByOpportunity(
            @PathVariable @Min(1) long opportunityId) {
        return service.findByOpportunity(opportunityId);
    }

    @GetMapping("/recommendations/{id}")
    @Operation(summary = "Consulta uma recomendação emitida")
    public RecommendationResponse findById(@PathVariable UUID id) {
        return service.findById(id);
    }

    @PostMapping("/recommendations/{id}/feedback")
    @Operation(summary = "Registra feedback manual e terminal")
    public FeedbackResultResponse feedback(
            @PathVariable UUID id,
            @Valid @RequestBody FeedbackRequestBody request) {
        return service.recordManualFeedback(id, request);
    }

    @PostMapping("/recommendations/{id}/simulate-historical")
    @Operation(
            summary = "Simula o desfecho histórico sem fabricar contrafactuais",
            description = "O reward histórico só é observado quando o canal recomendado coincide "
                    + "com o canal que foi aplicado no dado histórico.")
    public FeedbackResultResponse simulateHistorical(@PathVariable UUID id) {
        return service.simulateHistorical(id);
    }
}
