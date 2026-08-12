package br.com.fiap._mlet.datathon.grupo101.crm.api.configuration;

import br.com.fiap._mlet.datathon.grupo101.crm.api.configuration.dto.ActivateConfigurationRequest;
import br.com.fiap._mlet.datathon.grupo101.crm.api.configuration.dto.ConfigurationResponse;
import br.com.fiap._mlet.datathon.grupo101.crm.api.shared.error.BusinessRuleException;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConfigurationService {

    private final ConfigurationRepository repository;

    public ConfigurationService(ConfigurationRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public ConfigurationResponse active() {
        return ConfigurationResponse.from(repository.findActive());
    }

    @Transactional(readOnly = true)
    public List<ConfigurationResponse> history(int limit) {
        return repository.findHistory(limit).stream()
                .map(ConfigurationResponse::from)
                .toList();
    }

    @Transactional
    public ConfigurationResponse activate(ActivateConfigurationRequest request) {
        validateInvariants(request);
        repository.acquireActivationLock();
        RuntimeConfiguration active = repository.findActive();
        if (active.version() != request.expectedVersion()) {
            throw new BusinessRuleException(
                    "A configuração ativa mudou durante a revisão. Recarregue a versão "
                            + active.version() + " antes de ativar novamente.");
        }
        return ConfigurationResponse.from(repository.insert(active.version() + 1, request));
    }

    private void validateInvariants(ActivateConfigurationRequest request) {
        boolean approved = "approved".equals(request.policyMode());
        if (approved && (request.adaptiveTrafficPercentage() != 0 || request.learningEnabled())) {
            throw new BusinessRuleException(
                    "A baseline aprovada exige tráfego adaptativo zero e aprendizado desligado.");
        }
        if (!approved
                && (request.adaptiveTrafficPercentage() == 0 || request.experimentName().isBlank())) {
            throw new BusinessRuleException(
                    "Um modo adaptativo exige tráfego maior que zero e identificador de experimento.");
        }
        if (request.killSwitch()
                && (!approved || request.adaptiveTrafficPercentage() != 0 || request.learningEnabled())) {
            throw new BusinessRuleException(
                    "O kill switch exige baseline aprovada, tráfego zero e aprendizado desligado.");
        }
    }
}
