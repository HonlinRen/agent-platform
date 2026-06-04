package org.example.gatewaydemo.ratelimit;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.List;

/** 绑定 application.yaml 中 app.rate-limit.* */
@ConfigurationProperties(prefix = "app.rate-limit")
public record RateLimitProperties(List<String> llmPathPrefixes) {

    public RateLimitProperties {
        if (llmPathPrefixes == null || llmPathPrefixes.isEmpty()) {
            llmPathPrefixes = List.of("/v1/");
        }
    }
}
