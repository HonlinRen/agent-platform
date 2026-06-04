package org.example.gatewaydemo.support;

import io.lettuce.core.api.StatefulRedisConnection;
import org.junit.jupiter.api.Assumptions;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component
public class RedisTestSupport {

    @Autowired(required = false)
    private StatefulRedisConnection<String, byte[]> bucket4jRedisConnection;

    public void assumeRedisAvailable() {
        Assumptions.assumeTrue(bucket4jRedisConnection != null, "Redis connection bean not available");
        try {
            bucket4jRedisConnection.sync().ping();
        } catch (Exception e) {
            Assumptions.assumeTrue(false, "Redis not reachable at localhost:6379 — " + e.getMessage());
        }
    }

    public void flushRateLimitKeys() {
        if (bucket4jRedisConnection == null) {
            return;
        }
        bucket4jRedisConnection.sync().flushdb();
    }
}
