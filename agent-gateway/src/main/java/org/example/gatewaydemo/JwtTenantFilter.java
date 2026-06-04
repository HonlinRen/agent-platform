package org.example.gatewaydemo;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.example.gatewaydemo.ratelimit.AdminPathSupport;
import org.example.gatewaydemo.ratelimit.JwtProperties;
import org.example.gatewaydemo.ratelimit.JwtValidator;
import org.example.gatewaydemo.ratelimit.ObservabilitySupport;
import org.example.gatewaydemo.ratelimit.RateLimitOrders;
import org.example.gatewaydemo.ratelimit.RateLimitResponseWriter;
import org.example.gatewaydemo.ratelimit.TenantResolver;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * 可选 JWT 租户绑定：Bearer JWT 的 sub 必须与 X-Tenant-Id 一致。
 * 未携带 JWT 时保持向后兼容（仅使用 X-Tenant-Id）。
 */
@Component
public class JwtTenantFilter implements GlobalFilter, Ordered {

    private final JwtProperties jwtProperties;
    private final Tracer tracer;

    public JwtTenantFilter(JwtProperties jwtProperties, Tracer tracer) {
        this.jwtProperties = jwtProperties;
        this.tracer = tracer;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        if (!jwtProperties.isEnabled() || AdminPathSupport.skipRateLimit(exchange)) {
            return chain.filter(exchange);
        }

        String auth = exchange.getRequest().getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
        if (auth == null || !auth.startsWith("Bearer ")) {
            return chain.filter(exchange);
        }

        String token = auth.substring("Bearer ".length()).trim();
        String tenantId = TenantResolver.resolve(exchange);
        Span span = tracer.nextSpan().name("gateway.jwt")
                .tag("tenant.id", tenantId)
                .tag("http.request_id", ObservabilitySupport.resolveRequestId(exchange))
                .start();

        try {
            String subject = JwtValidator.extractSubject(token, jwtProperties.getSecret());
            if (!tenantId.equals(subject)) {
                return RateLimitResponseWriter.forbidden(exchange, "JWT sub 与 X-Tenant-Id 不一致")
                        .doFinally(st -> span.end());
            }
        } catch (IllegalArgumentException ex) {
            return RateLimitResponseWriter.forbidden(exchange, "JWT 无效: " + ex.getMessage())
                    .doFinally(st -> span.end());
        }
        return chain.filter(exchange).doFinally(st -> span.end());
    }

    @Override
    public int getOrder() {
        return RateLimitOrders.JWT_TENANT;
    }
}
