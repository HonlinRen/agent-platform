package org.example.gatewaydemo.ratelimit;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 绑定 application.yaml 中 app.tenants.* */
@ConfigurationProperties(prefix = "app.tenants")
public class TenantQuotaProperties {

    private Map<String, TenantLimits> quotas = defaultQuotas();

    public Map<String, TenantLimits> getQuotas() {
        return quotas;
    }

    public void setQuotas(Map<String, TenantLimits> quotas) {
        this.quotas = quotas == null || quotas.isEmpty() ? defaultQuotas() : quotas;
    }

    public List<String> getKnownTenantIds() {
        return List.copyOf(quotas.keySet());
    }

    public TenantLimits limitsFor(String tenantId) {
        return quotas.getOrDefault(tenantId, quotas.getOrDefault(TenantResolver.DEFAULT_TENANT, new TenantLimits(60, 2000, 2000)));
    }

    private static Map<String, TenantLimits> defaultQuotas() {
        Map<String, TenantLimits> map = new LinkedHashMap<>();
        map.put("default_tenant", new TenantLimits(60, 2000, 2000));
        map.put("default_tenant_test", new TenantLimits(2, 2000, 2000));
        map.put("tenant_vip", new TenantLimits(10, 10000, 10000));
        map.put("tenant_vip_test", new TenantLimits(2, 10000, 10000));
        return map;
    }

    public record TenantLimits(long rpm, long tpmInput, long tpmOutput) {
    }
}
