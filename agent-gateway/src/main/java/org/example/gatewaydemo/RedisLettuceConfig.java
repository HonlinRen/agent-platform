package org.example.gatewaydemo;

import io.github.bucket4j.distributed.ExpirationAfterWriteStrategy;
import io.github.bucket4j.distributed.proxy.ProxyManager;
import io.github.bucket4j.redis.lettuce.Bucket4jLettuce;
import io.lettuce.core.RedisClient;
import io.lettuce.core.RedisURI;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.codec.ByteArrayCodec;
import io.lettuce.core.codec.RedisCodec;
import io.lettuce.core.codec.StringCodec;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

/**
 * Bucket4j 专用 Redis 连接（与 Spring Data Redis 可共用同一实例）。
 * ProxyManager 负责在 Redis 上维护分布式令牌桶状态。
 */
@Configuration
@EnableConfigurationProperties(RedisLettuceConfig.LocalRedisProperties.class)
public class RedisLettuceConfig {

    @Bean(destroyMethod = "shutdown")
    public RedisClient bucket4jRedisClient(LocalRedisProperties properties) {
        RedisURI.Builder builder = RedisURI.builder()
                .withHost(properties.host())
                .withPort(properties.port())
                .withDatabase(properties.database());

        if (properties.password() != null && !properties.password().isBlank()) {
            builder.withPassword(properties.password().toCharArray());
        }

        return RedisClient.create(builder.build());
    }

    @Bean(destroyMethod = "close")
    public StatefulRedisConnection<String, byte[]> bucket4jRedisConnection(RedisClient bucket4jRedisClient) {
        RedisCodec<String, byte[]> codec = RedisCodec.of(StringCodec.UTF8, ByteArrayCodec.INSTANCE);
        return bucket4jRedisClient.connect(codec);
    }

    @Bean
    public ProxyManager<String> bucket4jProxyManager(StatefulRedisConnection<String, byte[]> bucket4jRedisConnection) {
        // CAS + 1 分钟过期策略，与 RPM/TPM「每分钟」配额对齐
        return Bucket4jLettuce.casBasedBuilder(bucket4jRedisConnection)
                .expirationAfterWrite(ExpirationAfterWriteStrategy.basedOnTimeForRefillingBucketUpToMax(Duration.ofMinutes(1)))
                .build();
    }

    @ConfigurationProperties(prefix = "spring.data.redis")
    record LocalRedisProperties(String host, int port, int database, String password) {
        LocalRedisProperties {
            if (host == null) {
                host = "localhost";
            }
            if (port == 0) {
                port = 6379;
            }
        }
    }
}
