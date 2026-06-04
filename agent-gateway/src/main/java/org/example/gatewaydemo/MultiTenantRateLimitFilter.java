package org.example.gatewaydemo;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.example.gatewaydemo.ratelimit.AdminPathSupport;
import org.example.gatewaydemo.ratelimit.DistributedRateLimiterService;
import org.example.gatewaydemo.ratelimit.GatewayMetricsService;
import org.example.gatewaydemo.ratelimit.ObservabilitySupport;
import org.example.gatewaydemo.ratelimit.RateLimitOrders;
import org.example.gatewaydemo.ratelimit.RateLimitResponseWriter;
import org.example.gatewaydemo.ratelimit.TenantResolver;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

/**
 * 全局过滤器 #1：多租户 RPM（Requests Per Minute）。
 * 每个请求消耗 1 个配额；超限直接 429，不转发上游。
 */
@Component
public class MultiTenantRateLimitFilter implements GlobalFilter, Ordered {

    private final DistributedRateLimiterService rateLimiter;
    private final GatewayMetricsService metricsService;
    private final Tracer tracer;

    public MultiTenantRateLimitFilter(DistributedRateLimiterService rateLimiter,
                                      GatewayMetricsService metricsService,
                                      Tracer tracer) {
        this.rateLimiter = rateLimiter;
        this.metricsService = metricsService;
        this.tracer = tracer;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        if (AdminPathSupport.skipRateLimit(exchange)) {
            return chain.filter(exchange);
        }

        String tenantId = TenantResolver.resolve(exchange);
        Span span = tracer.nextSpan().name("gateway.rate_limit.rpm")
                .tag("tenant.id", tenantId)
                .tag("http.request_id", ObservabilitySupport.resolveRequestId(exchange))
                .start();

        return Mono.fromCallable(() -> rateLimiter.tryConsumeRpm(tenantId))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(allowed -> {
                    if (allowed) {
                        metricsService.recordRpmAllowed(tenantId);
                        return chain.filter(exchange);
                    }
                    metricsService.recordRpmRejected(tenantId);
                    return RateLimitResponseWriter.tooManyRequests(
                            exchange, "RPM limit exceeded for tenant " + tenantId);
                })
                .doFinally(st -> span.end());
    }

    @Override
    public int getOrder() {
        return RateLimitOrders.RPM;
    }
}
