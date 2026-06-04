package org.example.gatewaydemo.ratelimit;

import org.springframework.web.server.ServerWebExchange;

import java.util.UUID;

public final class ObservabilitySupport {

    public static final String REQUEST_ID_ATTR = "observability.request_id";
    public static final String REQUEST_ID_HEADER = "X-Request-Id";

    private ObservabilitySupport() {
    }

    public static String resolveRequestId(ServerWebExchange exchange) {
        Object stored = exchange.getAttribute(REQUEST_ID_ATTR);
        if (stored instanceof String storedId && !storedId.isBlank()) {
            return storedId;
        }
        String header = exchange.getRequest().getHeaders().getFirst(REQUEST_ID_HEADER);
        if (header != null && !header.isBlank()) {
            return header.trim();
        }
        return UUID.randomUUID().toString();
    }

    public static String tenantId(ServerWebExchange exchange) {
        return TenantResolver.resolve(exchange);
    }
}
