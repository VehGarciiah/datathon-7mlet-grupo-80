package br.com.fiap._mlet.datathon.grupo101.crm.api.shared.error;

public class ResourceNotFoundException extends RuntimeException {

    public ResourceNotFoundException(String message) {
        super(message);
    }
}
