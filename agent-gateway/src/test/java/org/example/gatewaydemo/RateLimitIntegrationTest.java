package org.example.gatewaydemo;

import org.example.gatewaydemo.support.MockUpstreamServer;
import org.example.gatewaydemo.support.RateLimitTestQuotaConfig;
import org.example.gatewaydemo.support.RedisTestSupport;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.boot.test.web.server.LocalServerPort;

import java.io.IOException;

/**
 * 嵌入式网关 + 本地 Redis。运行前请启动 Redis。
 * <p>
 * mvn test -Dtest=RateLimitIntegrationTest
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("rate-limit-it")
@Import({RateLimitTestQuotaConfig.class, RedisTestSupport.class})
class RateLimitIntegrationTest {

    private static final String TENANT_HEADER = "X-Tenant-Id";

    @LocalServerPort
    private int port;

    private WebTestClient webTestClient;

    @Autowired
    private RedisTestSupport redisTestSupport;

    @BeforeAll
    static void startMockUpstream() throws IOException {
        MockUpstreamServer.start();
    }

    @AfterAll
    static void stopMockUpstream() throws IOException {
        MockUpstreamServer.shutdown();
    }

    @DynamicPropertySource
    static void mockUpstreamPort(DynamicPropertyRegistry registry) {
        registry.add("mock.upstream.port", MockUpstreamServer::getPort);
    }

    @BeforeEach
    void setUp() {
        redisTestSupport.assumeRedisAvailable();
        redisTestSupport.flushRateLimitKeys();
        webTestClient = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(java.time.Duration.ofSeconds(30))
                .build();
    }

    @Test
    @DisplayName("LLM 路径：配额内 POST /v1/chat/completions 应成功")
    void llmWithinQuota_returnsSuccess() {
        String body = """
                {"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}
                """;

        webTestClient.post()
                .uri("/v1/chat/completions")
                .header(TENANT_HEADER, "default_tenant")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .exchange()
                .expectStatus().is2xxSuccessful();
    }

    @Test
    @DisplayName("RPM：同一租户连续第 4 次请求应 429")
    void rpmExceeded_returns429() {
        for (int i = 0; i < 3; i++) {
            webTestClient.get()
                    .uri("/httpbin/get")
                    .header(TENANT_HEADER, "it_rpm")
                    .exchange()
                    .expectStatus().is2xxSuccessful();
        }

        webTestClient.get()
                .uri("/httpbin/get")
                .header(TENANT_HEADER, "it_rpm")
                .exchange()
                .expectStatus().isEqualTo(429)
                .expectBody()
                .jsonPath("$.error.type").isEqualTo("rate_limit_exceeded");
    }

    @Test
    @DisplayName("TPM 输入：超大 prompt 应 429")
    void tpmInputExceeded_returns429() {
        String hugeContent = "x".repeat(400);
        String body = """
                {"model":"gpt-4","messages":[{"role":"user","content":"%s"}]}
                """.formatted(hugeContent);

        webTestClient.post()
                .uri("/v1/chat/completions")
                .header(TENANT_HEADER, "it_tpm_in")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .exchange()
                .expectStatus().isEqualTo(429)
                .expectBody()
                .jsonPath("$.error.message").value(msg -> ((String) msg).contains("TPM input"));
    }

    @Test
    @DisplayName("TPM 输出：httpbin 回显大响应体应触发输出 TPM 429")
    void tpmOutputExceeded_returns429() {
        String body = """
                {"model":"gpt-4","messages":[{"role":"user","content":"%s"}]}
                """.formatted("y".repeat(500));

        webTestClient.post()
                .uri("/v1/chat/completions")
                .header(TENANT_HEADER, "it_tpm_out")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .exchange()
                .expectStatus().isEqualTo(429);
    }

    @Test
    @DisplayName("非 /v1 路径：不走 TPM 输入，仅 RPM")
    void nonLlmPath_skipsTpmInput_usesRpmOnly() {
        String body = "{\"not\":\"llm\"}";

        webTestClient.post()
                .uri("/httpbin/post")
                .header(TENANT_HEADER, "it_tpm_in")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .exchange()
                .expectStatus().is2xxSuccessful();
    }

    @Test
    @DisplayName("agent-rag 路径：配额内 POST /api/chat/stream 应成功")
    void agentRagChatWithinQuota_returnsSuccess() {
        String body = """
                {"message":"hello","history":[]}
                """;

        webTestClient.post()
                .uri("/api/chat/stream")
                .header(TENANT_HEADER, "default_tenant")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .bodyValue(body)
                .exchange()
                .expectStatus().is2xxSuccessful();
    }

    @Test
    @DisplayName("agent-rag 路径：GET /health 经网关转发应成功")
    void agentRagHealth_returnsSuccess() {
        webTestClient.get()
                .uri("/health")
                .header(TENANT_HEADER, "default_tenant")
                .exchange()
                .expectStatus().is2xxSuccessful()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    @DisplayName("agent-rag 路径：TPM 输入超大 message 应 429")
    void agentRagTpmInputExceeded_returns429() {
        String body = """
                {"message":"%s","history":[]}
                """.formatted("x".repeat(400));

        webTestClient.post()
                .uri("/api/chat/stream")
                .header(TENANT_HEADER, "it_tpm_in")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .exchange()
                .expectStatus().isEqualTo(429)
                .expectBody()
                .jsonPath("$.error.message").value(msg -> ((String) msg).contains("TPM input"));
    }

    @Test
    @DisplayName("管理接口：GET /admin/gateway/metrics 应返回租户统计")
    void gatewayMetricsEndpoint_returnsTenantStats() {
        webTestClient.get()
                .uri("/admin/gateway/metrics")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenants[0].tenant_id").isEqualTo("default_tenant")
                .jsonPath("$.tenants[0].rpm.limit").isEqualTo(60)
                .jsonPath("$.tenants[1].tenant_id").isEqualTo("default_tenant_test")
                .jsonPath("$.tenants[1].rpm.limit").isEqualTo(2)
                .jsonPath("$.tenants[2].tenant_id").isEqualTo("tenant_vip")
                .jsonPath("$.tenants[2].rpm.limit").isEqualTo(10)
                .jsonPath("$.tenants[3].tenant_id").isEqualTo("tenant_vip_test")
                .jsonPath("$.tenants[3].rpm.limit").isEqualTo(2);
    }

    @Test
    @DisplayName("管理接口：RPM 放行后 metrics 累计应增加")
    void gatewayMetricsRecordsRpmAllowed() {
        webTestClient.get()
                .uri("/httpbin/get")
                .header(TENANT_HEADER, "default_tenant")
                .exchange()
                .expectStatus().is2xxSuccessful();

        webTestClient.get()
                .uri("/admin/gateway/metrics")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenants[0].tenant_id").isEqualTo("default_tenant")
                .jsonPath("$.tenants[0].rpm.allowed_total").value(n -> {
                    if (n instanceof Number number) {
                        org.junit.jupiter.api.Assertions.assertTrue(number.longValue() >= 1L);
                    } else {
                        org.junit.jupiter.api.Assertions.fail("expected numeric allowed_total");
                    }
                });
    }

    @Test
    @DisplayName("agent-rag 路径：SSE 大响应应触发输出 TPM 429")
    void agentRagTpmOutputExceeded_returns429() {
        String body = """
                {"message":"%s","history":[]}
                """.formatted("y".repeat(500));

        webTestClient.post()
                .uri("/api/chat/stream")
                .header(TENANT_HEADER, "it_tpm_out")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .exchange()
                .expectStatus().isEqualTo(429);
    }
}
