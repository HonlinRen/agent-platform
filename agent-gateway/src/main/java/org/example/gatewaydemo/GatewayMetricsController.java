package org.example.gatewaydemo;

import org.example.gatewaydemo.ratelimit.DistributedRateLimiterService;
import org.example.gatewaydemo.ratelimit.GatewayMetricsService;
import org.example.gatewaydemo.ratelimit.TenantQuotaService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@RestController
@RequestMapping("/admin/gateway")
public class GatewayMetricsController {

    private final GatewayMetricsService metricsService;
    private final DistributedRateLimiterService rateLimiterService;
    private final TenantQuotaService tenantQuotaService;

    public GatewayMetricsController(GatewayMetricsService metricsService,
                                    DistributedRateLimiterService rateLimiterService,
                                    TenantQuotaService tenantQuotaService) {
        this.metricsService = metricsService;
        this.rateLimiterService = rateLimiterService;
        this.tenantQuotaService = tenantQuotaService;
    }

    @GetMapping("/metrics")
    public Mono<GatewayMetricsResponse> metrics() {
        return Mono.fromCallable(this::buildResponse).subscribeOn(Schedulers.boundedElastic());
    }

    private GatewayMetricsResponse buildResponse() {
        List<TenantMetricsView> tenants = new ArrayList<>();
        for (String tenantId : tenantQuotaService.getKnownTenantIds()) {
            tenants.add(new TenantMetricsView(
                    tenantId,
                    new DimensionMetricsView(
                            tenantQuotaService.getRpmLimit(tenantId),
                            rateLimiterService.getAvailableRpm(tenantId),
                            metricsService.getRpmAllowedTotal(tenantId),
                            metricsService.getRpmRejectedTotal(tenantId)
                    ),
                    new TokenDimensionMetricsView(
                            tenantQuotaService.getTpmInputLimit(tenantId),
                            rateLimiterService.getAvailableTpmInput(tenantId),
                            metricsService.getTpmInputTokensTotal(tenantId),
                            metricsService.getTpmInputRejectedTotal(tenantId)
                    ),
                    new TokenDimensionMetricsView(
                            tenantQuotaService.getTpmOutputLimit(tenantId),
                            rateLimiterService.getAvailableTpmOutput(tenantId),
                            metricsService.getTpmOutputTokensTotal(tenantId),
                            metricsService.getTpmOutputRejectedTotal(tenantId)
                    )
            ));
        }
        return new GatewayMetricsResponse(Instant.now().toString(), tenants);
    }

    public record GatewayMetricsResponse(String collected_at, List<TenantMetricsView> tenants) {
    }

    public record TenantMetricsView(
            String tenant_id,
            DimensionMetricsView rpm,
            TokenDimensionMetricsView tpm_input,
            TokenDimensionMetricsView tpm_output
    ) {
    }

    public record DimensionMetricsView(
            long limit,
            long remaining,
            long allowed_total,
            long rejected_total
    ) {
    }

    public record TokenDimensionMetricsView(
            long limit,
            long remaining,
            long tokens_total,
            long rejected_total
    ) {
    }
}
