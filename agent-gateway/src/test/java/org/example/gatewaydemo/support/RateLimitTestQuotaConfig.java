package org.example.gatewaydemo.support;

import org.example.gatewaydemo.ratelimit.TenantQuotaProperties;
import org.example.gatewaydemo.ratelimit.TenantQuotaService;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

/**
 * 集成测试用低配额，便于快速触发 429。
 */
@TestConfiguration
public class RateLimitTestQuotaConfig {

    @Bean
    @Primary
    TenantQuotaService testTenantQuotaService(TenantQuotaProperties quotaProperties) {
        return new TenantQuotaService(quotaProperties) {
            @Override
            public long getRpmLimit(String tenantId) {
                return switch (tenantId) {
                    case "it_rpm" -> 3L;
                    default -> super.getRpmLimit(tenantId);
                };
            }

            @Override
            public long getTpmInputLimit(String tenantId) {
                return switch (tenantId) {
                    case "it_tpm_in" -> 50L;
                    default -> super.getTpmInputLimit(tenantId);
                };
            }

            @Override
            public long getTpmOutputLimit(String tenantId) {
                return switch (tenantId) {
                    case "it_tpm_out" -> 30L;
                    default -> super.getTpmOutputLimit(tenantId);
                };
            }
        };
    }
}
