package org.example.gatewaydemo.ratelimit;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** JWT 租户绑定配置（Demo 级 HS256）。 */
@ConfigurationProperties(prefix = "app.jwt")
public class JwtProperties {

    /** 是否启用 JWT 与 X-Tenant-Id 绑定校验 */
    private boolean enabled = false;
    /** HS256 对称密钥（生产请用环境变量注入） */
    private String secret = "demo-agent-gateway-secret-change-me";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getSecret() {
        return secret;
    }

    public void setSecret(String secret) {
        this.secret = secret;
    }
}
