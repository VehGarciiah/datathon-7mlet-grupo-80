package br.com.fiap._mlet.datathon.grupo101.crm.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CrmApiApplication {

	public static void main(String[] args) {
		SpringApplication.run(CrmApiApplication.class, args);
	}

}
