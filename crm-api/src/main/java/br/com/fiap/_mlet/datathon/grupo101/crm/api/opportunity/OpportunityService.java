package br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity;

import br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.dto.EligibilityUpdateRequest;
import br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.dto.OpportunityResponse;
import br.com.fiap._mlet.datathon.grupo101.crm.api.shared.error.BusinessRuleException;
import br.com.fiap._mlet.datathon.grupo101.crm.api.shared.error.ResourceNotFoundException;
import br.com.fiap._mlet.datathon.grupo101.crm.api.shared.web.PageResponse;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OpportunityService {

    private static final Set<String> SUPPORTED_CHANNELS = Set.of("celular", "telefone");

    private final OpportunityRepository repository;

    public OpportunityService(OpportunityRepository repository) {
        this.repository = repository;
    }

    public PageResponse<OpportunityResponse> findAll(String search, int page, int size) {
        List<OpportunityResponse> content = repository.findPage(search, size, page * size)
                .stream().map(OpportunityResponse::from).toList();
        return PageResponse.of(content, page, size, repository.count(search));
    }

    public OpportunityResponse findById(long id) {
        return OpportunityResponse.from(getRequired(id));
    }

    public Opportunity getRequired(long id) {
        return repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Oportunidade %d não encontrada.".formatted(id)));
    }

    @Transactional
    public OpportunityResponse updateEligibility(long id, EligibilityUpdateRequest request) {
        getRequired(id);
        List<String> channels = List.copyOf(new LinkedHashSet<>(request.eligibleChannels()));
        if (channels.isEmpty() || !SUPPORTED_CHANNELS.containsAll(channels)) {
            throw new BusinessRuleException("Informe pelo menos um canal suportado: celular ou telefone.");
        }
        if (request.doNotContact() && request.contactAuthorized()) {
            throw new BusinessRuleException("Uma oportunidade marcada como não contatar não pode estar autorizada.");
        }
        repository.updateEligibility(id, request.contactAuthorized(), request.doNotContact(), channels);
        return findById(id);
    }
}
