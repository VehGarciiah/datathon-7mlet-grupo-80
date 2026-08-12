package br.com.fiap._mlet.datathon.grupo101.crm.api.shared.error;

public class BusinessRuleException extends RuntimeException {

    public BusinessRuleException(String message) {
        super(message);
    }
}
