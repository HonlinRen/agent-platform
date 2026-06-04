package org.example.gatewaydemo;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.junit.jupiter.api.condition.EnabledIf;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 对已启动的网关做联调（默认 http://localhost:8080）。
 * <p>
 * 1. 先启动：{@code .\mvnw.cmd spring-boot:run}
 * 2. 再执行：{@code .\mvnw.cmd test -Plive}
 *    或：{@code .\mvnw.cmd test -Dtest=RateLimitLiveTest -Dgateway.live=true}
 */
@Tag("live")
@EnabledIf("org.example.gatewaydemo.RateLimitLiveTest#liveTestsEnabled")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class RateLimitLiveTest {

    private static final String BASE_URL = System.getProperty("gateway.baseUrl", "http://localhost:8080");
    private static final String TENANT_HEADER = "X-Tenant-Id";

    private static WebClient client;

    static boolean liveTestsEnabled() {
        return "true".equalsIgnoreCase(System.getProperty("gateway.live"));
    }

    @BeforeAll
    static void initClient() {
        client = WebClient.builder()
                .baseUrl(BASE_URL)
                .build();
    }

    @Test
    @Order(1)
    @DisplayName("[Live] 健康探测：/httpbin/get 可访问")
    void gatewayIsUp() {
        int status = client.get()
                .uri("/httpbin/get")
                .header(TENANT_HEADER, "default_tenant")
                .exchangeToMono(resp -> Mono.just(resp.statusCode().value()))
                .block(Duration.ofSeconds(30));
        assertEquals(200, status);
    }

    @Test
    @Order(2)
    @DisplayName("[Live] LLM 路径：小请求应 2xx")
    void llmSmallRequestSucceeds() {
        String body = "{\"model\":\"gpt-4\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}";
        int status = postLlm("default_tenant", body);
        assertTrue(status >= 200 && status < 300, "expected 2xx, got " + status);
    }

    @Test
    @Order(3)
    @DisplayName("[Live] RPM：tenant_vip 限额 10/min，第 11 次应 429")
    void rpmBurstReturns429() {
        // tenant_vip 生产配额 RPM=10/min（见 TenantQuotaService）
        String tenant = "tenant_vip";
        int lastStatus = 200;
        for (int i = 1; i <= 11; i++) {
            lastStatus = client.get()
                    .uri("/httpbin/get")
                    .header(TENANT_HEADER, tenant)
                    .exchangeToMono(resp -> Mono.just(resp.statusCode().value()))
                    .block(Duration.ofSeconds(30));
        }
        assertEquals(429, lastStatus, "第 11 次请求应触发 RPM 429");
    }

    @Test
    @Order(4)
    @DisplayName("[Live] TPM 输入：超大 body 应 429")
    void tpmInputLargeBodyReturns429() {
        // default_tenant TPM 输入限额 2000/min；字符数/4 估算 → 需 >8000 字符才能触发
        String tenant = "live_tpm_in_" + System.currentTimeMillis();
        String body = "{\"model\":\"gpt-4\",\"messages\":[{\"role\":\"user\",\"content\":\""
                + "z".repeat(9000) + "\"}]}";
        int status = postLlm(tenant, body);
        assertEquals(429, status, "超大输入应触发 TPM input 429");
    }

    @Test
    @Order(5)
    @DisplayName("[Live] 非 LLM 路径：大 body 不因 TPM 输入被拒（仅 RPM）")
    void nonLlmLargeBodyNotBlockedByTpmInput() {
        // 不走 /v1，仅验证不会因 TPM 输入返回 429；body 不宜过大以免 httpbin 异常
        String tenant = "live_non_llm_" + System.currentTimeMillis();
        String body = "{\"payload\":\"" + "a".repeat(2000) + "\"}";
        int status = client.post()
                .uri("/httpbin/post")
                .header(TENANT_HEADER, tenant)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .exchangeToMono(resp -> Mono.just(resp.statusCode().value()))
                .block(Duration.ofSeconds(30));
        assertTrue(status >= 200 && status < 300,
                "非 /v1 路径不应走 TPM 输入，期望 2xx，实际 " + status);
    }

    private static int postLlm(String tenant, String jsonBody) {
        return client.post()
                .uri("/v1/chat/completions")
                .header(TENANT_HEADER, tenant)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(jsonBody)
                .exchangeToMono(resp -> Mono.just(resp.statusCode().value()))
                .block(Duration.ofSeconds(60));
    }
}
