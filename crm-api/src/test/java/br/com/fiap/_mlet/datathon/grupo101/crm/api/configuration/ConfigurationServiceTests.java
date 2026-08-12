package br.com.fiap._mlet.datathon.grupo101.crm.api.configuration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import br.com.fiap._mlet.datathon.grupo101.crm.api.configuration.dto.ActivateConfigurationRequest;
import br.com.fiap._mlet.datathon.grupo101.crm.api.shared.error.BusinessRuleException;
import java.time.OffsetDateTime;
import org.junit.jupiter.api.Test;

class ConfigurationServiceTests {

    private final ConfigurationRepository repository = mock(ConfigurationRepository.class);
    private final ConfigurationService service = new ConfigurationService(repository);

    @Test
    void shouldActivateTheNextVersionAfterLockingTheControlPlane() {
        RuntimeConfiguration active = configuration(4, "approved", 0, false);
        ActivateConfigurationRequest request = adaptiveRequest(4L);
        RuntimeConfiguration activated = configuration(5, "adaptive_demo", 25, true);
        when(repository.findActive()).thenReturn(active);
        when(repository.insert(5, request)).thenReturn(activated);

        var response = service.activate(request);

        verify(repository).acquireActivationLock();
        verify(repository).insert(5, request);
        assertThat(response.version()).isEqualTo(5);
        assertThat(response.provider()).isEqualTo("OpenFeature + flagd");
    }

    @Test
    void shouldRejectAStaleDraftWithoutOverwritingTheActiveVersion() {
        when(repository.findActive()).thenReturn(configuration(8, "approved", 0, false));

        assertThatThrownBy(() -> service.activate(adaptiveRequest(7L)))
                .isInstanceOf(BusinessRuleException.class)
                .hasMessageContaining("versão 8");
    }

    @Test
    void shouldRejectLearningOnTheFixedBaseline() {
        ActivateConfigurationRequest invalid = new ActivateConfigurationRequest(
                1L,
                "Operador",
                "Motivo suficientemente descritivo",
                "approved",
                false,
                0,
                "",
                true,
                true,
                7,
                true,
                true,
                true,
                true,
                10);

        assertThatThrownBy(() -> service.activate(invalid))
                .isInstanceOf(BusinessRuleException.class)
                .hasMessageContaining("aprendizado desligado");
    }

    private ActivateConfigurationRequest adaptiveRequest(long expectedVersion) {
        return new ActivateConfigurationRequest(
                expectedVersion,
                "Jean Bezerra",
                "Demonstração do rollout adaptativo",
                "adaptive_demo",
                false,
                25,
                "demo-openfeature",
                true,
                true,
                7,
                true,
                true,
                true,
                true,
                10);
    }

    private RuntimeConfiguration configuration(
            long version, String policyMode, int traffic, boolean learning) {
        return new RuntimeConfiguration(
                version,
                policyMode,
                false,
                traffic,
                traffic > 0 ? "demo-openfeature" : "",
                true,
                learning,
                7,
                true,
                true,
                true,
                true,
                10,
                "system",
                "Configuração de teste",
                OffsetDateTime.now());
    }
}
