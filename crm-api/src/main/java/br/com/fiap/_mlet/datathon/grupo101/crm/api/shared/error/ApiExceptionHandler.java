package br.com.fiap._mlet.datathon.grupo101.crm.api.shared.error;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import java.net.URI;
import java.time.Instant;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ResourceNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound(ResourceNotFoundException exception, HttpServletRequest request) {
        return problem(HttpStatus.NOT_FOUND, "Recurso não encontrado", exception.getMessage(), request);
    }

    @ExceptionHandler(BusinessRuleException.class)
    ResponseEntity<ProblemDetail> conflict(BusinessRuleException exception, HttpServletRequest request) {
        return problem(HttpStatus.CONFLICT, "Regra de negócio não atendida", exception.getMessage(), request);
    }

    @ExceptionHandler({MethodArgumentNotValidException.class, ConstraintViolationException.class})
    ResponseEntity<ProblemDetail> invalidInput(Exception exception, HttpServletRequest request) {
        return problem(HttpStatus.BAD_REQUEST, "Requisição inválida", exception.getMessage(), request);
    }

    @ExceptionHandler(UpstreamServiceException.class)
    ResponseEntity<ProblemDetail> upstream(UpstreamServiceException exception, HttpServletRequest request) {
        ProblemDetail detail = createProblem(
                HttpStatus.BAD_GATEWAY,
                "Falha no motor de recomendações",
                exception.getMessage(),
                request);
        detail.setProperty("upstreamStatus", exception.upstreamStatus().value());
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(detail);
    }

    private ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String title, String detail, HttpServletRequest request) {
        return ResponseEntity.status(status).body(createProblem(status, title, detail, request));
    }

    private ProblemDetail createProblem(
            HttpStatus status, String title, String detail, HttpServletRequest request) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(status, detail);
        problem.setTitle(title);
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("timestamp", Instant.now());
        return problem;
    }
}
