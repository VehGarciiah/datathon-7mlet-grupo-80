package br.com.fiap._mlet.datathon.grupo101.crm.api.shared.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    OpenAPI crmOpenApi() {
        return new OpenAPI().info(new Info()
                .title("CRM Simulator API")
                .version("v1")
                .description("Simula um CRM real consumindo o motor de recomendações do Datathon. "
                        + "Os atributos históricos de auditoria nunca são enviados ao modelo.")
                .contact(new Contact().name("FIAP 7MLET - Grupo 101"))
                .license(new License().name("Uso acadêmico")));
    }
}
