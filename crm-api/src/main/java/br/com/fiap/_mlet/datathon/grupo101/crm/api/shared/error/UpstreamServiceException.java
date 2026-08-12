package br.com.fiap._mlet.datathon.grupo101.crm.api.shared.error;

import org.springframework.http.HttpStatusCode;

public class UpstreamServiceException extends RuntimeException {

    private final HttpStatusCode upstreamStatus;

    public UpstreamServiceException(String message, HttpStatusCode upstreamStatus, Throwable cause) {
        super(message, cause);
        this.upstreamStatus = upstreamStatus;
    }

    public HttpStatusCode upstreamStatus() {
        return upstreamStatus;
    }
}
