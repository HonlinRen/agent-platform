package org.example.gatewaydemo.ratelimit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class GatewayMetricsService {

    private final StringRedisTemplate redisTemplate;
    private final MeterRegistry meterRegistry;

    public GatewayMetricsService(StringRedisTemplate redisTemplate, MeterRegistry meterRegistry) {
        this.redisTemplate = redisTemplate;
        this.meterRegistry = meterRegistry;
    }

    public void recordRpmAllowed(String tenantId) {
        increment(key(tenantId, "rpm", "allowed"));
    }

    public void recordRpmRejected(String tenantId) {
        increment(key(tenantId, "rpm", "rejected"));
        incrementMicrometer("gateway_rate_limit_rejected_total", "rpm", tenantId);
    }

    public void recordTpmInputTokens(String tenantId, long tokens) {
        if (tokens > 0L) {
            increment(key(tenantId, "tpm_in", "tokens"), tokens);
            Counter.builder("gateway_tpm_tokens_total")
                    .tag("direction", "in")
                    .tag("tenant", tenantId)
                    .register(meterRegistry)
                    .increment(tokens);
        }
    }

    public void recordTpmInputRejected(String tenantId) {
        increment(key(tenantId, "tpm_in", "rejected"));
        incrementMicrometer("gateway_rate_limit_rejected_total", "tpm_in", tenantId);
    }

    public void recordTpmOutputTokens(String tenantId, long tokens) {
        if (tokens > 0L) {
            increment(key(tenantId, "tpm_out", "tokens"), tokens);
            Counter.builder("gateway_tpm_tokens_total")
                    .tag("direction", "out")
                    .tag("tenant", tenantId)
                    .register(meterRegistry)
                    .increment(tokens);
        }
    }

    public void recordTpmOutputRejected(String tenantId) {
        increment(key(tenantId, "tpm_out", "rejected"));
        incrementMicrometer("gateway_rate_limit_rejected_total", "tpm_out", tenantId);
    }

    public long getRpmAllowedTotal(String tenantId) {
        return getCounter(key(tenantId, "rpm", "allowed"));
    }

    public long getRpmRejectedTotal(String tenantId) {
        return getCounter(key(tenantId, "rpm", "rejected"));
    }

    public long getTpmInputTokensTotal(String tenantId) {
        return getCounter(key(tenantId, "tpm_in", "tokens"));
    }

    public long getTpmInputRejectedTotal(String tenantId) {
        return getCounter(key(tenantId, "tpm_in", "rejected"));
    }

    public long getTpmOutputTokensTotal(String tenantId) {
        return getCounter(key(tenantId, "tpm_out", "tokens"));
    }

    public long getTpmOutputRejectedTotal(String tenantId) {
        return getCounter(key(tenantId, "tpm_out", "rejected"));
    }

    private static String key(String tenantId, String dimension, String metric) {
        return "metrics:gateway:" + tenantId + ":" + dimension + ":" + metric;
    }

    private void increment(String key) {
        increment(key, 1L);
    }

    private void increment(String key, long delta) {
        redisTemplate.opsForValue().increment(key, delta);
    }

    private void incrementMicrometer(String name, String type, String tenantId) {
        Counter.builder(name)
                .tag("type", type)
                .tag("tenant", tenantId)
                .register(meterRegistry)
                .increment();
    }

    private long getCounter(String key) {
        String value = redisTemplate.opsForValue().get(key);
        if (value == null || value.isBlank()) {
            return 0L;
        }
        return Long.parseLong(value);
    }
}
