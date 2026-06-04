package org.example.gatewaydemo.ratelimit;

import org.springframework.web.server.ServerWebExchange;

/**
 * 从请求头解析租户 ID，用于 Redis 限流桶 key 的分片（limit:rpm:{tenant} 等）。
 */
public final class TenantResolver {

    public static final String TENANT_HEADER = "X-Tenant-Id";
    public static final String DEFAULT_TENANT = "default_tenant";

    private TenantResolver() {
    }

    public static String resolve(ServerWebExchange exchange) {
        String tenantId = exchange.getRequest().getHeaders().getFirst(TENANT_HEADER);
        // 未传头时使用默认租户，仍参与独立限流桶
        return tenantId == null || tenantId.isBlank() ? DEFAULT_TENANT : tenantId;
    }
}
