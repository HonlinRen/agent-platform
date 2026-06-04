package org.example.gatewaydemo;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.example.gatewaydemo.ratelimit.AdminPathSupport;
import org.example.gatewaydemo.ratelimit.DistributedRateLimiterService;
import org.example.gatewaydemo.ratelimit.GatewayMetricsService;
import org.example.gatewaydemo.ratelimit.LlmApiSupport;
import org.example.gatewaydemo.ratelimit.ObservabilitySupport;
import org.example.gatewaydemo.ratelimit.RateLimitOrders;
import org.example.gatewaydemo.ratelimit.RateLimitProperties;
import org.example.gatewaydemo.ratelimit.RateLimitResponseWriter;
import org.example.gatewaydemo.ratelimit.TenantResolver;
import org.example.gatewaydemo.ratelimit.TokenEstimator;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpHeaders;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

/**
 * 全局过滤器 #2：TPM 输入（Tokens Per Minute，请求侧）。
 * 仅 LLM 路径：先读完整 body 估算 token，扣 Redis 配额后再用 Decorator 把 body 还给下游。
 */
@Component
public class TenantTpmInputRateLimitFilter implements GlobalFilter, Ordered {

    private final DistributedRateLimiterService rateLimiter;
    private final RateLimitProperties rateLimitProperties;
    private final GatewayMetricsService metricsService;
    private final Tracer tracer;

    public TenantTpmInputRateLimitFilter(DistributedRateLimiterService rateLimiter,
                                         RateLimitProperties rateLimitProperties,
                                         GatewayMetricsService metricsService,
                                         Tracer tracer) {
        this.rateLimiter = rateLimiter;
        this.rateLimitProperties = rateLimitProperties;
        this.metricsService = metricsService;
        this.tracer = tracer;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        if (AdminPathSupport.isAdminPath(exchange)) {
            return chain.filter(exchange);
        }

        if (!LlmApiSupport.isLlmApi(exchange, rateLimitProperties.llmPathPrefixes())) {
            return chain.filter(exchange);
        }

        String tenantId = TenantResolver.resolve(exchange);
        Span span = tracer.nextSpan().name("gateway.rate_limit.tpm_in")
                .tag("tenant.id", tenantId)
                .tag("http.request_id", ObservabilitySupport.resolveRequestId(exchange))
                .start();

        return DataBufferUtils.join(exchange.getRequest().getBody())
                .defaultIfEmpty(exchange.getResponse().bufferFactory().allocateBuffer(0))
                .flatMap(dataBuffer -> {
                    byte[] body = TokenEstimator.readBytesAndRelease(dataBuffer);
                    long inputTokens = TokenEstimator.estimateInputTokens(body);
                    return Mono.fromCallable(() -> rateLimiter.tryConsumeTpmInput(tenantId, inputTokens))
                            .subscribeOn(Schedulers.boundedElastic())
                            .flatMap(allowed -> {
                                if (!allowed) {
                                    metricsService.recordTpmInputRejected(tenantId);
                                    return RateLimitResponseWriter.tooManyRequests(
                                            exchange, "TPM input limit exceeded for tenant " + tenantId);
                                }
                                metricsService.recordTpmInputTokens(tenantId, inputTokens);
                                ServerHttpRequest decorated = new ServerHttpRequestDecorator(exchange.getRequest()) {
                                    @Override
                                    public Flux<DataBuffer> getBody() {
                                        if (body.length == 0) {
                                            return Flux.empty();
                                        }
                                        return Flux.just(exchange.getResponse().bufferFactory().wrap(body));
                                    }

                                    @Override
                                    public HttpHeaders getHeaders() {
                                        HttpHeaders headers = new HttpHeaders();
                                        headers.putAll(super.getHeaders());
                                        if (body.length > 0) {
                                            headers.setContentLength(body.length);
                                        }
                                        return headers;
                                    }
                                };
                                return chain.filter(exchange.mutate().request(decorated).build());
                            });
                })
                .doFinally(st -> span.end());
    }

    @Override
    public int getOrder() {
        return RateLimitOrders.TPM_INPUT;
    }
}
