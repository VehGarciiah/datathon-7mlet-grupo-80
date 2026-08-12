package br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.seed;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.core.io.Resource;

@ConfigurationProperties("crm.seed")
public record OpportunitySeedProperties(boolean enabled, Resource csvLocation) {
}
