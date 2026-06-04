package org.example.gatewaydemo;

import org.example.gatewaydemo.ratelimit.JwtProperties;
import org.example.gatewaydemo.ratelimit.RateLimitProperties;
import org.example.gatewaydemo.ratelimit.TenantQuotaProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

/**
 * 网关入口：基于 Spring Cloud Gateway（WebFlux 响应式栈）。
 * <p>
 * 核心能力：路由转发 + 多租户限流（RPM / TPM 输入 / TPM 输出），计数状态存 Redis（Bucket4j）。
 */
@SpringBootApplication
@EnableConfigurationProperties({RateLimitProperties.class, TenantQuotaProperties.class, JwtProperties.class})
public class GatewayDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayDemoApplication.class, args);
    }

}
