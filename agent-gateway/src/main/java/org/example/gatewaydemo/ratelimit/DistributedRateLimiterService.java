package org.example.gatewaydemo.ratelimit;

import io.github.bucket4j.Bucket;
import io.github.bucket4j.BucketConfiguration;
import io.github.bucket4j.distributed.proxy.ProxyManager;
import org.springframework.stereotype.Service;

import java.time.Duration;

/**
 * 分布式令牌桶：每个租户 × 每种维度对应一个 Redis key。
 * 算法由 Bucket4j 实现，容量按分钟贪婪回填（refillGreedy）。
 */
@Service
public class DistributedRateLimiterService {

    private final ProxyManager<String> proxyManager;
    private final TenantQuotaService tenantQuotaService;

    public DistributedRateLimiterService(ProxyManager<String> bucket4jProxyManager,
                                         TenantQuotaService tenantQuotaService) {
        this.proxyManager = bucket4jProxyManager;
        this.tenantQuotaService = tenantQuotaService;
    }

    public boolean tryConsumeRpm(String tenantId) {
        long limit = tenantQuotaService.getRpmLimit(tenantId);
        return tryConsume("limit:rpm:" + tenantId, limit, 1L);
    }

    public boolean tryConsumeTpmInput(String tenantId, long tokens) {
        long limit = tenantQuotaService.getTpmInputLimit(tenantId);
        return tryConsume("limit:tpm:in:" + tenantId, limit, normalize(tokens));
    }

    public boolean tryConsumeTpmOutput(String tenantId, long tokens) {
        long limit = tenantQuotaService.getTpmOutputLimit(tenantId);
        return tryConsume("limit:tpm:out:" + tenantId, limit, normalize(tokens));
    }

    public long getAvailableRpm(String tenantId) {
        long limit = tenantQuotaService.getRpmLimit(tenantId);
        return getAvailableTokens("limit:rpm:" + tenantId, limit);
    }

    public long getAvailableTpmInput(String tenantId) {
        long limit = tenantQuotaService.getTpmInputLimit(tenantId);
        return getAvailableTokens("limit:tpm:in:" + tenantId, limit);
    }

    public long getAvailableTpmOutput(String tenantId) {
        long limit = tenantQuotaService.getTpmOutputLimit(tenantId);
        return getAvailableTokens("limit:tpm:out:" + tenantId, limit);
    }

    private static long normalize(long tokens) {
        return tokens <= 0L ? 1L : tokens;
    }

    /** redisKey 示例：limit:rpm:tenant_vip、limit:tpm:in:default_tenant */
    private boolean tryConsume(String redisKey, long capacityPerMinute, long tokens) {
        Bucket bucket = getBucket(redisKey, capacityPerMinute);
        return bucket.tryConsume(tokens);
    }

    private long getAvailableTokens(String redisKey, long capacityPerMinute) {
        Bucket bucket = getBucket(redisKey, capacityPerMinute);
        return bucket.getAvailableTokens();
    }

    private Bucket getBucket(String redisKey, long capacityPerMinute) {
        BucketConfiguration configuration = BucketConfiguration.builder()
                .addLimit(limit -> limit
                        .capacity(capacityPerMinute)
                        .refillGreedy(capacityPerMinute, Duration.ofMinutes(1)))
                .build();
        return proxyManager.getProxy(redisKey, () -> configuration);
    }
}
