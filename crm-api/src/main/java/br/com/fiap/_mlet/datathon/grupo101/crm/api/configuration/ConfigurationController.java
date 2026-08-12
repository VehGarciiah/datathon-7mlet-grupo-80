package br.com.fiap._mlet.datathon.grupo101.crm.api.configuration;

import br.com.fiap._mlet.datathon.grupo101.crm.api.configuration.dto.ActivateConfigurationRequest;
import br.com.fiap._mlet.datathon.grupo101.crm.api.configuration.dto.ConfigurationResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@Tag(name = "Configurações", description = "Control plane versionado do motor de recomendações")
public class ConfigurationController {

    private final ConfigurationService service;
    private final ConfigurationRepository repository;
    private final FlagdConfigurationFactory flagdFactory;

    public ConfigurationController(
            ConfigurationService service,
            ConfigurationRepository repository,
            FlagdConfigurationFactory flagdFactory) {
        this.service = service;
        this.repository = repository;
        this.flagdFactory = flagdFactory;
    }

    @GetMapping("/api/v1/configurations/active")
    @Operation(summary = "Consulta a configuração ativa")
    public ConfigurationResponse active() {
        return service.active();
    }

    @GetMapping("/api/v1/configurations/history")
    @Operation(summary = "Consulta o histórico imutável de ativações")
    public List<ConfigurationResponse> history(
            @RequestParam(defaultValue = "10") @Min(1) @Max(50) int limit) {
        return service.history(limit);
    }

    @PostMapping("/api/v1/configurations/activate")
    @Operation(summary = "Ativa uma nova versão e a publica ao flagd")
    public ConfigurationResponse activate(@Valid @RequestBody ActivateConfigurationRequest request) {
        return service.activate(request);
    }

    @GetMapping("/internal/openfeature/flags.json")
    public ResponseEntity<Map<String, Object>> flagdSource(
            @RequestHeader(value = HttpHeaders.IF_NONE_MATCH, required = false) String ifNoneMatch) {
        RuntimeConfiguration configuration = repository.findActive();
        String etag = "\"crm-runtime-" + configuration.version() + "\"";
        if (etag.equals(ifNoneMatch)) {
            return ResponseEntity.status(HttpStatus.NOT_MODIFIED).eTag(etag).build();
        }
        return ResponseEntity.ok()
                .eTag(etag)
                .header(HttpHeaders.CACHE_CONTROL, "no-cache")
                .body(flagdFactory.create(configuration));
    }
}
