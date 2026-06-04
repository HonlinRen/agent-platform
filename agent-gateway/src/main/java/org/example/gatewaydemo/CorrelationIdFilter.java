package org.example.gatewaydemo;

import org.example.gatewaydemo.ratelimit.ObservabilitySupport;
import org.example.gatewaydemo.ratelimit.RateLimitOrders;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * 最早执行的过滤器：解析或生成 X-Request-Id，写入 exchange 并在响应头回传。
 */
@Component
public class CorrelationIdFilter implements GlobalFilter, Ordered {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String requestId = ObservabilitySupport.resolveRequestId(exchange);
        exchange.getAttributes().put(ObservabilitySupport.REQUEST_ID_ATTR, requestId);
        exchange.getResponse().beforeCommit(() -> {
            if (exchange.getResponse().getHeaders().getFirst(ObservabilitySupport.REQUEST_ID_HEADER) == null) {
                exchange.getResponse().getHeaders().set(ObservabilitySupport.REQUEST_ID_HEADER, requestId);
            }
            return Mono.empty();
        });
        return chain.filter(exchange);
    }

    @Override
    public int getOrder() {
        return RateLimitOrders.CORRELATION_ID;
    }
}
