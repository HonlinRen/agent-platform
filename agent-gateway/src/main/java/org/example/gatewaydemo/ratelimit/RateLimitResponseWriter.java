package org.example.gatewaydemo.ratelimit;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.nio.charset.StandardCharsets;

/** 限流拒绝时统一返回 429 + OpenAI 风格 JSON 错误体。 */
public final class RateLimitResponseWriter {

    private RateLimitResponseWriter() {
    }

    public static Mono<Void> tooManyRequests(ServerWebExchange exchange, String message) {
        return writeError(exchange, HttpStatus.TOO_MANY_REQUESTS, "rate_limit_exceeded", message);
    }

    public static Mono<Void> forbidden(ServerWebExchange exchange, String message) {
        return writeError(exchange, HttpStatus.FORBIDDEN, "forbidden", message);
    }

    private static Mono<Void> writeError(
            ServerWebExchange exchange,
            HttpStatus status,
            String type,
            String message) {
        exchange.getResponse().setStatusCode(status);
        exchange.getResponse().getHeaders().setContentType(MediaType.APPLICATION_JSON);
        String requestId = ObservabilitySupport.resolveRequestId(exchange);
        exchange.getResponse().getHeaders().set(ObservabilitySupport.REQUEST_ID_HEADER, requestId);
        String escapedMessage = message.replace("\"", "\\\"");
        byte[] body = ("{\"error\":{\"message\":\"" + escapedMessage
                + "\",\"type\":\"" + type
                + "\",\"request_id\":\"" + requestId + "\"}}")
                .getBytes(StandardCharsets.UTF_8);
        return exchange.getResponse().writeWith(Mono.just(exchange.getResponse().bufferFactory().wrap(body)));
    }
}
