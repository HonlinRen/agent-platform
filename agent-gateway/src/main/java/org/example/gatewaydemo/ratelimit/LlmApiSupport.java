package org.example.gatewaydemo.ratelimit;

import org.springframework.http.MediaType;
import org.springframework.web.server.ServerWebExchange;

import java.util.List;

/** 判断当前请求是否应按大模型 API 做 TPM 限流（路径前缀 + POST + JSON/SSE）。 */
public final class LlmApiSupport {

    private LlmApiSupport() {
    }

    public static boolean isLlmApi(ServerWebExchange exchange, List<String> pathPrefixes) {
        String path = exchange.getRequest().getPath().value();
        boolean matchesPrefix = pathPrefixes.stream().anyMatch(path::startsWith);
        if (!matchesPrefix) {
            return false;
        }
        if (!"POST".equalsIgnoreCase(exchange.getRequest().getMethod().name())) {
            return false;
        }
        MediaType contentType = exchange.getRequest().getHeaders().getContentType();
        return contentType == null
                || MediaType.APPLICATION_JSON.isCompatibleWith(contentType)
                || MediaType.parseMediaType("text/event-stream").isCompatibleWith(contentType);
    }
}
