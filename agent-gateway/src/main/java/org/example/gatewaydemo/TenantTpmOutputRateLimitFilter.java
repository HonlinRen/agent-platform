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
import org.example.gatewaydemo.ratelimit.TenantResolver;
import org.example.gatewaydemo.ratelimit.TokenEstimator;
import org.reactivestreams.Publisher;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.http.server.reactive.ServerHttpResponseDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 全局过滤器 #3：TPM 输出（响应侧，支持 SSE 流式与非流式 JSON）。
 * 装饰 ServerHttpResponse，在 writeWith 每个 chunk 上扣减输出 token 配额。
 */
@Component
public class TenantTpmOutputRateLimitFilter implements GlobalFilter, Ordered {

    private final DistributedRateLimiterService rateLimiter;
    private final RateLimitProperties rateLimitProperties;
    private final GatewayMetricsService metricsService;
    private final Tracer tracer;

    public TenantTpmOutputRateLimitFilter(DistributedRateLimiterService rateLimiter,
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
        Span span = tracer.nextSpan().name("gateway.rate_limit.tpm_out")
                .tag("tenant.id", tenantId)
                .tag("http.request_id", ObservabilitySupport.resolveRequestId(exchange))
                .start();
        AtomicLong consumedOutput = new AtomicLong(0L);
        AtomicBoolean rejected = new AtomicBoolean(false);

        ServerHttpResponseDecorator decoratedResponse = new ServerHttpResponseDecorator(exchange.getResponse()) {
            @Override
            public Mono<Void> writeWith(Publisher<? extends DataBuffer> body) {
                MediaType contentType = getHeaders().getContentType();
                Flux<DataBuffer> flux = Flux.from(body).concatMap(buffer -> {
                    if (rejected.get()) {
                        DataBufferUtils.release(buffer);
                        return Mono.empty();
                    }
                    byte[] bytes = TokenEstimator.readBytesAndRelease(buffer);
                    TokenEstimator.OutputChunkResult chunk = TokenEstimator.parseOutputChunk(bytes, contentType);
                    long toConsume = resolveTokensToConsume(chunk, consumedOutput);
                    if (toConsume <= 0L) {
                        return Mono.just(wrap(bytes));
                    }
                    return Mono.fromCallable(() -> rateLimiter.tryConsumeTpmOutput(tenantId, toConsume))
                            .subscribeOn(Schedulers.boundedElastic())
                            .flatMap(allowed -> {
                                if (!allowed) {
                                    rejected.set(true);
                                    metricsService.recordTpmOutputRejected(tenantId);
                                    if (!exchange.getResponse().isCommitted()) {
                                        exchange.getResponse().setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
                                    }
                                    return Mono.empty();
                                }
                                metricsService.recordTpmOutputTokens(tenantId, toConsume);
                                return Mono.just(wrap(bytes));
                            });
                });
                return super.writeWith(flux);
            }

            private DataBuffer wrap(byte[] bytes) {
                if (bytes.length == 0) {
                    return bufferFactory().allocateBuffer(0);
                }
                return bufferFactory().wrap(bytes);
            }
        };

        return chain.filter(exchange.mutate().response(decoratedResponse).build())
                .doFinally(st -> span.end());
    }

    private static long resolveTokensToConsume(TokenEstimator.OutputChunkResult chunk, AtomicLong consumedOutput) {
        if (chunk.usageFromApi()) {
            long total = chunk.tokensToConsume();
            long delta = total - consumedOutput.get();
            consumedOutput.set(total);
            return Math.max(0L, delta);
        }
        long delta = chunk.tokensToConsume();
        if (delta > 0L) {
            consumedOutput.addAndGet(delta);
        }
        return delta;
    }

    @Override
    public int getOrder() {
        return RateLimitOrders.TPM_OUTPUT;
    }
}
