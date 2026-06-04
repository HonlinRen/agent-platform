package org.example.gatewaydemo.ratelimit;

import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 租户配额源：优先读取 application.yaml 中 app.tenants.quotas。
 */
@Service
public class TenantQuotaService {

    private final TenantQuotaProperties quotaProperties;

    public TenantQuotaService(TenantQuotaProperties quotaProperties) {
        this.quotaProperties = quotaProperties;
    }

    public List<String> getKnownTenantIds() {
        return quotaProperties.getKnownTenantIds();
    }

    public long getRpmLimit(String tenantId) {
        return quotaProperties.limitsFor(tenantId).rpm();
    }

    public long getTpmInputLimit(String tenantId) {
        return quotaProperties.limitsFor(tenantId).tpmInput();
    }

    public long getTpmOutputLimit(String tenantId) {
        return quotaProperties.limitsFor(tenantId).tpmOutput();
    }
}
